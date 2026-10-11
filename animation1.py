"""Animation 1: phones that "like" each other and gossip their G-Counters, by hand.

Nothing happens on its own. Click a user's name beside a phone and that phone
likes that user: the phone's own slot in the user's G-Counter grows by one.
Click a phone and it sends its state, one G-Counter per user, to every other
phone; the envelope takes FLIGHT_SECONDS to arrive and the receiver merges it
on arrival (maximum per replica slot). The reset button at the bottom right
puts everything back to the start: fresh G-Counters, nothing in flight, t = 0.

Beside each phone, one line per user shows how many likes that user has, as
far as this replica knows. A heart pops when a like happens, and the lines
that change on a merge flash green.

Run:  uv run animation1.py
"""

from __future__ import annotations

import random

import py5

from scene import HEIGHT, HOVER, INK, PAPER, WIDTH, Scene, draw_frame

PHONE_IDS = ["Usuária-A", "Usuária-B"]
FLIGHT_SECONDS = 1.0
RESET_BUTTON = (WIDTH - 160, HEIGHT - 80, 120, 40)  # x, y, w, h: bottom right

scene: Scene
_start = 0.0  # sketch time of the last reset, in seconds
_cursor: int | None = None
_hover_button = False


def settings() -> None:
    py5.size(WIDTH, HEIGHT)


def setup() -> None:
    py5.window_title("CAPstagram")
    py5.frame_rate(60)
    reset()


def reset() -> None:
    """Back to the initial state: new phones with empty counters, clock at zero."""
    global scene, _start
    scene = Scene(
        PHONE_IDS,
        random.Random(),
        title="CAPstagram",
        flight_seconds=FLIGHT_SECONDS,
    )
    _start = py5.millis() / 1000


def elapsed() -> float:
    """The animation clock: seconds since the last reset."""
    return py5.millis() / 1000 - _start


def in_button(x: float, y: float) -> bool:
    bx, by, bw, bh = RESET_BUTTON
    return bx <= x <= bx + bw and by <= y <= by + bh


def hover(x: float, y: float) -> None:
    """Remember what is under the pointer, for the highlight and the cursor."""
    global _hover_button
    _hover_button = in_button(x, y)
    scene.hover_line = None if _hover_button else scene.hit_line(x, y)
    scene.hover_phone = None
    if not _hover_button and not scene.hover_line:
        scene.hover_phone = scene.hit_phone(x, y)
    hot = _hover_button or scene.hover_line or scene.hover_phone
    set_cursor(py5.HAND if hot else py5.ARROW)


def click(x: float, y: float, now: float) -> None:
    if in_button(x, y):
        reset()
    elif line := scene.hit_line(x, y):
        scene.like(*line, now)
    elif phone := scene.hit_phone(x, y):
        scene.send(phone, now)


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
    draw_frame(scene, now)
    draw_reset_button(_hover_button)


def mouse_pressed() -> None:
    click(py5.mouse_x, py5.mouse_y, elapsed())


if __name__ == "__main__":
    py5.run_sketch()
