import math

import numpy as np
import pytest

from board import (
    BLACK,
    BLUE,
    NEVER,
    RED,
    WHITE,
    Board,
    Segment,
    brush_indices,
    stroke_indices,
)

W, H = 8, 6  # a tiny board keeps the tests readable


def board(replica: int = 0, peers=("B", "C")) -> Board:
    return Board(replica, peers, W, H)


def segment(index: int, colour: int, stamp: float, writer: int) -> Segment:
    return Segment(
        np.array([index], dtype=np.int32),
        np.array([colour], dtype=np.uint8),
        np.array([stamp], dtype=np.float64),
        np.array([writer], dtype=np.int8),
        raw_count=1,
    )


def test_fresh_board_is_white_and_unwritten():
    b = board()
    assert (b.colour == WHITE).all()
    assert (b.stamp == NEVER).all()
    assert (b.writer == -1).all()
    assert b.painted() == 0 and b.wal_size == 0


def test_newer_stamp_wins_and_older_loses():
    b = board()
    assert b.write([5], RED, 2.0) == 1
    changed, recoloured = b.merge(segment(5, BLUE, 1.0, 1))  # older: ignored
    assert changed == 0 and len(recoloured) == 0 and b.colour[5] == RED
    changed, recoloured = b.merge(segment(5, BLUE, 3.0, 1))  # newer: wins
    assert changed == 1 and list(recoloured) == [5]
    assert b.colour[5] == BLUE and b.stamp[5] == 3.0 and b.writer[5] == 1


def test_equal_stamps_go_to_the_higher_writer():
    low, high = board(replica=0), board(replica=1)
    low.write([3], RED, 1.0)
    high.write([3], BLUE, 1.0)
    low.merge(high.segment_for("B"))
    high.merge(low.segment_for("B"))
    assert low.colour[3] == high.colour[3] == BLUE
    assert low.same_state(high)


def test_merge_is_idempotent_and_duplicates_are_not_logged():
    b = board()
    seg = segment(7, BLACK, 1.0, 2)
    changed, recoloured = b.merge(seg)
    assert changed == 1 and list(recoloured) == [7]
    size = b.wal_size
    changed, recoloured = b.merge(seg)
    assert changed == 0 and len(recoloured) == 0
    assert b.wal_size == size  # a duplicate changes nothing, so nothing to forward


def test_repainting_the_same_colour_still_moves_the_stamp_and_logs():
    b = board()
    b.write([4], BLACK, 1.0)
    assert b.write([4], BLACK, 2.0) == 1
    assert b.stamp[4] == 2.0 and b.wal_size == 2
    # Without that, a write stamped between the two would win elsewhere and lose here.
    assert b.merge(segment(4, RED, 1.5, 1))[0] == 0


def test_segment_compacts_to_one_entry_per_pixel_with_the_latest_register():
    b = board()
    b.write([1, 2], RED, 1.0)
    b.write([2], BLUE, 2.0)
    seg = b.segment_for("B")
    assert seg.raw_count == 3 and len(seg) == 2
    assert list(seg.indices) == [1, 2]
    assert list(seg.colours) == [RED, BLUE]
    assert list(seg.stamps) == [1.0, 2.0]
    assert list(seg.writers) == [0, 0]


def test_erasing_travels_as_a_white_write():
    a, b = board(0, peers=["B"]), board(1, peers=["A"])
    a.write([9], RED, 1.0)
    b.merge(a.segment_for("B"))
    a.mark_sent("B")
    assert b.colour[9] == RED
    a.write([9], WHITE, 2.0)
    seg = a.segment_for("B")
    assert list(seg.indices) == [9] and seg.colours[0] == WHITE
    b.merge(seg)
    assert b.colour[9] == WHITE and b.stamp[9] == 2.0
    assert a.same_state(b)


def test_checkpoints_move_on_send_and_the_log_is_pruned_behind_the_slowest_peer():
    b = board()
    b.write([0, 1, 2], RED, 1.0)
    assert b.wal_size == 3 and b.pending("B") == b.pending("C") == 3
    b.mark_sent("B")
    assert b.pending("B") == 0 and b.pending("C") == 3
    assert b.wal_size == 3 and b.wal_offset("B") == 3 and b.wal_offset("C") == 0
    assert len(b.segment_for("B")) == 0
    b.write([3], RED, 2.0)
    b.mark_sent("C")
    assert b.wal_size == 1 and b.wal_start == 3  # only the entry B still lacks
    assert b.wal_offset("B") == 0 and b.wal_offset("C") == 1
    assert list(b.segment_for("B").indices) == [3]
    b.mark_sent("B")
    assert b.wal_size == 0 and b.wal_end == 4


def test_a_board_forwards_what_it_learned_without_an_echo_storm():
    ids = ["A", "B", "C"]
    a, b, c = (Board(i, [x for x in ids if x != ids[i]], W, H) for i in range(3))
    c.write([6], BLACK, 1.0)
    b.merge(c.segment_for("B"))
    c.mark_sent("B")
    assert b.pending("A") == 1  # B logged what it learned from C
    a.merge(b.segment_for("A"))
    b.mark_sent("A")
    assert a.colour[6] == BLACK and a.writer[6] == 2  # C's write, via B
    # The same write arriving directly from C changes nothing and is not re-logged.
    changed, recoloured = a.merge(c.segment_for("A"))
    assert changed == 0 and len(recoloured) == 0
    assert a.pending("B") == 1 and a.pending("C") == 1
    # The echo back to C changes nothing there either.
    changed, recoloured = c.merge(a.segment_for("C"))
    assert changed == 0 and len(recoloured) == 0


def test_merge_order_does_not_matter():
    first, second = segment(2, RED, 5.0, 1), segment(2, BLUE, 4.0, 2)
    x, y = board(), board()
    x.merge(first)
    x.merge(second)
    y.merge(second)
    y.merge(first)
    assert x.same_state(y) and x.colour[2] == RED


def test_same_state_compares_registers_not_just_colours():
    x, y = board(), board()
    x.merge(segment(2, RED, 1.0, 1))
    y.merge(segment(2, RED, 2.0, 1))
    assert not x.same_state(y)


def test_brush_indices_are_distinct_round_and_clipped():
    centre = brush_indices(4, 3, 1, W, H)
    assert sorted(centre) == sorted({3 * W + 4, 2 * W + 4, 4 * W + 4, 3 * W + 3, 3 * W + 5,
                                     2 * W + 3, 2 * W + 5, 4 * W + 3, 4 * W + 5})
    corner = brush_indices(0, 0, 2, W, H)
    assert len(corner) == len(set(corner.tolist())) and corner.min() >= 0
    assert all(i % W <= 2 and i // W <= 2 for i in corner)
    assert len(brush_indices(-10, -10, 2, W, H)) == 0
    assert list(brush_indices(1, 1, 0, W, H)) == [W + 1]


def test_a_stroke_leaves_no_gap_between_dabs():
    radius = 1
    stroke = stroke_indices(0, 1, 7, 1, radius, W, H)
    xs = sorted({i % W for i in stroke if i // W == 1})
    assert xs == list(range(W))
    assert len(stroke) == len(set(stroke.tolist()))
    dot = stroke_indices(3, 3, 3, 3, radius, W, H)
    assert set(dot.tolist()) == set(brush_indices(3, 3, radius, W, H).tolist())


def test_rgb_is_the_palette_applied_to_the_grid():
    b = board()
    b.write([W + 2], RED, 1.0)
    rgb = b.rgb()
    assert rgb.shape == (H, W, 3)
    assert tuple(rgb[1, 2]) == (229, 57, 70) and tuple(rgb[0, 0]) == (255, 255, 255)
