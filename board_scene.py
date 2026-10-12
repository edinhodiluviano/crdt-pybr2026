"""Drawing and bookkeeping for the paint-board animation.

py5 runs in module mode, so the entry points live in ``animation4.py``. Everything
they share is here: four paint windows near the corners of the screen, the brush
strokes, the WAL bar under each canvas, the envelopes carrying log segments, and the
short-lived effects (a green flash on the pixels a merge recoloured, a pulse around
the window that just merged).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np
import py5

import board
from board import BLACK, BLUE, GREEN, PALETTE, RED, WHITE, Segment, stroke_indices
from board_simulation import BoardSimulation, Delivery, Message
from scene import (
    AMBER,
    ENVELOPE_H,
    FLASH_SECONDS,
    HEIGHT,
    HOVER,
    INK,
    LANE_OFFSET,
    MERGE,
    MUTED,
    PAPER,
    PULSE_SECONDS,
    WIDTH,
    draw_envelope,
    draw_footer,
    draw_header,
)

CANVAS_W, CANVAS_H = board.WIDTH, board.HEIGHT
TITLE_H = 24  # the window's title bar: name on the left, swatches on the right
STRIP_H = 30  # under the canvas: the WAL bar
WINDOW_W = CANVAS_W
WINDOW_H = TITLE_H + CANVAS_H + STRIP_H
MARGIN_X = 60
TOP_Y = 62
BOTTOM_Y = HEIGHT - 10 - WINDOW_H
SWATCHES = [BLACK, WHITE, BLUE, GREEN, RED]  # left to right in the title bar
SWATCH = 16
SWATCH_GAP = 5
BAR_FULL = CANVAS_W * CANVAS_H  # a full WAL bar: one entry per pixel of the board
BAR_H = 10
CLEARANCE = 26  # how far past a window's edge an envelope starts and ends


@dataclass(frozen=True)
class Window:
    """A paint window: title bar, canvas, WAL strip. (x, y) is its top-left corner."""

    x: float
    y: float

    @property
    def canvas(self) -> tuple[float, float]:
        return self.x, self.y + TITLE_H

    @property
    def strip_y(self) -> float:
        return self.y + TITLE_H + CANVAS_H

    @property
    def centre(self) -> tuple[float, float]:
        return self.x + WINDOW_W / 2, self.y + WINDOW_H / 2

    def on_canvas(self, mx: float, my: float) -> bool:
        cx, cy = self.canvas
        return cx <= mx < cx + CANVAS_W and cy <= my < cy + CANVAS_H

    def swatch_box(self, i: int) -> tuple[float, float, float, float]:
        """x, y, w, h of the i-th swatch, right-aligned in the title bar."""
        slots = len(SWATCHES) - i
        x = self.x + WINDOW_W - 8 - slots * (SWATCH + SWATCH_GAP) + SWATCH_GAP
        return x, self.y + (TITLE_H - SWATCH) / 2, SWATCH, SWATCH


@dataclass(frozen=True)
class Hit:
    kind: str  # "canvas" or "swatch"
    board: str
    swatch: int = -1


@dataclass
class Pulse:
    board: str
    colour: tuple[int, int, int]
    born: float


def layout(board_ids: list[str]) -> dict[str, Window]:
    """Up to four windows, one near each corner: top-left, top-right, bottom-left, bottom-right."""
    right = WIDTH - MARGIN_X - WINDOW_W
    corners = [(MARGIN_X, TOP_Y), (right, TOP_Y), (MARGIN_X, BOTTOM_Y), (right, BOTTOM_Y)]
    if len(board_ids) > len(corners):
        raise ValueError("the layout has room for four boards")
    return {bid: Window(*corners[i]) for i, bid in enumerate(board_ids)}


def short(board_id: str) -> str:
    """'Usuária-B' -> 'B': the label for a checkpoint mark."""
    return board_id.rsplit("-", 1)[-1]


def compact(n: int) -> str:
    """1234 -> '1.2k', 12345 -> '12k'."""
    if n < 1000:
        return str(n)
    if n < 10_000:
        return f"{n / 1000:.1f}k"
    return f"{round(n / 1000)}k"


class PaintScene:
    """The simulation plus the visual state around it: selections, images, effects."""

    def __init__(
        self,
        board_ids: list[str],
        rng: random.Random,
        *,
        title: str,
        message_probability: float = 0.25,
        tick_seconds: float = 1.0,
        flight_seconds: float = 1.0,
        brush_radius: float = 3,
    ) -> None:
        self.title = title
        self.sim = BoardSimulation(
            board_ids,
            message_probability=message_probability,
            flight_time=flight_seconds,
            rng=rng,
        )
        self.tick_seconds = tick_seconds
        self.next_tick = tick_seconds
        self.windows = layout(list(board_ids))
        self.brush_radius = brush_radius
        self.selected = {bid: BLACK for bid in board_ids}
        self.pulses: list[Pulse] = []
        self.hover: Hit | None = None
        n = CANVAS_W * CANVAS_H
        self._images: dict[str, py5.Py5Image] = {}
        self._dirty = {bid: True for bid in board_ids}
        self._flash_born = {bid: np.full(n, -math.inf) for bid in board_ids}
        self._flash_until = {bid: -math.inf for bid in board_ids}

    def advance(self, now: float) -> None:
        while now >= self.next_tick:
            self.sim.tick(self.next_tick)
            self.next_tick += self.tick_seconds
        for delivery in self.sim.deliver(now):
            self.on_delivery(delivery)
        self.pulses = [p for p in self.pulses if now - p.born < PULSE_SECONDS]

    # --- painting -------------------------------------------------------

    def paint(self, bid: str, x0: float, y0: float, x1: float, y1: float, now: float) -> int:
        """A stroke on ``bid``'s canvas from (x0, y0) to (x1, y1), in canvas pixels."""
        indices = stroke_indices(x0, y0, x1, y1, self.brush_radius, CANVAS_W, CANVAS_H)
        if len(indices) == 0:
            return 0
        changed = self.sim.paint(bid, indices, self.selected[bid], now)
        if changed:
            self._dirty[bid] = True
        return changed

    def to_canvas(self, bid: str, mx: float, my: float) -> tuple[float, float]:
        cx, cy = self.windows[bid].canvas
        return mx - cx, my - cy

    def hit(self, mx: float, my: float) -> Hit | None:
        for bid, win in self.windows.items():
            if win.on_canvas(mx, my):
                return Hit("canvas", bid)
            for i in range(len(SWATCHES)):
                x, y, w, h = win.swatch_box(i)
                if x <= mx <= x + w and y <= my <= y + h:
                    return Hit("swatch", bid, i)
        return None

    # --- effects --------------------------------------------------------

    def on_delivery(self, delivery: Delivery) -> None:
        bid = delivery.message.receiver
        if len(delivery.recoloured):
            self._flash_born[bid][delivery.recoloured] = delivery.at
            self._flash_until[bid] = delivery.at + FLASH_SECONDS
            self._dirty[bid] = True
        self.pulses.append(Pulse(bid, MERGE if delivery.changed else MUTED, delivery.at))

    def picture(self, bid: str, now: float) -> py5.Py5Image:
        """The canvas image, rebuilt when the board changed or a flash is still fading."""
        flashing = now < self._flash_until[bid]
        img = self._images.get(bid)
        if img is None or self._dirty[bid] or flashing:
            rgb = self.sim.boards[bid].rgb()
            if flashing:
                blend_flash(rgb, self._flash_born[bid], now)
            img = py5.create_image_from_numpy(rgb, "RGB", dst=img)
            self._images[bid] = img
            self._dirty[bid] = False
        return img

    # --- geometry -------------------------------------------------------

    def envelope_position(self, message: Message, now: float) -> tuple[float, float]:
        """From just outside the sender's window to just outside the receiver's."""
        sx, sy = self.windows[message.sender].centre
        rx, ry = self.windows[message.receiver].centre
        dx, dy = rx - sx, ry - sy
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        nx, ny = -uy, ux  # right-hand normal: separates the two directions
        reach = min(
            WINDOW_W / 2 / abs(ux) if ux else math.inf,
            WINDOW_H / 2 / abs(uy) if uy else math.inf,
        ) + CLEARANCE
        x0, y0 = sx + ux * reach, sy + uy * reach
        x1, y1 = rx - ux * reach, ry - uy * reach
        t = message.progress(now)
        t = t * t * (3 - 2 * t)  # ease in and out
        return x0 + (x1 - x0) * t + nx * LANE_OFFSET, y0 + (y1 - y0) * t + ny * LANE_OFFSET


def blend_flash(rgb: np.ndarray, born: np.ndarray, now: float) -> None:
    """Tint the pixels whose flash is still alive towards green, in place."""
    age = now - born
    active = age < FLASH_SECONDS
    if not active.any():
        return
    alpha = (1 - age[active] / FLASH_SECONDS)[:, None]
    flat = rgb.reshape(-1, 3)
    flat[active] = (flat[active] * (1 - alpha) + np.asarray(MERGE) * alpha).astype(np.uint8)


# --- drawing -----------------------------------------------------------


def draw_frame(scene: PaintScene, now: float, pointer: tuple[float, float]) -> None:
    py5.background(*PAPER)
    draw_header(scene.title)
    for message in scene.sim.in_flight:  # under the windows, like the phones hide them
        x, y = scene.envelope_position(message, now)
        draw_envelope(x, y)
        draw_tag(x, y, message.segment)
    for bid, win in scene.windows.items():
        draw_window(scene, bid, win, now)
    for pulse in scene.pulses:
        draw_window_pulse(scene.windows[pulse.board], pulse.colour, (now - pulse.born) / PULSE_SECONDS)
    if scene.hover and scene.hover.kind == "canvas":
        draw_brush_outline(*pointer, scene.brush_radius)
    draw_footer(scene, now)


def draw_window(scene: PaintScene, bid: str, win: Window, now: float) -> None:
    x, y = win.x, win.y
    py5.push_style()
    py5.rect_mode(py5.CORNER)
    py5.stroke(*INK)
    py5.stroke_weight(2)
    py5.fill(*PAPER)
    py5.rect(x, y, WINDOW_W, WINDOW_H, 6)
    py5.no_stroke()
    py5.fill(*HOVER)
    py5.rect(x + 1, y + 1, WINDOW_W - 2, TITLE_H - 1, 5, 5, 0, 0)
    py5.fill(*INK)
    py5.text_size(14)
    py5.text_align(py5.LEFT, py5.CENTER)
    py5.text(bid, x + 10, y + TITLE_H / 2 - 1)
    for i, colour in enumerate(SWATCHES):
        sx, sy, sw, sh = win.swatch_box(i)
        selected = scene.selected[bid] == colour
        grow = 2 if scene.hover == Hit("swatch", bid, i) else 0
        py5.stroke(*(INK if selected else MUTED))
        py5.stroke_weight(2.5 if selected else 1)
        py5.fill(*(int(c) for c in PALETTE[colour]))
        py5.rect(sx - grow, sy - grow, sw + 2 * grow, sh + 2 * grow, 3)
    cx, cy = win.canvas
    py5.image(scene.picture(bid, now), cx, cy)
    py5.stroke(*INK)
    py5.stroke_weight(1)
    py5.line(x, cy, x + WINDOW_W, cy)
    py5.line(x, cy + CANVAS_H, x + WINDOW_W, cy + CANVAS_H)
    draw_wal_bar(scene, bid, win)
    py5.pop_style()


def draw_wal_bar(scene: PaintScene, bid: str, win: Window) -> None:
    """The board's WAL as a bar: kept entries, with a mark at each peer's checkpoint."""
    b = scene.sim.boards[bid]
    bar_x = win.x + 42
    bar_w = WINDOW_W - 42 - 56
    bar_y = win.strip_y + 5
    mid = bar_y + BAR_H / 2 - 1
    py5.text_size(11)
    py5.text_align(py5.LEFT, py5.CENTER)
    py5.no_stroke()
    py5.fill(*MUTED)
    py5.text("WAL", win.x + 8, mid)
    py5.stroke(*MUTED)
    py5.stroke_weight(1)
    py5.no_fill()
    py5.rect(bar_x, bar_y, bar_w, BAR_H, 2)
    if b.wal_size:
        py5.no_stroke()
        py5.fill(*AMBER)
        py5.rect(bar_x, bar_y, max(2.0, bar_w * min(1.0, b.wal_size / BAR_FULL)), BAR_H, 2)
    py5.no_stroke()
    py5.fill(*INK)
    py5.text_align(py5.RIGHT, py5.CENTER)
    py5.text(compact(b.wal_size), win.x + WINDOW_W - 8, mid)
    # Checkpoints close together share one mark so their letters stay readable.
    marks = sorted((min(1.0, b.wal_offset(p) / BAR_FULL) * bar_w, short(p)) for p in b.checkpoints)
    groups: list[tuple[float, list[str]]] = []
    for offset, name in marks:
        if groups and offset - groups[-1][0] < 12:
            groups[-1][1].append(name)
        else:
            groups.append((offset, [name]))
    py5.text_size(10)
    py5.text_align(py5.CENTER, py5.TOP)
    for offset, names in groups:
        mx = bar_x + offset
        py5.stroke(*INK)
        py5.stroke_weight(2)
        py5.line(mx, bar_y - 2, mx, bar_y + BAR_H + 2)
        py5.no_stroke()
        py5.fill(*INK)
        py5.text("".join(sorted(names)), mx, bar_y + BAR_H + 3)


def draw_tag(x: float, y: float, segment: Segment) -> None:
    """Under an envelope: the pixels it carries and the log entries they came from."""
    py5.push_style()
    py5.no_stroke()
    py5.text_align(py5.CENTER, py5.TOP)
    py5.fill(*INK)
    py5.text_size(11)
    top = y + ENVELOPE_H / 2 + 3
    py5.text(f"{compact(len(segment))} px", x, top)
    py5.fill(*MUTED)
    py5.text_size(10)
    py5.text(f"from {compact(segment.raw_count)} ops", x, top + 13)
    py5.pop_style()


def draw_window_pulse(win: Window, colour: tuple[int, int, int], t: float) -> None:
    """An expanding, fading ring around a window that just merged a message."""
    grow = 10 + 36 * t
    py5.push_style()
    py5.rect_mode(py5.CORNER)
    py5.no_fill()
    py5.stroke(*colour, 220 * (1 - t))
    py5.stroke_weight(4)
    py5.rect(win.x - grow / 2, win.y - grow / 2, WINDOW_W + grow, WINDOW_H + grow, 6 + grow / 2)
    py5.pop_style()


def draw_brush_outline(mx: float, my: float, radius: float) -> None:
    py5.push_style()
    py5.no_fill()
    py5.stroke(*INK, 170)
    py5.stroke_weight(1)
    py5.circle(mx, my, 2 * radius + 1)
    py5.pop_style()
