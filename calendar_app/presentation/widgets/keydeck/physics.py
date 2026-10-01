# -*- coding: utf-8 -*-
"""Switch feel profiles and the spring that drives keycap travel.

Travel is normalised: 0 = key at rest, 1 = bottomed out, negative = hover lift.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

_SUBSTEP = 1.0 / 240.0
_REST_EPS_POS = 0.002
_REST_EPS_VEL = 0.02
MIN_TRAVEL = -0.12
LATCH_DEPTH = 0.5
HOVER_LIFT = -0.07


@dataclass(frozen=True, slots=True)
class SwitchProfile:
    switch_id: str
    stem_color: str
    stiffness: float
    damping: float
    bump_start: float = 0.0
    bump_end: float = 0.0
    bump_force: float = 0.0
    click_at: float = 0.0
    click_impulse: float = 0.0
    press_sound: str = ""
    release_sound: str = ""


SWITCH_PROFILES = {
    "linear": SwitchProfile("linear", "#e5484d", 900.0, 38.0, press_sound="soft_click"),
    "tactile": SwitchProfile(
        "tactile",
        "#a86b3c",
        950.0,
        36.0,
        bump_start=0.2,
        bump_end=0.42,
        bump_force=520.0,
        press_sound="mechanical",
    ),
    "clicky": SwitchProfile(
        "clicky",
        "#3b82f6",
        1000.0,
        34.0,
        bump_start=0.28,
        bump_end=0.48,
        bump_force=420.0,
        click_at=0.5,
        click_impulse=9.0,
        press_sound="crisp_click",
        release_sound="soft_click",
    ),
    "silent": SwitchProfile("silent", "#2b2f36", 820.0, 54.0),
}


def switch_profile(switch_id: object) -> SwitchProfile:
    return SWITCH_PROFILES.get(str(switch_id or ""), SWITCH_PROFILES["tactile"])


# 스위치 이벤트 (소리·촉감 타이밍용)
EVENT_BUMP = "bump"  # 택타일 리프에 걸림
EVENT_CLICK = "click"  # 클릭 재킷이 튐 (눌림)
EVENT_CLICK_UP = "click_up"  # 클릭 재킷 복귀 (뗄 때)
EVENT_BOTTOM = "bottom"  # 슬라이더가 바닥에 닿기 직전 (소리 지연 보정을 위해 약간 일찍)
EVENT_TOP = "top"  # 스템이 위 하우징에 부딪힘 (업스트로크)

FINGER_SPEED = 7.0  # 손가락이 닿는 순간의 초기 속도 (travel/s)
FINGER_FORCE = 1150.0  # 끝까지 누르는 손가락 힘 (travel/s²)
SPRING_RESISTANCE = 0.3  # 스위치 스프링이 누름에 저항하는 비율 (stiffness 배수)
BOTTOM_TRIGGER = 0.8
TOP_TRIGGER = 0.08
BOTTOM_BOUNCE = 0.16
TOP_BOUNCE = 0.1
_RELEASE_STIFFNESS = 2.2


class KeySpring:
    """Damped spring with tactile bump and clicky snap, integrated in fixed sub-steps.

    step() returns the switch events crossed during the step so sounds can be timed
    to what physically happens (actuation click, bottom-out, upstroke) instead of the
    mouse button.  impact holds the speed of the last bottom-out/top-out.
    """

    __slots__ = (
        "position",
        "velocity",
        "target",
        "profile",
        "impact",
        "_clicked",
        "_bumped",
        "_bottomed",
        "_topped",
        "_click_up",
    )

    def __init__(self, profile: SwitchProfile, position: float = 0.0):
        self.profile = profile
        self.position = float(position)
        self.velocity = 0.0
        self.target = float(position)
        self.impact = 0.0
        self._clicked = False
        self._bumped = False
        self._bottomed = False
        self._topped = True
        self._click_up = True

    @property
    def settled(self) -> bool:
        return (
            abs(self.position - self.target) < _REST_EPS_POS and abs(self.velocity) < _REST_EPS_VEL
        )

    def set_target(self, target: float) -> None:
        target = max(MIN_TRAVEL, min(1.0, float(target)))
        if target > self.target:
            self._clicked = self._bumped = self._bottomed = False
        elif target < self.target:
            self._topped = self._click_up = False
        self.target = target

    def press(self, depth: float = 1.0) -> None:
        """Finger contact: the cap starts moving at finger speed immediately."""
        self.set_target(depth)
        self.velocity = max(self.velocity, FINGER_SPEED)

    def snap(self, position: float) -> None:
        """Jump to a position without motion (reduce-motion mode)."""
        self.position = self.target = max(MIN_TRAVEL, min(1.0, float(position)))
        self.velocity = 0.0

    def step(self, dt: float) -> tuple[str, ...]:
        """Advance the spring and return the switch events crossed during this step."""
        profile = self.profile
        events: list[str] = []
        steps = max(1, int(math.ceil(max(0.0, dt) / _SUBSTEP)))
        sub_dt = max(0.0, dt) / steps
        # 끝까지 누르는 동안은 손가락 힘으로 바닥까지 밀어붙이고(실제처럼 바닥에 부딪힘),
        # 떼거나 반쯤 걸린 토글은 스위치 스프링이 목표 위치로 되돌린다.
        full_press = self.target >= 0.9
        release_stiffness = profile.stiffness * _RELEASE_STIFFNESS
        release_damping = profile.damping * 1.35
        press_damping = profile.damping * 0.35
        for _ in range(steps):
            if full_press:
                if self.position >= 1.0 and self.velocity <= 0.5:
                    # 바닥에 안착: 손가락이 누르고 있는 동안 움직이지 않는다.
                    self.position = 1.0
                    self.velocity = 0.0
                    continue
                accel = (
                    FINGER_FORCE
                    - profile.stiffness * SPRING_RESISTANCE * self.position
                    - press_damping * self.velocity
                )
            else:
                accel = (
                    release_stiffness * (self.target - self.position)
                    - release_damping * self.velocity
                )
            if (
                profile.bump_force
                and self.velocity > 0.0
                and profile.bump_start <= self.position <= profile.bump_end
            ):
                span = max(1e-3, profile.bump_end - profile.bump_start)
                phase = (self.position - profile.bump_start) / span
                accel -= profile.bump_force * math.sin(math.pi * phase)
            self.velocity += accel * sub_dt
            previous = self.position
            self.position += self.velocity * sub_dt
            if (
                profile.bump_force
                and not profile.click_at
                and not self._bumped
                and previous < profile.bump_start <= self.position
            ):
                self._bumped = True
                events.append(EVENT_BUMP)
            if (
                profile.click_at
                and not self._clicked
                and previous < profile.click_at <= self.position
            ):
                self._clicked = True
                events.append(EVENT_CLICK)
                self.velocity += profile.click_impulse
            if (
                profile.click_at
                and not self._click_up
                and previous > profile.click_at >= self.position
            ):
                self._click_up = True
                events.append(EVENT_CLICK_UP)
            if (
                not self._bottomed
                and self.target >= 0.9
                and previous < BOTTOM_TRIGGER <= self.position
            ):
                self._bottomed = True
                self.impact = max(0.0, self.velocity)
                events.append(EVENT_BOTTOM)
            if (
                not self._topped
                and self.target <= 0.1
                and previous > TOP_TRIGGER >= self.position
                and self.velocity < -1.0
            ):
                self._topped = True
                self.impact = -self.velocity
                events.append(EVENT_TOP)
            if self.position > 1.0:
                self.position = 1.0
                self.velocity = -abs(self.velocity) * BOTTOM_BOUNCE
            elif self.target <= 0.0 <= previous and self.position < 0.0:
                # 스템이 윗 하우징에 부딪혀 멈춘다: 레스트 위로 튀어나가지 않고 살짝 되튄다.
                self.position = 0.0
                self.velocity = abs(self.velocity) * TOP_BOUNCE
            elif self.position < MIN_TRAVEL:
                self.position = MIN_TRAVEL
                self.velocity = 0.0
        if self.settled or (full_press and self.position >= 1.0 and self.velocity == 0.0):
            self.position = self.target if not full_press else min(1.0, self.target)
            self.velocity = 0.0
        return tuple(events)


class TiltSpring:
    """Keycap rocking: off-center presses tilt the cap, release lets it wobble back."""

    __slots__ = ("x", "y", "vx", "vy", "tx", "ty")

    STIFFNESS = 700.0
    DAMPING = 16.0

    def __init__(self):
        self.x = self.y = self.vx = self.vy = self.tx = self.ty = 0.0

    @property
    def settled(self) -> bool:
        return (
            abs(self.x - self.tx) < 0.003
            and abs(self.y - self.ty) < 0.003
            and abs(self.vx) < 0.03
            and abs(self.vy) < 0.03
        )

    def set_target(self, x: float, y: float) -> None:
        self.tx = max(-1.0, min(1.0, float(x)))
        self.ty = max(-1.0, min(1.0, float(y)))

    def snap(self, x: float = 0.0, y: float = 0.0) -> None:
        self.x, self.y = float(x), float(y)
        self.tx, self.ty = self.x, self.y
        self.vx = self.vy = 0.0

    def step(self, dt: float) -> None:
        steps = max(1, int(math.ceil(max(0.0, dt) / _SUBSTEP)))
        sub_dt = max(0.0, dt) / steps
        for _ in range(steps):
            self.vx += (self.STIFFNESS * (self.tx - self.x) - self.DAMPING * self.vx) * sub_dt
            self.vy += (self.STIFFNESS * (self.ty - self.y) - self.DAMPING * self.vy) * sub_dt
            self.x += self.vx * sub_dt
            self.y += self.vy * sub_dt
        if self.settled:
            self.snap(self.tx, self.ty)


__all__ = [
    "BOTTOM_TRIGGER",
    "EVENT_BOTTOM",
    "EVENT_BUMP",
    "EVENT_CLICK",
    "EVENT_CLICK_UP",
    "EVENT_TOP",
    "FINGER_SPEED",
    "HOVER_LIFT",
    "LATCH_DEPTH",
    "MIN_TRAVEL",
    "SWITCH_PROFILES",
    "KeySpring",
    "SwitchProfile",
    "TiltSpring",
    "switch_profile",
]
