from pathlib import Path
import re

p = Path("lelab/arduino_robot.py")
s = p.read_text(encoding="utf-8")

pattern = re.compile(
    r"^    def start_gamepad_search\(self\) -> None:\n.*?(?=^    def |\Z)",
    re.MULTILINE | re.DOTALL,
)

replacement = '''    def start_gamepad_search(self) -> None:
        """Do not initialize Pygame from a background thread.

        Gamepad initialization is performed lazily by get_action(), in the
        same worker thread that polls the joystick during calibration.
        """
        # Intentionally do not launch _init_gamepad in another thread.
        return

'''

if not pattern.search(s):
    raise SystemExit("Could not find start_gamepad_search; file unchanged.")

s = pattern.sub(lambda _: replacement, s, count=1)
p.write_text(s, encoding="utf-8")
print("Disabled background Pygame initialization.")
