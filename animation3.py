"""Animation 3: the automatic version of animation 2, with four phones.

Every second each phone:

1. likes some user, itself included, with probability LIKE_PROBABILITY. The
   like increments that user's G-Counter at the liker's own replica slot;
2. sends its whole state, one G-Counter per user, to each other phone with
   probability MESSAGE_PROBABILITY. The envelope takes FLIGHT_SECONDS to
   arrive and the receiver merges it on arrival (maximum per replica slot).

Beside each phone, one line per user shows how many likes that user has, as
far as this replica knows. A heart pops when a like happens, and the lines
that change on a merge flash green.

The "Parar ♥" button at the bottom right stops the likes. From then on only
the messages keep flowing, so the replicas drift together until they all
agree.

Run:  uv run animation3.py
"""

from __future__ import annotations

import random

import py5

from scene import (
    HEIGHT,
    HOVER,
    INK,
    MUTED,
    PAPER,
    WIDTH,
    Scene,
    draw_frame,
    draw_heart,
)

PHONE_IDS = ["Usuária-A", "Usuária-B", "Usuária-C", "Usuária-D"]
LIKE_PROBABILITY = 0.5
MESSAGE_PROBABILITY = 0.25
TICK_SECONDS = 1.0
FLIGHT_SECONDS = 1.0
SEED: int | None = None  # set an int for a repeatable run
STOP_BUTTON = (WIDTH - 160, HEIGHT - 80, 120, 40)  # x, y, w, h: bottom right
STOP_LABEL = "Parar"
HEART_SIZE = 8  # draw_heart's s: the heart is about 1.9 s tall and 2.3 s wide

scene: Scene
_stopped_at: float | None = None  # sketch time of the click on the button
_cursor: int | None = None


def settings() -> None:
    py5.size(WIDTH, HEIGHT)


def setup() -> None:
    global scene
    py5.window_title("CAPstagram")
    py5.frame_rate(60)
    scene = Scene(
        PHONE_IDS,
        random.Random(SEED),
        title="CAPstagram",
        like_probability=LIKE_PROBABILITY,
        message_probability=MESSAGE_PROBABILITY,
        tick_seconds=TICK_SECONDS,
        flight_seconds=FLIGHT_SECONDS,
    )


def in_button(x: float, y: float) -> bool:
    bx, by, bw, bh = STOP_BUTTON
    return bx <= x <= bx + bw and by <= y <= by + bh


def stop_likes(now: float) -> None:
    """No more likes from now on; the messages keep flowing."""
    global _stopped_at
    _stopped_at = now
    scene.sim.like_probability = 0.0


def set_cursor(kind: int) -> None:
    global _cursor
    if kind != _cursor:
        py5.cursor(kind)
        _cursor = kind


def draw_stop_button(hovered: bool) -> None:
    """The "Parar" label and a heart; greyed out once the likes have stopped."""
    x, y, w, h = STOP_BUTTON
    cx, cy = x + w / 2, y + h / 2
    enabled = _stopped_at is None
    colour = INK if enabled else MUTED
    py5.push_style()
    py5.rect_mode(py5.CORNER)
    py5.stroke(*colour)
    py5.stroke_weight(2)
    py5.fill(*(HOVER if hovered else PAPER))
    py5.rect(x, y, w, h, 8)
    py5.no_stroke()
    py5.fill(*colour)
    py5.text_size(18)
    py5.text_align(py5.LEFT, py5.CENTER)
    label_w = py5.text_width(STOP_LABEL)
    heart_w = 2.3 * HEART_SIZE
    gap = 8
    left = cx - (label_w + gap + heart_w) / 2
    py5.text(STOP_LABEL, left, cy - 1)
    draw_heart(left + label_w + gap + heart_w / 2, cy, HEART_SIZE, 255 if enabled else 90)
    py5.pop_style()



def draw() -> None:
    now = py5.millis() / 1000
    hovered = _stopped_at is None and in_button(py5.mouse_x, py5.mouse_y)
    set_cursor(py5.HAND if hovered else py5.ARROW)
    scene.advance(now)
    draw_frame(scene, now)
    draw_stop_button(hovered)


def mouse_pressed() -> None:
    if _stopped_at is None and in_button(py5.mouse_x, py5.mouse_y):
        stop_likes(py5.millis() / 1000)


if __name__ == "__main__":
    py5.run_sketch()
