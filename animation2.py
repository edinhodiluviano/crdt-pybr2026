"""Animation 2: the manual version of animation 1.

Nothing happens on its own. Click a user's name beside a phone and that phone
likes that user: the phone's own slot in the user's G-Counter grows by one.
Click a phone and it sends its state to every other phone; the envelope takes
FLIGHT_SECONDS to arrive and the receiver merges it on arrival.

Run:  uv run animation2.py
"""

from __future__ import annotations

import random

import py5

from scene import HEIGHT, WIDTH, Scene, draw_frame

PHONE_IDS = ["Usuária-A", "Usuária-B"]
FLIGHT_SECONDS = 1.0

scene: Scene
_cursor: int | None = None


def settings() -> None:
    py5.size(WIDTH, HEIGHT)


def setup() -> None:
    global scene
    py5.window_title("CRDT: G-Counter likes, by hand")
    py5.frame_rate(60)
    others = "the other phone" if len(PHONE_IDS) == 2 else "every other phone"
    scene = Scene(
        PHONE_IDS,
        random.Random(),
        title="G-Counter likes, by hand",
        subtitle=(
            "nothing happens on its own. Click a name beside a phone to like that user "
            f"from that phone. Click a phone to send its state to {others}."
        ),
        flight_seconds=FLIGHT_SECONDS,
    )


def hover(x: float, y: float) -> None:
    """Remember what is under the pointer, for the highlight and the cursor."""
    scene.hover_line = scene.hit_line(x, y)
    scene.hover_phone = None if scene.hover_line else scene.hit_phone(x, y)
    set_cursor(py5.HAND if scene.hover_line or scene.hover_phone else py5.ARROW)


def click(x: float, y: float, now: float) -> None:
    if line := scene.hit_line(x, y):
        scene.like(*line, now)
    elif phone := scene.hit_phone(x, y):
        scene.send(phone, now)


def set_cursor(kind: int) -> None:
    global _cursor
    if kind != _cursor:
        py5.cursor(kind)
        _cursor = kind


def draw() -> None:
    now = py5.millis() / 1000
    hover(py5.mouse_x, py5.mouse_y)
    scene.advance(now)
    draw_frame(scene, now)


def mouse_pressed() -> None:
    click(py5.mouse_x, py5.mouse_y, py5.millis() / 1000)


if __name__ == "__main__":
    py5.run_sketch()
