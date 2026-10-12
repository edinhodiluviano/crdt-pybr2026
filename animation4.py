"""Animation 4: four paint boards that gossip their strokes through a write-ahead log.

Each window near a corner is a replica of the same 320 x 240 picture and a tiny paint
program: pick a colour in its title bar, draw with the mouse, resize the brush with
the wheel. Every pixel is a last-writer-wins register (colour, time, writer), so a
pixel painted on two boards ends up with the later stroke everywhere. White is a
colour like any other: erasing is a write that travels too.

Instead of shipping the whole picture, a board logs the pixels it changed, by its own
strokes or by merges, in a write-ahead log (WAL), and keeps one checkpoint per peer.
Every second it sends each other board, with probability MESSAGE_PROBABILITY, the log
after that board's checkpoint, compacted to one entry per pixel, and moves the
checkpoint to the end. Nothing is sent when there is nothing new. The envelope takes
FLIGHT_SECONDS to arrive and shows how many pixels it carries and from how many log
entries they were compacted. On arrival the receiver merges them, and the pixels that
change colour flash green.

The bar under each canvas is the board's WAL: its length is the entries still kept, a
full bar being one entry per pixel of the board, with a mark at each peer's
checkpoint. Entries behind the slowest peer are pruned, so the bar shrinks from the
left as the peers catch up. The reset button at the top right starts over.

Run:  uv run animation4.py
"""

from __future__ import annotations

import random

import py5

from board_scene import SWATCHES, PaintScene, draw_frame
from scene import HEIGHT, HOVER, INK, PAPER, WIDTH

BOARD_IDS = ["Usuária-A", "Usuária-B", "Usuária-C", "Usuária-D"]
MESSAGE_PROBABILITY = 0.25
TICK_SECONDS = 1.0
FLIGHT_SECONDS = 1.0
BRUSH_RADIUS = 3  # pixels; the mouse wheel moves it between 1 and MAX_BRUSH
MAX_BRUSH = 24
SEED: int | None = None  # set an int for a repeatable gossip pattern
RESET_BUTTON = (WIDTH - 160, 14, 120, 36)  # x, y, w, h: top right
TITLE = "CAPintura"

scene: PaintScene
_start = 0.0  # sketch time of the last reset, in seconds
_stroke: tuple[str, float, float] | None = None  # board being painted, last point on it
_cursor: int | None = None
_hover_button = False


def settings() -> None:
    py5.size(WIDTH, HEIGHT)


def setup() -> None:
    py5.window_title(TITLE)
    py5.frame_rate(60)
    reset()


def reset() -> None:
    """Back to the start: white boards, empty logs, nothing in flight, clock at zero."""
    global scene, _start, _stroke
    scene = PaintScene(
        BOARD_IDS,
        random.Random(SEED),
        title=TITLE,
        message_probability=MESSAGE_PROBABILITY,
        tick_seconds=TICK_SECONDS,
        flight_seconds=FLIGHT_SECONDS,
        brush_radius=BRUSH_RADIUS,
    )
    _start = py5.millis() / 1000
    _stroke = None


def elapsed() -> float:
    """The animation clock: seconds since the last reset."""
    return py5.millis() / 1000 - _start


def in_button(x: float, y: float) -> bool:
    bx, by, bw, bh = RESET_BUTTON
    return bx <= x <= bx + bw and by <= y <= by + bh


def hover(x: float, y: float) -> None:
    """Remember what is under the pointer, for the highlights and the cursor."""
    global _hover_button
    _hover_button = in_button(x, y)
    scene.hover = None if _hover_button else scene.hit(x, y)
    if _hover_button or (scene.hover and scene.hover.kind == "swatch"):
        set_cursor(py5.HAND)
    elif scene.hover:
        set_cursor(py5.CROSS)
    else:
        set_cursor(py5.ARROW)


def set_cursor(kind: int) -> None:
    global _cursor
    if kind != _cursor:
        py5.cursor(kind)
        _cursor = kind


def draw_reset_button(hovered: bool) -> None:
    x, y, w, h = RESET_BUTTON
    py5.push_style()
    py5.rect_mode(py5.CORNER)
    py5.stroke(*INK)
    py5.stroke_weight(2)
    py5.fill(*(HOVER if hovered else PAPER))
    py5.rect(x, y, w, h, 8)
    py5.no_stroke()
    py5.fill(*INK)
    py5.text_size(18)
    py5.text_align(py5.CENTER, py5.CENTER)
    py5.text("reset", x + w / 2, y + h / 2 - 1)
    py5.pop_style()


def draw() -> None:
    now = elapsed()
    hover(py5.mouse_x, py5.mouse_y)
    scene.advance(now)
    draw_frame(scene, now, (py5.mouse_x, py5.mouse_y))
    draw_reset_button(_hover_button)


def mouse_pressed() -> None:
    global _stroke
    x, y = py5.mouse_x, py5.mouse_y
    if in_button(x, y):
        reset()
        return
    hit = scene.hit(x, y)
    if hit is None:
        return
    if hit.kind == "swatch":
        scene.selected[hit.board] = SWATCHES[hit.swatch]
    else:
        cx, cy = scene.to_canvas(hit.board, x, y)
        scene.paint(hit.board, cx, cy, cx, cy, elapsed())
        _stroke = (hit.board, cx, cy)


def mouse_dragged() -> None:
    """Keep painting the board the stroke started on; the brush clips at its edges."""
    global _stroke
    if _stroke is None:
        return
    bid, x0, y0 = _stroke
    x1, y1 = scene.to_canvas(bid, py5.mouse_x, py5.mouse_y)
    scene.paint(bid, x0, y0, x1, y1, elapsed())
    _stroke = (bid, x1, y1)


def mouse_released() -> None:
    global _stroke
    _stroke = None


def mouse_wheel(event: py5.Py5MouseEvent) -> None:
    """Wheel up for a bigger brush, down for a smaller one."""
    scene.brush_radius = min(MAX_BRUSH, max(1, scene.brush_radius - event.get_count()))


if __name__ == "__main__":
    py5.run_sketch()
