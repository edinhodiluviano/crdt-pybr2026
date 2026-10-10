"""Phones that "like" each other and gossip their G-Counters. No drawing here.

Each phone keeps one :class:`GCounter` per phone (itself included), keyed by
the liked phone's id. The phone's own id is its replica id, so liking a phone
increments that phone's counter at the liker's slot. A message carries a
snapshot of the sender's whole map of counters, and the receiver merges it.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from gcounter import GCounter, copy_counters, merge_counters


@dataclass
class Phone:
    id: str
    likes: dict[str, GCounter]  # liked phone id -> likes it got, as known here

    def like(self, target: str) -> None:
        self.likes[target].increment(self.id)

    def snapshot(self) -> dict[str, GCounter]:
        return copy_counters(self.likes)

    def receive(self, state: dict[str, GCounter]) -> set[str]:
        """Merge an incoming state. Returns the ids whose counter changed."""
        return merge_counters(self.likes, state)


@dataclass
class Message:
    sender: str
    receiver: str
    state: dict[str, GCounter]
    sent_at: float
    arrives_at: float

    def progress(self, now: float) -> float:
        """0.0 when sent, 1.0 on arrival, clamped."""
        span = self.arrives_at - self.sent_at
        if span <= 0:
            return 1.0
        return min(max((now - self.sent_at) / span, 0.0), 1.0)


@dataclass
class Like:
    liker: str
    target: str
    at: float


@dataclass
class Delivery:
    message: Message
    changed: set[str] = field(default_factory=set)  # counters changed by the merge
    at: float = 0.0


class Simulation:
    """Discrete rounds of liking and gossiping between phones."""

    def __init__(
        self,
        phone_ids: Sequence[str],
        *,
        like_probability: float = 0.5,
        message_probability: float = 0.25,
        flight_time: float = 1.0,
        rng: random.Random | None = None,
    ) -> None:
        if len(set(phone_ids)) != len(phone_ids):
            raise ValueError("phone ids must be unique")
        self.phone_ids = list(phone_ids)
        self.phones = {
            pid: Phone(pid, {other: GCounter() for other in self.phone_ids})
            for pid in self.phone_ids
        }
        self.like_probability = like_probability
        self.message_probability = message_probability
        self.flight_time = flight_time
        self.rng = rng or random.Random()
        self.in_flight: list[Message] = []

    def tick(self, now: float) -> list[Like | Message]:
        """One round of decisions, meant to run once per second.

        Each phone likes some phone (itself included, chosen uniformly) with
        ``like_probability``, then sends its state to each other phone with
        ``message_probability``. Returns the likes and messages in order.
        """
        events: list[Like | Message] = []
        for phone_id in self.phone_ids:
            if self.rng.random() < self.like_probability:
                events.append(self.like(phone_id, self.rng.choice(self.phone_ids), now))
            for other in self.phone_ids:
                if other != phone_id and self.rng.random() < self.message_probability:
                    events.append(self.send(phone_id, other, now))
        return events

    def like(self, phone: str, target: str, now: float) -> Like:
        """``phone`` likes ``target``: its own slot in target's counter grows."""
        self.phones[phone].like(target)
        return Like(phone, target, now)

    def send(self, sender: str, receiver: str, now: float) -> Message:
        """Put a snapshot of ``sender``'s state in flight towards ``receiver``."""
        message = Message(
            sender, receiver, self.phones[sender].snapshot(), now, now + self.flight_time
        )
        self.in_flight.append(message)
        return message

    def deliver(self, now: float) -> list[Delivery]:
        """Hand every message that has arrived by ``now`` to its receiver."""
        arrived = [m for m in self.in_flight if now >= m.arrives_at]
        self.in_flight = [m for m in self.in_flight if now < m.arrives_at]
        deliveries = []
        for message in sorted(arrived, key=lambda m: m.arrives_at):
            changed = self.phones[message.receiver].receive(message.state)
            deliveries.append(Delivery(message, changed, now))
        return deliveries

    def converged(self) -> bool:
        """True when every phone holds the same state."""
        states = [phone.likes for phone in self.phones.values()]
        return all(state == states[0] for state in states[1:])
