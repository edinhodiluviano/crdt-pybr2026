"""Animation 4: animation 3, but the likes stop after LIKES_STOP_SECONDS.

For the first LIKES_STOP_SECONDS seconds this is animation 3: every second
each phone likes some user with probability LIKE_PROBABILITY and sends its
state to each other phone with probability MESSAGE_PROBABILITY. Then the
likes stop while the messages keep flowing, so the replicas drift together
until they all agree.

Run:  uv run animation4.py
"""

from __future__ import annotations

import random

import py5

from scene import AMBER, HEIGHT, MUTED, WIDTH, Scene, draw_frame

PHONE_IDS = ["Usuária-A", "Usuária-B", "Usuária-C", "Usuária-D"]
LIKE_PROBABILITY = 0.5
MESSAGE_PROBABILITY = 0.25
TICK_SECONDS = 1.0
FLIGHT_SECONDS = 1.0
LIKES_STOP_SECONDS = 20.0
SEED: int | None = None  # set an int for a repeatable run

scene: Scene


def settings() -> None:
    py5.size(WIDTH, HEIGHT)


def setup() -> None:
    global scene
    py5.window_title("CRDT: G-Counter likes, then only messages")
    py5.frame_rate(60)
    scene = Scene(
        PHONE_IDS,
        random.Random(SEED),
        title="G-Counter likes, then only messages",
        subtitle=(
            f"for {LIKES_STOP_SECONDS:.0f} s each phone likes someone every second with "
            f"p = {LIKE_PROBABILITY:.0%}. Messages to each other phone keep going with "
            f"p = {MESSAGE_PROBABILITY:.0%} per second."
        ),
        like_probability=LIKE_PROBABILITY,
        message_probability=MESSAGE_PROBABILITY,
        tick_seconds=TICK_SECONDS,
        flight_seconds=FLIGHT_SECONDS,
    )


def draw_phase(now: float) -> None:
    """Top-right note: countdown to the stop, then a reminder that likes are off."""
    py5.push_style()
    py5.text_align(py5.RIGHT, py5.TOP)
    py5.text_size(18)
    if now < LIKES_STOP_SECONDS:
        py5.fill(*MUTED)
        py5.text(f"likes stop in {LIKES_STOP_SECONDS - now:4.1f} s", WIDTH - 40, 36)
    else:
        py5.fill(*AMBER)
        py5.text(f"likes stopped at {LIKES_STOP_SECONDS:.0f} s, only messages now", WIDTH - 40, 36)
    py5.pop_style()


def draw() -> None:
    now = py5.millis() / 1000
    if now >= LIKES_STOP_SECONDS:
        scene.sim.like_probability = 0.0
    scene.advance(now)
    draw_frame(scene, now)
    draw_phase(now)


if __name__ == "__main__":
    py5.run_sketch()
