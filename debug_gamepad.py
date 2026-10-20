from pathlib import Path

p = Path("lelab/calibrate.py")
s = p.read_text(encoding="utf-8")

old = '''                    print("[CALIBRATION GAMEPAD]", action, flush=True)
                    self._last_gamepad_debug = now
'''

new = '''                    gp = leader._gamepad
                    raw_axes = []
                    raw_buttons = []
                    if gp is not None:
                        try:
                            import pygame
                            pygame.event.pump()
                            raw_axes = [
                                round(gp.get_axis(i), 3)
                                for i in range(gp.get_numaxes())
                            ]
                            raw_buttons = [
                                gp.get_button(i)
                                for i in range(gp.get_numbuttons())
                            ]
                        except Exception as exc:
                            print("[RAW INPUT ERROR]", repr(exc), flush=True)
                    print(
                        "[CALIBRATION DEBUG]",
                        "actions=", action,
                        "raw_axes=", raw_axes,
                        "raw_buttons=", raw_buttons,
                        flush=True,
                    )
                    self._last_gamepad_debug = now
'''

if s.count(old) != 1:
    raise SystemExit("Expected debug print not found exactly once; file unchanged.")

p.write_text(s.replace(old, new, 1), encoding="utf-8")
print("Raw controller diagnostics added.")
