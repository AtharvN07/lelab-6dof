import pygame
import time

pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("ERROR: No controller detected.")
    raise SystemExit(1)

joy = pygame.joystick.Joystick(0)
joy.init()

print(f"\nController: {joy.get_name()}")
print(f"Axes: {joy.get_numaxes()} | Buttons: {joy.get_numbuttons()}")
print("\nMove each stick slowly and press every button.")
print("Press Ctrl+C to stop.\n")

last_axes = [0.0] * joy.get_numaxes()
last_buttons = [0] * joy.get_numbuttons()

try:
    while True:
        pygame.event.pump()

        for i in range(joy.get_numaxes()):
            value = joy.get_axis(i)
            if abs(value - last_axes[i]) > 0.08:
                print(f"AXIS {i}: {value:+.3f}")
                last_axes[i] = value

        for i in range(joy.get_numbuttons()):
            value = joy.get_button(i)
            if value != last_buttons[i]:
                print(f"BUTTON {i}: {'PRESSED' if value else 'RELEASED'}")
                last_buttons[i] = value

        time.sleep(0.02)

except KeyboardInterrupt:
    print("\nController test stopped.")
finally:
    pygame.quit()
