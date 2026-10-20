from pathlib import Path
import re

p = Path("lelab/calibrate.py")
s = p.read_text(encoding="utf-8")

pattern = re.compile(
    r"^    def _calibration_gamepad_loop\(self\):.*?(?=^    def |\Z)",
    re.MULTILINE | re.DOTALL,
)

replacement = '''    def _calibration_gamepad_loop(self):
        """Read gamepad, log raw inputs and commands, and move slowly."""
        leader = self.gamepad_leader
        driver = self.device

        if leader is None or driver is None:
            logger.error("Calibration gamepad/Arduino is not initialized")
            return

        import pygame

        axis_names = {
            0: "LEFT_X / BASE",
            1: "LEFT_Y / SHOULDER",
            2: "RIGHT_X / ROTATE",
            3: "RIGHT_Y / WRIST",
            4: "LEFT_TRIGGER / ELBOW_DOWN",
            5: "RIGHT_TRIGGER / ELBOW_UP",
        }
        button_names = {
            0: "A / GRIPPER_CLOSE",
            1: "B / GRIPPER_OPEN",
            2: "X",
            3: "Y",
            4: "L1 / ELBOW_DOWN",
            5: "R1 / ELBOW_UP",
        }

        logger.info("DETAILED GAMEPAD DEBUG ACTIVE")
        logger.info("Move only one control at a time; watch the terminal.")

        last_debug = 0.0

        while not self._gamepad_stop.is_set() and not self.stop_calibration:
            try:
                action = leader.get_action()
                gp = leader._gamepad
                axes = []
                buttons = []
                pressed_names = []

                if gp is not None and leader._gamepad_backend == "pygame":
                    # get_action() already pumps the pygame event queue.
                    axes = [
                        round(float(gp.get_axis(i)), 3)
                        for i in range(gp.get_numaxes())
                    ]
                    buttons = [
                        int(gp.get_button(i))
                        for i in range(gp.get_numbuttons())
                    ]
                    pressed_names = [
                        button_names.get(i, f"BUTTON_{i}")
                        for i, value in enumerate(buttons)
                        if value
                    ]

                deltas = []
                for motor in CONTINUOUS_MOTORS:
                    value = float(action.get(f"{motor}.pos", 0.0))
                    if abs(value) < 0.15:
                        deltas.append(0)
                    else:
                        deltas.append(1 if value > 0 else -1)

                wire = getattr(driver, "gripper_wire", 0)
                driver.send_delta(deltas, wire)

                now = time.monotonic()
                if now - last_debug >= 1.0:
                    active_axes = {
                        axis_names.get(i, f"AXIS_{i}"): value
                        for i, value in enumerate(axes)
                        if abs(value) > 0.15
                    }
                    print(
                        "\\\\n[CALIBRATION GAMEPAD DEBUG]"
                        f"\\\\n  backend       = {leader._gamepad_backend}"
                        f"\\\\n  device        = {gp.get_name() if gp else None}"
                        f"\\\\n  raw_axes      = {axes}"
                        f"\\\\n  active_axes   = {active_axes}"
                        f"\\\\n  raw_buttons   = {buttons}"
                        f"\\\\n  pressed       = {pressed_names}"
                        f"\\\\n  mapped_action = {action}"
                        f"\\\\n  sent_deltas   = {deltas} "
                        "(base, shoulder, elbow, wrist, rotate)"
                        f"\\\\n  gripper_wire  = {wire}"
                        "\\\\n----------------------------------------",
                        flush=True,
                    )
                    last_debug = now

            except Exception:
                logger.exception("Calibration gamepad control failed")
                time.sleep(0.2)

            time.sleep(0.12)

        logger.info("Calibration gamepad control stopped")
'''

if not pattern.search(s):
    raise SystemExit(
        "Could not find _calibration_gamepad_loop. File unchanged."
    )

s = pattern.sub(lambda _: replacement + "\\n", s, count=1)
p.write_text(s, encoding="utf-8")
print("Installed detailed calibration gamepad debug.")
