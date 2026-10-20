from pathlib import Path

p = Path("lelab/arduino_robot.py")
s = p.read_text(encoding="utf-8")

old = '''            if getattr(self, "_pygame_ready", False):
                try:
                    pygame.joystick.quit()
                    pygame.joystick.init()
                except Exception:
                    pass
'''

if old not in s:
    raise SystemExit(
        "Expected joystick reset block not found. No changes made."
    )

s = s.replace(
    old,
    '''            # Do not quit/reinitialize the joystick subsystem on retries.
            # Doing so invalidates joystick objects that are already open.
''',
    1,
)

p.write_text(s, encoding="utf-8")
print("Removed repeated joystick subsystem reset.")
