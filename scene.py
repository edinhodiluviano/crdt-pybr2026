"""Shared drawing and bookkeeping for the phone animations.

py5 runs in module mode, so the entry points (settings, setup, draw and the
mouse events) live in each ``animationN.py``. Everything they share is here:
the phones on a circle, the likes list beside each phone, envelopes in flight,
the short-lived effects (heart pops, flashes, pulses), hit testing for the
manual animation, and the frame drawing itself.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import py5

from simulation import Delivery, Like, Message, Simulation

WIDTH, HEIGHT = 1200, 800

INK = (25, 25, 25)
PAPER = (255, 255, 255)
MUTED = (120, 120, 120)
HOVER = (236, 236, 236)
ENVELOPE = (255, 204, 0)
HEART = (229, 57, 70)
MERGE = (40, 160, 70)
AMBER = (205, 125, 0)

TEXT_SIZE = 22
LINE_HEIGHT = 30
NUMBER_COLUMN = 44
LANE_OFFSET = 18  # A->B and B->A envelopes travel on separate lanes
ENVELOPE_W, ENVELOPE_H = 48, 32
HEART_SECONDS = 0.9
FLASH_SECONDS = 0.8
PULSE_SECONDS = 0.6


@dataclass(frozen=True)
class Spot:
    """Where a phone sits and which side its likes list goes on."""

    x: float
    y: float
    side: int  # -1: list on the left of the phone, +1: on its right


@dataclass
class HeartPop:
    x: float
    y: float
    born: float


@dataclass
class Flash:
    colour: tuple[int, int, int]
    born: float


@dataclass
class Pulse:
    phone: str
    colour: tuple[int, int, int]
    born: float


def phone_height(n: int) -> float:
    """Two phones get big icons at the sides; a fuller ring gets smaller ones."""
    return 200 if n <= 2 else 150


def layout(phone_ids: list[str]) -> dict[str, Spot]:
    """Phones equally spaced on a circle, the first one on the left."""
    n = len(phone_ids)
    cx, cy = WIDTH / 2, HEIGHT / 2 + 10
    radius = 300 if n <= 2 else 210
    spots = {}
    for i, pid in enumerate(phone_ids):
        angle = math.pi + 2 * math.pi * i / n
        ux, uy = math.cos(angle), math.sin(angle)
        side = -1 if ux < -1e-9 else 1
        spots[pid] = Spot(cx + radius * ux, cy + radius * uy, side)
    return spots


def blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float):
    t = min(max(t, 0.0), 1.0)
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Scene:
    """The simulation plus the short-lived visual effects it triggers.

    With both probabilities at zero nothing happens on its own; the manual
    animation then drives it through :meth:`like` and :meth:`send`.
    """

    def __init__(
        self,
        phone_ids: list[str],
        rng: random.Random,
        *,
        title: str,
        like_probability: float = 0.0,
        message_probability: float = 0.0,
        tick_seconds: float = 1.0,
        flight_seconds: float = 1.0,
    ) -> None:
        self.title = title
        self.sim = Simulation(
            phone_ids,
            like_probability=like_probability,
            message_probability=message_probability,
            flight_time=flight_seconds,
            rng=rng,
        )
        self.tick_seconds = tick_seconds
        self.next_tick = tick_seconds
        self.spots = layout(phone_ids)
        self.phone_h = phone_height(len(phone_ids))
        self.phone_w = self.phone_h * 0.55
        self.hearts: list[HeartPop] = []
        self.flashes: dict[tuple[str, str], Flash] = {}
        self.pulses: list[Pulse] = []
        self.hover_line: tuple[str, str] | None = None  # (phone, liked user)
        self.hover_phone: str | None = None
        py5.text_size(TEXT_SIZE)
        self.id_column = max(py5.text_width(pid) for pid in phone_ids) + 16

    def advance(self, now: float) -> None:
        while now >= self.next_tick:
            for event in self.sim.tick(self.next_tick):
                if isinstance(event, Like):
                    self.on_like(event)
            self.next_tick += self.tick_seconds
        for delivery in self.sim.deliver(now):
            self.on_delivery(delivery)
        self.hearts = [h for h in self.hearts if now - h.born < HEART_SECONDS]
        self.flashes = {
            k: f for k, f in self.flashes.items() if now - f.born < FLASH_SECONDS
        }
        self.pulses = [p for p in self.pulses if now - p.born < PULSE_SECONDS]

    # --- manual actions ------------------------------------------------

    def like(self, phone: str, key: str, now: float) -> None:
        """``phone`` likes user ``key``."""
        self.on_like(self.sim.like(phone, key, now))

    def send(self, phone: str, now: float) -> None:
        """``phone`` sends its state to every other phone."""
        for other in self.sim.phone_ids:
            if other != phone:
                self.sim.send(phone, other, now)

    # --- effects --------------------------------------------------------

    def on_like(self, like: Like) -> None:
        x, y = self.heart_anchor(like.liker, like.target)
        self.hearts.append(HeartPop(x, y, like.at))
        self.flashes[(like.liker, like.target)] = Flash(HEART, like.at)

    def on_delivery(self, delivery: Delivery) -> None:
        receiver = delivery.message.receiver
        for key in delivery.changed:
            self.flashes[(receiver, key)] = Flash(MERGE, delivery.at)
        colour = MERGE if delivery.changed else MUTED
        self.pulses.append(Pulse(receiver, colour, delivery.at))

    # --- geometry of the likes list beside a phone ---------------------

    def anchor_x(self, phone: str) -> float:
        spot = self.spots[phone]
        return spot.x + spot.side * (self.phone_w / 2 + 26)

    def line_y(self, phone: str, key: str) -> float:
        ids = self.sim.phone_ids
        return self.spots[phone].y + (ids.index(key) - (len(ids) - 1) / 2) * LINE_HEIGHT

    def line_box(self, phone: str, key: str) -> tuple[float, float, float, float]:
        """Bounding box (x0, y0, x1, y1) of the line for ``key`` beside ``phone``."""
        ax = self.anchor_x(phone)
        y = self.line_y(phone, key)
        width = self.id_column + NUMBER_COLUMN
        if self.spots[phone].side < 0:
            x0, x1 = ax - width, ax + 6
        else:
            x0, x1 = ax - 6, ax + width
        return x0, y - LINE_HEIGHT / 2, x1, y + LINE_HEIGHT / 2

    def heart_anchor(self, phone: str, key: str) -> tuple[float, float]:
        """Just past the outer end of the line for ``key`` beside ``phone``."""
        ax = self.anchor_x(phone)
        reach = self.id_column + NUMBER_COLUMN + 12
        x = ax - reach if self.spots[phone].side < 0 else ax + reach
        return x, self.line_y(phone, key)

    def envelope_position(self, message: Message, now: float) -> tuple[float, float]:
        s, r = self.spots[message.sender], self.spots[message.receiver]
        dx, dy = r.x - s.x, r.y - s.y
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        nx, ny = -uy, ux  # right-hand normal: separates the two directions
        edge = self.phone_w / 2 + 12
        sx, sy = s.x + ux * edge, s.y + uy * edge
        t = message.progress(now)
        t = t * t * (3 - 2 * t)  # ease in and out
        return sx + (r.x - sx) * t + nx * LANE_OFFSET, sy + (r.y - sy) * t + ny * LANE_OFFSET

    # --- hit testing ----------------------------------------------------

    def hit_line(self, mx: float, my: float) -> tuple[str, str] | None:
        """The (phone, user) line under the point, if any."""
        for phone in self.sim.phone_ids:
            for key in self.sim.phone_ids:
                x0, y0, x1, y1 = self.line_box(phone, key)
                if x0 <= mx <= x1 and y0 <= my <= y1:
                    return phone, key
        return None

    def hit_phone(self, mx: float, my: float) -> str | None:
        """The phone whose body is under the point, if any."""
        for pid, spot in self.spots.items():
            if abs(mx - spot.x) <= self.phone_w / 2 and abs(my - spot.y) <= self.phone_h / 2:
                return pid
        return None


# --- drawing -----------------------------------------------------------


def draw_frame(scene: Scene, now: float) -> None:
    py5.background(*PAPER)
    draw_header(scene.title)
    for pid in scene.sim.phone_ids:
        draw_likes(scene, pid, now)
    for message in scene.sim.in_flight:
        draw_envelope(*scene.envelope_position(message, now))
    for pid, spot in scene.spots.items():
        draw_phone(spot.x, spot.y, scene.phone_h, pid, hovered=pid == scene.hover_phone)
    for pulse in scene.pulses:
        spot = scene.spots[pulse.phone]
        draw_pulse(spot, scene.phone_h, pulse.colour, (now - pulse.born) / PULSE_SECONDS)
    for heart in scene.hearts:
        draw_heart_pop(heart, (now - heart.born) / HEART_SECONDS)
    draw_footer(scene, now)


def draw_header(title: str) -> None:
    py5.push_style()
    py5.text_align(py5.CENTER, py5.TOP)
    py5.fill(*INK)
    py5.text_size(28)
    py5.text(title, WIDTH / 2, 30)
    py5.pop_style()


def draw_footer(scene: Scene, now: float) -> None:
    converged = scene.sim.converged()
    py5.push_style()
    py5.text_align(py5.CENTER, py5.BOTTOM)
    py5.text_size(18)
    py5.fill(*MUTED)
    py5.text(
        f"t = {now:5.1f} s     messages in flight: {len(scene.sim.in_flight)}",
        WIDTH / 2,
        HEIGHT - 52,
    )
    py5.fill(*(MERGE if converged else AMBER))
    py5.text("all replicas agree" if converged else "replicas differ", WIDTH / 2, HEIGHT - 26)
    py5.pop_style()


def draw_likes(scene: Scene, phone: str, now: float) -> None:
    """One line per user: the name and how many likes it has, as known here."""
    spot = scene.spots[phone]
    ax = scene.anchor_x(phone)
    py5.push_style()
    py5.text_size(TEXT_SIZE)
    for key in scene.sim.phone_ids:
        y = scene.line_y(phone, key)
        if scene.hover_line == (phone, key):
            x0, y0, x1, y1 = scene.line_box(phone, key)
            py5.no_stroke()
            py5.fill(*HOVER)
            py5.rect(x0 - 8, y0, x1 - x0 + 16, y1 - y0, 8)
        colour = INK
        if flash := scene.flashes.get((phone, key)):
            colour = blend(flash.colour, INK, (now - flash.born) / FLASH_SECONDS)
        value = str(scene.sim.phones[phone].likes[key].value())
        if spot.side < 0:
            py5.text_align(py5.RIGHT, py5.CENTER)
            py5.fill(*MUTED)
            py5.text(key, ax - NUMBER_COLUMN, y)
            py5.fill(*colour)
            py5.text(value, ax, y)
        else:
            py5.text_align(py5.LEFT, py5.CENTER)
            py5.fill(*MUTED)
            py5.text(key, ax, y)
            py5.fill(*colour)
            py5.text(value, ax + scene.id_column, y)
    py5.pop_style()


def draw_phone(x: float, y: float, h: float, label: str, hovered: bool = False) -> None:
    """A black phone outline in the style of mobile.png, with its id on screen."""
    w, sw, r = h * 0.55, h * 0.043, h * 0.1
    py5.push_style()
    py5.rect_mode(py5.CENTER)
    py5.stroke(*INK)
    py5.stroke_weight(sw)
    py5.fill(*(HOVER if hovered else PAPER))
    py5.rect(x, y, w - sw, h - sw, r)
    py5.no_stroke()
    py5.fill(*INK)
    py5.rect(x, y - h / 2 + h * 0.11, w * 0.32, h * 0.04, h * 0.02)  # speaker
    py5.circle(x, y + h / 2 - h * 0.13, h * 0.085)  # home button
    py5.fill(*MUTED)
    py5.text_size(h * 0.08)  # 16 px on a 200 px phone
    py5.text_align(py5.CENTER, py5.CENTER)
    py5.text(label, x, y - h / 2 + h * 0.27)
    py5.pop_style()


def draw_envelope(x: float, y: float) -> None:
    w, h = ENVELOPE_W, ENVELOPE_H
    py5.push_style()
    py5.rect_mode(py5.CENTER)
    py5.stroke(*INK)
    py5.stroke_weight(2)
    py5.fill(*ENVELOPE)
    py5.rect(x, y, w, h, 3)
    py5.line(x - w / 2, y - h / 2, x, y + h * 0.15)
    py5.line(x + w / 2, y - h / 2, x, y + h * 0.15)
    py5.pop_style()


def draw_pulse(spot: Spot, h: float, colour: tuple[int, int, int], t: float) -> None:
    """An expanding, fading ring around a phone that just merged a message."""
    grow = 12 + 40 * t
    py5.push_style()
    py5.rect_mode(py5.CENTER)
    py5.no_fill()
    py5.stroke(*colour, 220 * (1 - t))
    py5.stroke_weight(4)
    py5.rect(spot.x, spot.y, h * 0.55 + grow, h + grow, h * 0.1 + grow / 2)
    py5.pop_style()


def draw_heart_pop(heart: HeartPop, t: float) -> None:
    size = 10 + 4 * math.sin(math.pi * min(t * 2, 1))
    draw_heart(heart.x, heart.y - 14 * t, size, 255 * (1 - t * t))


def draw_heart(x: float, y: float, s: float, alpha: float) -> None:
    py5.push_style()
    py5.no_stroke()
    py5.fill(*HEART, alpha)
    py5.begin_shape()
    py5.vertex(x, y + s)
    py5.bezier_vertex(x - 2 * s, y - 0.5 * s, x - s, y - 1.6 * s, x, y - 0.4 * s)
    py5.bezier_vertex(x + s, y - 1.6 * s, x + 2 * s, y - 0.5 * s, x, y + s)
    py5.end_shape(py5.CLOSE)
    py5.pop_style()
