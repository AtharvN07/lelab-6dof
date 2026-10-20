import time
import pygame

pygame.init()
pygame.joystick.init()

print("Controllers found:", pygame.joystick.get_count())

if pygame.joystick.get_count() == 0:
    raise SystemExit("No controller detected by pygame.")

pad = pygame.joystick.Joystick(0)
pad.init()

print("Controller:", pad.get_name())
print("Axes:", pad.get_numaxes(), "Buttons:", pad.get_numbuttons())
print("Move each stick and press buttons. Ctrl+C to exit.")

try:
    while True:
        pygame.event.pump()
        axes = [round(pad.get_axis(i), 3) for i in range(pad.get_numaxes())]
        buttons = [pad.get_button(i) for i in range(pad.get_numbuttons())]
        print("AXES:", axes, "BUTTONS:", buttons, flush=True)
        time.sleep(0.25)
except KeyboardInterrupt:
    pass
finally:
    pygame.quit()
