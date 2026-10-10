import random

import pytest

from simulation import Delivery, Like, Message, Simulation

IDS = ["phone-a", "phone-b", "phone-c"]


def values(sim, phone):
    return {key: counter.value() for key, counter in sim.phones[phone].likes.items()}


def test_every_phone_starts_with_one_zero_counter_per_phone():
    sim = Simulation(IDS)
    for phone in IDS:
        assert values(sim, phone) == {pid: 0 for pid in IDS}


def test_duplicate_ids_are_rejected():
    with pytest.raises(ValueError):
        Simulation(["a", "a"])


def test_like_increments_the_target_counter_at_the_liker_slot():
    sim = Simulation(IDS, like_probability=1.0, message_probability=0.0, rng=random.Random(1))
    events = sim.tick(now=1.0)
    likes = [e for e in events if isinstance(e, Like)]
    assert len(likes) == len(IDS)
    assert not [e for e in events if isinstance(e, Message)]
    for like in likes:
        assert like.at == 1.0
        assert sim.phones[like.liker].likes[like.target].slot(like.liker) == 1
    # a phone only knows about its own likes until it hears from the others
    for phone in IDS:
        assert sum(values(sim, phone).values()) == 1


def test_messages_go_to_every_other_phone_with_a_snapshot():
    sim = Simulation(IDS, like_probability=0.0, message_probability=1.0, flight_time=2.0)
    events = sim.tick(now=3.0)
    messages = [e for e in events if isinstance(e, Message)]
    assert len(messages) == len(IDS) * (len(IDS) - 1)
    assert sim.in_flight == messages
    for message in messages:
        assert message.sender != message.receiver
        assert message.sent_at == 3.0
        assert message.arrives_at == 5.0
        assert set(message.state) == set(IDS)
    # the snapshot does not follow later changes on the sender
    sim.phones["phone-a"].like("phone-b")
    for message in messages:
        assert message.state["phone-b"].value() == 0


def test_message_progress_is_clamped():
    message = Message("a", "b", {}, sent_at=1.0, arrives_at=3.0)
    assert message.progress(0.0) == 0.0
    assert message.progress(2.0) == 0.5
    assert message.progress(9.0) == 1.0


def test_deliver_merges_on_arrival_only():
    sim = Simulation(["phone-a", "phone-b"], like_probability=0.0, message_probability=0.0)
    sim.phones["phone-a"].like("phone-b")
    sim.phones["phone-a"].like("phone-a")
    sim.message_probability = 1.0
    sim.tick(now=1.0)
    sim.message_probability = 0.0

    assert sim.deliver(now=1.5) == []
    assert values(sim, "phone-b") == {"phone-a": 0, "phone-b": 0}

    deliveries = sim.deliver(now=2.0)
    assert sim.in_flight == []
    to_b = [d for d in deliveries if d.message.receiver == "phone-b"]
    assert len(to_b) == 1
    assert to_b[0].changed == {"phone-a", "phone-b"}
    assert to_b[0].at == 2.0
    assert values(sim, "phone-b") == {"phone-a": 1, "phone-b": 1}
    # the message from b carried nothing new for a
    to_a = [d for d in deliveries if d.message.receiver == "phone-a"]
    assert to_a[0].changed == set()


def test_full_gossip_round_converges():
    sim = Simulation(IDS, like_probability=1.0, message_probability=1.0, rng=random.Random(3))
    sim.tick(now=1.0)
    assert not sim.converged()
    sim.deliver(now=2.0)
    assert sim.converged()
    total = sum(values(sim, "phone-a").values())
    assert total == len(IDS)  # every like of the round is counted exactly once


def test_random_run_never_loses_likes_and_converges_after_a_final_exchange():
    sim = Simulation(IDS, rng=random.Random(42))
    likes = 0
    seen = {phone: {pid: 0 for pid in IDS} for phone in IDS}
    for second in range(1, 60):
        for event in sim.tick(now=float(second)):
            if isinstance(event, Like):
                likes += 1
        sim.deliver(now=second + 0.5)
        for phone in IDS:  # G-Counters only grow
            for key, value in values(sim, phone).items():
                assert value >= seen[phone][key]
                seen[phone][key] = value
    assert likes > 0

    sim.like_probability = 0.0
    sim.message_probability = 1.0
    sim.tick(now=100.0)
    deliveries = sim.deliver(now=101.0)
    assert all(isinstance(d, Delivery) for d in deliveries)
    assert sim.converged()
    assert sum(values(sim, "phone-a").values()) == likes


def test_manual_like_and_send():
    sim = Simulation(["phone-a", "phone-b"], like_probability=0.0, message_probability=0.0)
    like = sim.like("phone-a", "phone-b", now=2.0)
    assert like == Like("phone-a", "phone-b", 2.0)
    assert values(sim, "phone-a") == {"phone-a": 0, "phone-b": 1}
    assert values(sim, "phone-b") == {"phone-a": 0, "phone-b": 0}

    message = sim.send("phone-a", "phone-b", now=2.5)
    assert sim.in_flight == [message]
    assert (message.sender, message.receiver) == ("phone-a", "phone-b")
    assert (message.sent_at, message.arrives_at) == (2.5, 3.5)
    assert message.state["phone-b"].value() == 1

    assert sim.deliver(now=3.5)[0].changed == {"phone-b"}
    assert sim.converged()
