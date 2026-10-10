import pytest

from gcounter import GCounter, copy_counters, merge_counters


def test_new_counter_is_zero():
    assert GCounter().value() == 0
    assert GCounter().slots() == {}


def test_increment_adds_to_own_slot_only():
    c = GCounter()
    c.increment("a")
    c.increment("a")
    c.increment("b", 3)
    assert c.slot("a") == 2
    assert c.slot("b") == 3
    assert c.slot("c") == 0
    assert c.value() == 5


@pytest.mark.parametrize("amount", [0, -1])
def test_increment_rejects_non_positive_amounts(amount):
    with pytest.raises(ValueError):
        GCounter().increment("a", amount)


def test_negative_slot_is_rejected():
    with pytest.raises(ValueError):
        GCounter({"a": -1})


def test_merge_takes_the_per_slot_maximum():
    a = GCounter({"a": 3, "b": 1})
    b = GCounter({"b": 4, "c": 2})
    assert a.merge(b) is True
    assert a.slots() == {"a": 3, "b": 4, "c": 2}
    assert a.value() == 9


def test_merge_reports_no_change_when_already_up_to_date():
    a = GCounter({"a": 3})
    assert a.merge(GCounter({"a": 2})) is False
    assert a.slots() == {"a": 3}


def test_merge_is_commutative_associative_and_idempotent():
    x = GCounter({"a": 1, "b": 5})
    y = GCounter({"a": 4})
    z = GCounter({"b": 2, "c": 7})

    xy = x.copy()
    xy.merge(y)
    yx = y.copy()
    yx.merge(x)
    assert xy == yx

    xy_z = xy.copy()
    xy_z.merge(z)
    yz = y.copy()
    yz.merge(z)
    x_yz = x.copy()
    x_yz.merge(yz)
    assert xy_z == x_yz

    xx = x.copy()
    xx.merge(x)
    assert xx == x


def test_merge_never_lowers_a_slot():
    a = GCounter({"a": 5})
    a.merge(GCounter({"a": 1}))
    assert a.slot("a") == 5


def test_copy_is_independent():
    a = GCounter({"a": 1})
    b = a.copy()
    b.increment("a")
    assert a.value() == 1
    assert b.value() == 2


def test_merge_counters_merges_each_key_and_reports_changes():
    mine = {"a": GCounter({"a": 2}), "b": GCounter({"a": 1, "b": 1})}
    theirs = {"a": GCounter({"a": 1}), "b": GCounter({"b": 3}), "c": GCounter({"b": 1})}
    assert merge_counters(mine, theirs) == {"b", "c"}
    assert mine["a"].slots() == {"a": 2}
    assert mine["b"].slots() == {"a": 1, "b": 3}
    assert mine["c"].slots() == {"b": 1}


def test_merge_counters_does_not_alias_incoming_counters():
    mine: dict[str, GCounter] = {}
    theirs = {"a": GCounter({"a": 1})}
    merge_counters(mine, theirs)
    theirs["a"].increment("a")
    assert mine["a"].value() == 1


def test_copy_counters_is_deep():
    original = {"a": GCounter({"a": 1})}
    snapshot = copy_counters(original)
    original["a"].increment("a")
    assert snapshot["a"].value() == 1


def test_two_phones_converge_after_exchanging_state():
    phones = ["phone-a", "phone-b"]
    a = {p: GCounter() for p in phones}
    b = {p: GCounter() for p in phones}

    a["phone-b"].increment("phone-a")  # phone-a likes phone-b
    a["phone-a"].increment("phone-a")  # phone-a likes itself
    b["phone-b"].increment("phone-b")  # phone-b likes itself

    merge_counters(b, copy_counters(a))  # a -> b
    merge_counters(a, copy_counters(b))  # b -> a

    assert a == b
    assert a["phone-a"].value() == 1
    assert a["phone-b"].value() == 2
