"""Animation 2: the automatic version of animation 1.

Every second each phone:

1. likes some user, itself included, with probability LIKE_PROBABILITY. The
   like increments that user's G-Counter at the liker's own replica slot;
2. sends its whole state, one G-Counter per user, to each other phone with
   probability MESSAGE_PROBABILITY. The envelope takes FLIGHT_SECONDS to
   arrive and the receiver merges it on arrival (maximum per replica slot).

Beside each phone, one line per user shows how many likes that user has, as
far as this replica knows. A heart pops when a like happens, and the lines
that change on a merge flash green.

Run:  uv run animation2.py
"""

from __future__ import annotations

import random

import py5

from scene import HEIGHT, WIDTH, Scene, draw_frame

PHONE_IDS = ["Usuária-A", "Usuária-B"]
LIKE_PROBABILITY = 0.5
MESSAGE_PROBABILITY = 0.25
TICK_SECONDS = 1.0
FLIGHT_SECONDS = 1.0
SEED: int | None = None  # set an int for a repeatable run

scene: Scene


def settings() -> None:
    py5.size(WIDTH, HEIGHT)


def setup() -> None:
    global scene
    py5.window_title("CRDT: G-Counter likes")
    py5.frame_rate(60)
    scene = Scene(
        PHONE_IDS,
        random.Random(SEED),
        title="G-Counter likes",
        subtitle=(
            f"every second, each phone likes someone with p = {LIKE_PROBABILITY:.0%} and "
            f"sends its state to each other phone with p = {MESSAGE_PROBABILITY:.0%}. "
            "A merge keeps the maximum per replica."
        ),
        like_probability=LIKE_PROBABILITY,
        message_probability=MESSAGE_PROBABILITY,
        tick_seconds=TICK_SECONDS,
        flight_seconds=FLIGHT_SECONDS,
    )


def draw() -> None:
    now = py5.millis() / 1000
    scene.advance(now)
    draw_frame(scene, now)


if __name__ == "__main__":
    py5.run_sketch()
