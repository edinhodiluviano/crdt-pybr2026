import random

import numpy as np

from board import BLACK, BLUE, RED, WHITE, brush_indices
from board_simulation import BoardSimulation

IDS = ["A", "B", "C", "D"]
W, H = 8, 6


def sim(p: float = 0.25, seed: int = 1) -> BoardSimulation:
    return BoardSimulation(
        IDS, message_probability=p, flight_time=1.0, rng=random.Random(seed), width=W, height=H
    )


def test_nothing_to_say_means_no_envelope():
    s = sim(p=1.0)
    assert s.send("A", "B", 0.0) is None
    assert s.tick(0.0) == [] and s.in_flight == []


def test_a_send_carries_the_segment_and_moves_the_checkpoint():
    s = sim()
    s.paint("A", np.array([0, 1]), RED, 0.5)
    message = s.send("A", "B", 1.0)
    assert message is not None and len(message.segment) == 2
    assert message.arrives_at == 2.0 and s.in_flight == [message]
    assert s.boards["A"].pending("B") == 0 and s.boards["A"].pending("C") == 2
    assert s.send("A", "B", 1.5) is None


def test_delivery_merges_on_arrival_and_reports_what_changed():
    s = sim()
    s.paint("A", np.array([3]), BLUE, 0.5)
    s.send("A", "B", 1.0)
    assert s.deliver(1.5) == [] and not s.converged()
    (delivery,) = s.deliver(2.0)
    assert delivery.changed == 1 and list(delivery.recoloured) == [3]
    assert s.boards["B"].colour[3] == BLUE and s.in_flight == []


def test_the_last_writer_wins_everywhere():
    s = sim()
    s.paint("A", brush_indices(3, 3, 1, W, H), RED, 1.0)
    s.paint("B", brush_indices(3, 3, 1, W, H), BLACK, 1.2)
    for sender, receiver in [("A", "B"), ("B", "A")]:
        s.send(sender, receiver, 2.0)
    s.deliver(3.0)
    assert s.boards["A"].colour[3 * W + 3] == BLACK == s.boards["B"].colour[3 * W + 3]
    assert s.boards["A"].same_state(s.boards["B"])


def test_gossip_converges_once_the_painting_stops():
    s = sim(p=0.25, seed=7)
    rng = random.Random(3)
    now = 0.0
    for _ in range(20):
        now += 1.0
        bid = rng.choice(IDS)
        s.paint(bid, brush_indices(rng.randrange(W), rng.randrange(H), 1, W, H), rng.choice([BLACK, BLUE, RED, WHITE]), now - 0.5)
        s.tick(now)
        s.deliver(now)
    assert not s.converged() or s.in_flight  # still busy, almost surely
    quiet = 0
    while quiet < 10:
        now += 1.0
        sent = s.tick(now)
        s.deliver(now)
        quiet = quiet + 1 if not sent and not s.in_flight else 0
    assert s.converged()
    assert all(board.painted() == s.boards["A"].painted() for board in s.boards.values())
    assert all(board.wal_size == 0 for board in s.boards.values())


def test_the_wal_is_pruned_as_peers_catch_up():
    s = sim(p=1.0)
    s.paint("A", np.arange(10), RED, 0.5)
    a = s.boards["A"]
    assert a.wal_size == 10
    s.send("A", "B", 1.0)
    s.send("A", "C", 1.0)
    assert a.wal_size == 10  # D has not been sent anything yet
    s.send("A", "D", 1.0)
    assert a.wal_size == 0
