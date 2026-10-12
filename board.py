"""A drawing board whose pixels are last-writer-wins registers, plus its write-ahead log.

Every pixel is an LWW register: a colour, the time it was written and who wrote it.
A write with a newer stamp wins; equal stamps go to the higher writer id. Merging two
boards compares pixel by pixel, so the merge is commutative, associative and
idempotent: the boards converge whatever order the writes reach them in. White is a
colour like any other. An erased pixel keeps its stamp and travels like any write;
only pixels nobody ever touched stay out of the messages.

Instead of shipping the whole board, a board keeps a write-ahead log (WAL): the flat
index of every pixel whose register changed here, by a local stroke or by a merge, in
order. One checkpoint per peer marks how far into the WAL that peer has been sent.
The segment for a peer is the WAL after its checkpoint, compacted to one entry per
distinct pixel carrying the pixel's current register, which is at least as new as
anything the log remembers about it. Whatever lies before the slowest peer's
checkpoint has gone to everyone and is pruned.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Iterable
from dataclasses import dataclass

import numpy as np

WIDTH, HEIGHT = 320, 240

WHITE, BLACK, BLUE, GREEN, RED = range(5)
PALETTE = np.array(
    [(255, 255, 255), (0, 0, 0), (30, 90, 230), (40, 160, 70), (229, 57, 70)],
    dtype=np.uint8,
)
NEVER = -math.inf  # stamp of a pixel nobody has written yet

_NO_PIXELS = np.empty(0, dtype=np.int32)


@dataclass(frozen=True)
class Segment:
    """What a board sends one peer: its WAL after that peer's checkpoint, compacted.

    The arrays run in parallel: ``indices[i]`` is a flat pixel index (y * width + x)
    and the other three are that pixel's register. ``raw_count`` is how many WAL
    entries the segment was compacted from.
    """

    indices: np.ndarray
    colours: np.ndarray
    stamps: np.ndarray
    writers: np.ndarray
    raw_count: int

    def __len__(self) -> int:
        return len(self.indices)


class Board:
    """A grid of LWW registers with a WAL and one checkpoint per peer."""

    def __init__(
        self,
        replica: int,
        peers: Iterable[Hashable],
        width: int = WIDTH,
        height: int = HEIGHT,
    ) -> None:
        self.replica = replica
        self.width, self.height = width, height
        n = width * height
        self.colour = np.full(n, WHITE, dtype=np.uint8)
        self.stamp = np.full(n, NEVER, dtype=np.float64)
        self.writer = np.full(n, -1, dtype=np.int8)
        self._wal = _NO_PIXELS
        self.wal_start = 0  # sequence number of the first kept WAL entry
        self.checkpoints: dict[Hashable, int] = {peer: 0 for peer in peers}

    # --- the WAL ---------------------------------------------------------

    @property
    def wal_end(self) -> int:
        """Sequence number the next WAL entry will get."""
        return self.wal_start + len(self._wal)

    @property
    def wal_size(self) -> int:
        """Entries still kept: everything after the slowest peer's checkpoint."""
        return len(self._wal)

    def pending(self, peer: Hashable) -> int:
        """WAL entries ``peer`` has not been sent yet."""
        return self.wal_end - self.checkpoints[peer]

    def wal_offset(self, peer: Hashable) -> int:
        """Where ``peer``'s checkpoint sits inside the kept WAL, from 0 to wal_size."""
        return self.checkpoints[peer] - self.wal_start

    def segment_for(self, peer: Hashable) -> Segment:
        """The compacted WAL after ``peer``'s checkpoint, with the current registers."""
        tail = self._wal[self.wal_offset(peer):]
        indices = np.unique(tail)
        return Segment(
            indices,
            self.colour[indices].copy(),
            self.stamp[indices].copy(),
            self.writer[indices].copy(),
            raw_count=len(tail),
        )

    def mark_sent(self, peer: Hashable) -> None:
        """Move ``peer``'s checkpoint to the end of the WAL, then prune."""
        self.checkpoints[peer] = self.wal_end
        self.prune()

    def prune(self) -> int:
        """Drop the WAL before the slowest peer's checkpoint. Returns entries dropped."""
        floor = min(self.checkpoints.values(), default=self.wal_end)
        dropped = floor - self.wal_start
        if dropped > 0:
            self._wal = self._wal[dropped:]
            self.wal_start = floor
        return dropped

    # --- writes ----------------------------------------------------------

    def write(self, indices: np.ndarray, colour: int, stamp: float) -> int:
        """A local stroke: paint ``colour`` on the distinct pixels ``indices`` at ``stamp``.

        Returns how many registers changed. Repainting a pixel with the colour it
        already has still counts: its stamp moves forward, and that has to travel.
        """
        indices = np.asarray(indices, dtype=np.int32)
        n = len(indices)
        changed, _ = self._apply(
            indices,
            np.full(n, colour, dtype=np.uint8),
            np.full(n, stamp, dtype=np.float64),
            np.full(n, self.replica, dtype=np.int8),
        )
        return len(changed)

    def merge(self, segment: Segment) -> tuple[int, np.ndarray]:
        """Merge a peer's segment. Returns (registers changed, pixels whose colour changed)."""
        changed, recoloured = self._apply(
            segment.indices, segment.colours, segment.stamps, segment.writers
        )
        return len(changed), recoloured

    def _apply(
        self,
        indices: np.ndarray,
        colours: np.ndarray,
        stamps: np.ndarray,
        writers: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """The LWW rule on distinct pixels. The winners are logged to the WAL."""
        if len(indices) == 0:
            return _NO_PIXELS, _NO_PIXELS
        mine_stamp = self.stamp[indices]
        mine_writer = self.writer[indices]
        newer = (stamps > mine_stamp) | ((stamps == mine_stamp) & (writers > mine_writer))
        changed = indices[newer]
        recoloured = changed[self.colour[changed] != colours[newer]]
        self.colour[changed] = colours[newer]
        self.stamp[changed] = stamps[newer]
        self.writer[changed] = writers[newer]
        if len(changed):
            self._wal = np.concatenate([self._wal, changed.astype(np.int32)])
        return changed, recoloured

    # --- reading ---------------------------------------------------------

    def same_state(self, other: Board) -> bool:
        """True when every register matches, stamps and writers included."""
        return (
            np.array_equal(self.colour, other.colour)
            and np.array_equal(self.stamp, other.stamp)
            and np.array_equal(self.writer, other.writer)
        )

    def painted(self) -> int:
        """How many pixels have ever been written, as far as this board knows."""
        return int(np.count_nonzero(self.writer >= 0))

    def rgb(self) -> np.ndarray:
        """The picture as a (height, width, 3) uint8 array."""
        return PALETTE[self.colour].reshape(self.height, self.width, 3)


# --- brushes -------------------------------------------------------------


def brush_indices(
    cx: float, cy: float, radius: float, width: int = WIDTH, height: int = HEIGHT
) -> np.ndarray:
    """Flat indices of the pixels within ``radius`` of (cx, cy), clipped to the board."""
    x0, x1 = max(0, math.floor(cx - radius)), min(width - 1, math.ceil(cx + radius))
    y0, y1 = max(0, math.floor(cy - radius)), min(height - 1, math.ceil(cy + radius))
    if x0 > x1 or y0 > y1:
        return _NO_PIXELS
    ys, xs = np.mgrid[y0 : y1 + 1, x0 : x1 + 1]
    inside = (xs - cx) ** 2 + (ys - cy) ** 2 <= (radius + 0.5) ** 2
    return (ys[inside] * width + xs[inside]).astype(np.int32)


def stroke_indices(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    radius: float,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> np.ndarray:
    """Distinct pixels under brush dabs laid along the segment, close enough to leave no gap."""
    steps = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / max(1.0, radius / 2)))
    dabs = [
        brush_indices(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps, radius, width, height)
        for i in range(steps + 1)
    ]
    return np.unique(np.concatenate(dabs))
