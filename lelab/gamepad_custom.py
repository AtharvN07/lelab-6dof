"""ARIS (Cosmic Byte) -> Arduino D: protocol. All 6 joints mapped + HOME button.

Mapping confirmed by check_buttons.py on your Cosmic Byte ARIS (Xbox 360 layout):
  AXIS 0  left stick X   -> base        -> D d0
  AXIS 1  left stick Y   -> shoulder    -> D d1
  AXIS 2  right stick X  -> wrist rotate-> D d4
  AXIS 3  right stick Y  -> wrist bend  -> D d3
  AXIS 4  LT trigger     -> elbow down  -> D d2
  AXIS 5  RT trigger     -> elbow up    -> D d2
  BUTTON 0 (A)            -> gripper close -> D wire = 1  (90 deg)
  BUTTON 1 (B)            -> gripper open  -> D wire = -1 (0 deg)
  BUTTON 2 (X)            -> HOME (all servos to 90 / gripper open)
  BUTTON 3 (Y)            -> gripper toggle
  BUTTON 4/5 (LB/RB)      -> elbow down/up fallback
  BUTTON 11-14 (D-pad)    -> elbow down/up fallback

Triggers rest at -1.0 and reach +1.0 when pressed -> t = (axis + 1) / 2
Arduino v8.ino protocol: D:d0,d1,d2,d3,d4,wire   (NOT J,channel,angle)
"""
import time
import serial

from arduino_driver import find_arduino_port

try:
    import pygame
except ImportError:
    raise SystemExit("pip install pygame")

AXIS_BASE = 0
AXIS_SHOULDER = 1
AXIS_WRIST_ROTATION = 2
AXIS_WRIST_BEND = 3
AXIS_LT = 4
AXIS_RT = 5

BTN_GRIPPER_CLOSE = 0
BTN_GRIPPER_OPEN = 1
BTN_HOME = 2          # X button -> HOME
BTN_GRIPPER_TOGGLE = 3  # Y button -> gripper toggle
BTN_LB = 4
BTN_RB = 5
BTN_DPAD_UP = 11
BTN_DPAD_DOWN = 12
BTN_DPAD_LEFT = 13
BTN_DPAD_RIGHT = 14

RT_DEADZONE = 0.15   # for sticks
TRIG_THRESHOLD = 0.5  # for triggers (0..1 range)
SCALE = 5.0           # degrees per unit stick travel


port = find_arduino_port()
print(f"[Arduino] Port: {port}")
s = serial.Serial(port, 115200, timeout=1)
time.sleep(2)
s.read_all()  # drain READY
print("[Arduino] Connected")

pygame.init()
pygame.joystick.init()
deadline = time.monotonic() + 30
joystick = None
while time.monotonic() < deadline:
    pygame.event.pump()
    if pygame.joystick.get_count() > 0:
        joystick = pygame.joystick.Joystick(0)
        joystick.init()
        break
    time.sleep(0.25)

if joystick is None:
    raise SystemExit("[ARIS] No controller detected - connect USB dongle / Bluetooth")

print(f"[ARIS] Connected: {joystick.get_name()} - Axes: {joystick.get_numaxes()} Buttons: {joystick.get_numbuttons()}")

print(
    "\n  NOTE: this script holds the ARIS (and the Arduino serial port) exclusively."
    "\n  Stop it before using leLab's own teleoperation, or leLab cannot open the"
    "\n  controller and the arm will not move."
    "\n"
)
print("  LS-X=base  LS-Y=shoulder  RS-Y=wrist bend  RS-X=wrist rotate")
print("  LT=elbow down  RT=elbow up  A=gripper close  B=gripper open")
print("  X=HOME (all servos to 90)  Y=gripper toggle")
print("Ctrl+C to stop\n")


def dz(v, d=RT_DEADZONE):
    v = float(v)
    return 0.0 if abs(v) < d else v


def send_home():
    """Move every servo to 90 deg and open the gripper (firmware HOME command)."""
    s.write(b"HOME\n")
    resp = s.readline().decode().strip()
    print(f"[HOME] -> {resp}")


gripper_closed = False
prev_buttons = {}

try:
    while True:
        pygame.event.pump()
        axes = [joystick.get_axis(i) for i in range(joystick.get_numaxes())]
        buttons = [joystick.get_button(i) for i in range(joystick.get_numbuttons())]

        def axis(i):
            return dz(axes[i]) if i < len(axes) else 0.0

        def pressed(i):
            return i < len(buttons) and bool(buttons[i])

        def just_pressed(i):
            """True only on the frame the button transitions from up to down."""
            now = pressed(i)
            was = prev_buttons.get(i, False)
            prev_buttons[i] = now
            return now and not was

        def trigger(i):
            """Trigger axes rest at -1, press toward +1 -> 0..1"""
            if i >= len(axes):
                return 0.0
            return max(0.0, min(1.0, (float(axes[i]) + 1.0) / 2.0))

        # ---- X button: HOME all servos to 90 ----
        if just_pressed(BTN_HOME):
            send_home()
            continue

        # ---- Y button: toggle gripper ----
        if just_pressed(BTN_GRIPPER_TOGGLE):
            gripper_closed = not gripper_closed
            wire = 1 if gripper_closed else -1
            s.write(f"D:0,0,0,0,0,{wire}\n".encode())
            resp = s.readline().decode().strip()
            print(f"[Gripper] {'close' if gripper_closed else 'open'} -> {resp}")
            continue

        # --- arm joints from sticks ---
        base = axis(AXIS_BASE)
        shoulder = -axis(AXIS_SHOULDER)
        wrist_bend = -axis(AXIS_WRIST_BEND)
        wrist_rot = axis(AXIS_WRIST_ROTATION)

        # --- elbow from triggers (primary) or shoulder buttons (fallback) ---
        lt = trigger(AXIS_LT)
        rt = trigger(AXIS_RT)
        elbow = 0.0
        if rt > TRIG_THRESHOLD or pressed(BTN_RB) or pressed(BTN_DPAD_UP):
            elbow = 1.0
        elif lt > TRIG_THRESHOLD or pressed(BTN_LB) or pressed(BTN_DPAD_DOWN):
            elbow = -1.0

        # --- gripper from A/B ---
        wire = 0
        if pressed(BTN_GRIPPER_CLOSE):
            wire = 1     # close -> 90 deg
        elif pressed(BTN_GRIPPER_OPEN):
            wire = -1    # open  -> 0 deg

        d0 = int(base * SCALE)
        d1 = int(shoulder * SCALE)
        d2 = int(elbow * SCALE)
        d3 = int(wrist_bend * SCALE)
        d4 = int(wrist_rot * SCALE)

        if any((d0, d1, d2, d3, d4)) or wire != 0:
            cmd = f"D:{d0},{d1},{d2},{d3},{d4},{wire}\n"
            try:
                s.write(cmd.encode())
                s.flush()
                # Read until a complete line arrives, skipping partial/garbled
                # fragments (the board can reboot mid-transmission).
                resp = ""
                for _ in range(6):
                    raw = s.readline()
                    if not raw:
                        break
                    text = raw.decode("utf-8", "ignore").strip()
                    if "OK:" in text:
                        resp = text
                        break
                    resp = text
            except serial.SerialException as e:
                print(f"[ARIS] serial error: {e} - reconnecting")
                try:
                    s.close()
                except Exception:
                    pass
                s = serial.Serial(port, 115200, timeout=1)
                time.sleep(2)
                s.read_all()
                continue
            if resp:
                print(f"{cmd.strip()}  ->  {resp}")

        time.sleep(0.05)  # 20 Hz
except KeyboardInterrupt:
    pass
finally:
    try:
        s.write(b"HOME\n")
        s.readline()
    except Exception:
        pass
    s.close()
    pygame.quit()
    print("\n[ARIS] Stopped - HOME sent")
