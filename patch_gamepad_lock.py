from pathlib import Path

p = Path("lelab/arduino_robot.py")
s = p.read_text(encoding="utf-8")

old_init = '''        self._gamepad = None
        self._gamepad_backend = None
        self._pygame_ready = False
'''

new_init = '''        self._gamepad = None
        self._gamepad_backend = None
        self._pygame_ready = False
        self._gamepad_lock = threading.RLock()
'''

if old_init not in s:
    raise SystemExit("Could not find gamepad initialization block; no changes made.")

if "self._gamepad_lock = threading.RLock()" not in s:
    s = s.replace(old_init, new_init, 1)

old_read = '''            if self._gamepad_backend == "inputs":
                axes, buttons = self._read_inputs_state()
            else:
                import pygame

                pygame.event.pump()
                axes = [self._gamepad.get_axis(i) for i in range(self._gamepad.get_numaxes())]
                buttons = [self._gamepad.get_button(i) for i in range(self._gamepad.get_numbuttons())]
'''

new_read = '''            with self._gamepad_lock:
                if self._gamepad is None:
                    return action

                if self._gamepad_backend == "inputs":
                    axes, buttons = self._read_inputs_state()
                else:
                    import pygame

                    pygame.event.pump()
                    axes = [
                        self._gamepad.get_axis(i)
                        for i in range(self._gamepad.get_numaxes())
                    ]
                    buttons = [
                        self._gamepad.get_button(i)
                        for i in range(self._gamepad.get_numbuttons())
                    ]
'''

if old_read not in s:
    raise SystemExit("Could not find joystick read block; no changes made.")

s = s.replace(old_read, new_read, 1)
p.write_text(s, encoding="utf-8")
print("Added gamepad lock and protected joystick reads.")
