"""Boards that get painted on and ship WAL segments to each other. No drawing here.

Every tick each board rolls a die per other board and, on success, sends it the
compacted WAL segment after that board's checkpoint, then moves the checkpoint to
the end of the log. Nothing is sent when the segment is empty. The message takes
``flight_time`` to arrive and the receiver merges it, pixel by pixel, on arrival.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from board import HEIGHT, WIDTH, Board, Segment


@dataclass
class Message:
    sender: str
    receiver: str
    segment: Segment
    sent_at: float
    arrives_at: float

    def progress(self, now: float) -> float:
        """0.0 when sent, 1.0 on arrival, clamped."""
        span = self.arrives_at - self.sent_at
        if span <= 0:
            return 1.0
        return min(max((now - self.sent_at) / span, 0.0), 1.0)


@dataclass
class Delivery:
    message: Message
    changed: int  # registers the merge updated
    recoloured: np.ndarray  # flat indices of the pixels whose colour changed
    at: float


class BoardSimulation:
    """Discrete rounds of gossip between boards; the painting comes from outside."""

    def __init__(
        self,
        board_ids: Sequence[str],
        *,
        message_probability: float = 0.25,
        flight_time: float = 1.0,
        rng: random.Random | None = None,
        width: int = WIDTH,
        height: int = HEIGHT,
    ) -> None:
        if len(set(board_ids)) != len(board_ids):
            raise ValueError("board ids must be unique")
        self.board_ids = list(board_ids)
        self.boards = {
            bid: Board(i, [other for other in self.board_ids if other != bid], width, height)
            for i, bid in enumerate(self.board_ids)
        }
        self.message_probability = message_probability
        self.flight_time = flight_time
        self.rng = rng or random.Random()
        self.in_flight: list[Message] = []

    def paint(self, board_id: str, indices: np.ndarray, colour: int, now: float) -> int:
        """Paint ``colour`` on ``board_id`` at ``now``. Returns registers changed."""
        return self.boards[board_id].write(indices, colour, now)

    def tick(self, now: float) -> list[Message]:
        """One round of decisions, meant to run once per second."""
        messages = []
        for sender in self.board_ids:
            for receiver in self.board_ids:
                if receiver != sender and self.rng.random() < self.message_probability:
                    if message := self.send(sender, receiver, now):
                        messages.append(message)
        return messages

    def send(self, sender: str, receiver: str, now: float) -> Message | None:
        """Put ``sender``'s segment for ``receiver`` in flight, unless it is empty."""
        board = self.boards[sender]
        segment = board.segment_for(receiver)
        if len(segment) == 0:
            return None
        board.mark_sent(receiver)
        message = Message(sender, receiver, segment, now, now + self.flight_time)
        self.in_flight.append(message)
        return message

    def deliver(self, now: float) -> list[Delivery]:
        """Hand every message that has arrived by ``now`` to its receiver."""
        arrived = [m for m in self.in_flight if now >= m.arrives_at]
        self.in_flight = [m for m in self.in_flight if now < m.arrives_at]
        deliveries = []
        for message in sorted(arrived, key=lambda m: m.arrives_at):
            changed, recoloured = self.boards[message.receiver].merge(message.segment)
            deliveries.append(Delivery(message, changed, recoloured, now))
        return deliveries

    def converged(self) -> bool:
        """True when every board holds the same registers."""
        boards = list(self.boards.values())
        return all(board.same_state(boards[0]) for board in boards[1:])
