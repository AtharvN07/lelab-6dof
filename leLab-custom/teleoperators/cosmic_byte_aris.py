"""
gamepad.py — Cosmic Byte Aris wireless controller support with robust macOS retry loop.
"""

from __future__ import annotations

import math
import sys
import time
from typing import Optional

import pygame

# Axis indices (confirmed for Cosmic Byte Aris / Xbox One Mac Layout)
AXIS_LEFT_X   = 0   # base
AXIS_LEFT_Y   = 1   # shoulder
AXIS_RIGHT_X  = 2   # elbow
AXIS_RIGHT_Y  = 3   # wrist
AXIS_TRIG_L   = 4   # rotate -
AXIS_TRIG_R   = 5   # rotate +

# Button indices
BTN_GRIP_CLOSE = 0
BTN_GRIP_OPEN  = 1
BTN_MODE_TOGGLE = 2

# Mapping: joint index -> (axis, sign)
JOINT_AXIS_MAP = {
    0: (AXIS_LEFT_X,   1.0),   # base
    1: (AXIS_LEFT_Y,  -1.0),   # shoulder
    2: (AXIS_RIGHT_X,  1.0),   # elbow
    3: (AXIS_RIGHT_Y, -1.0),   # wrist
}


class Gamepad:
    def __init__(self, deadzone: float = 0.12):
        self.deadzone = deadzone
        self.joystick = None
        self._initialized = False

    def init(self) -> bool:
        """Initialize pygame joystick subsystem with a robust macOS retry loop."""
        try:
            pygame.init()
            pygame.joystick.init()
        except Exception as e:
            print(f"[Gamepad] pygame init failed: {e}")
            return False

        # Loop for up to 3 seconds to catch the Mac USB handshake after camera setup delays
        print("[Gamepad] Scanning for controller connection...", flush=True)
        count = 0
        for _ in range(6):
            pygame.event.pump()
            count = pygame.joystick.get_count()
            if count > 0:
                break
            time.sleep(0.5)

        if count == 0:
            print("[Gamepad] No gamepad detected. Connect Cosmic Byte Aris and retry.")
            return False

        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        self._initialized = True
        print(f"[Gamepad] Connected: {self.joystick.get_name()}")
        print(f"[Gamepad] Axes: {self.joystick.get_numaxes()}, Buttons: {self.joystick.get_numbuttons()}")
        return True

    def _apply_deadzone(self, value: float) -> float:
        if abs(value) < self.deadzone:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        scaled = (abs(value) - self.deadzone) / (1.0 - self.deadzone)
        return sign * max(0.0, min(1.0, scaled))

    def read(self) -> Optional[dict]:
        if not self._initialized or self.joystick is None:
            return None

        pygame.event.pump()

        axes = [self._apply_deadzone(self.joystick.get_axis(i))
                for i in range(self.joystick.get_numaxes())]
        buttons = [self.joystick.get_button(i)
                   for i in range(self.joystick.get_numbuttons())]

        return {"axes": axes, "buttons": buttons}

    def close(self):
        if self.joystick:
            self.joystick.quit()
        pygame.quit()


def gamepad_to_action(state: dict, max_delta_rad: float, fine_mode: bool = False) -> list[float]:
    axes = state.get("axes", [])
    buttons = state.get("buttons", [])

    scale = 0.25 if fine_mode else 1.0
    action = [0.0] * 6

    # Joints 0-3 from analog sticks
    for joint_idx in range(4):
        axis_idx, sign = JOINT_AXIS_MAP[joint_idx]
        if axis_idx is not None and axis_idx < len(axes):
            action[joint_idx] = axes[axis_idx] * sign * max_delta_rad * scale

    # Joint 4 (wrist rotation) from triggers (fixed indexing syntax)
    if len(axes) > AXIS_TRIG_R and len(axes) > AXIS_TRIG_L:
        trig_r = (axes[AXIS_TRIG_R] + 1.0) / 2.0   
        trig_l = (axes[AXIS_TRIG_L] + 1.0) / 2.0   
        action[4] = (trig_r - trig_l) * max_delta_rad * scale

    # Joint 5 (gripper) from buttons (fixed indexing syntax)
    if len(buttons) > BTN_GRIP_CLOSE and buttons[BTN_GRIP_CLOSE]:
        action[5] = max_delta_rad * scale   
    elif len(buttons) > BTN_GRIP_OPEN and buttons[BTN_GRIP_OPEN]:
        action[5] = -max_delta_rad * scale  

    return action
