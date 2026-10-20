# LeLab + Custom 6-DOF Arduino Arm — Windows Setup

Complete, standalone guide. Everything you need is in this folder.

---

## 0. What you need

| Item | Notes |
|---|---|
| Arduino Mega 2560 | + PCA9685 servo board (I2C 0x40), 6 servos on ch 0-5 |
| Cosmic Byte ARIS controller | Windows/Android only — plug in the USB dongle |
| 2× USB cameras | top + wrist, plugged in before leLab starts |
| Python 3.12+ | `python --version` must be ≥ 3.12 |

---

## 1. Flash the Arduino firmware

Open `robot_controller_v8.ino` in Arduino IDE:
- **Tools → Board → Arduino Mega 2560**
- **Tools → Port →** the Arduino's COM port (e.g. `COM5`)
- Click **Upload**

The firmware speaks the `D:` protocol (delta degrees + gripper wire) over
115200 baud. Verify with the Arduino Serial Monitor at 115200 baud:
- type `PING` → expect `PONG`
- type `STATE` → expect `OK:STATE:90,90,90,90,90,0`
- type `D:5,0,0,0,0,0` → expect `OK:D:95,90,90,90,90,0`

---

## 2. Get LeLab

```powershell
git clone https://github.com/huggingface/leLab.git
cd leLab
git checkout -b custom6dof-arisa
```

---

## 3. Install LeLab

```powershell
pip install -e .
```

Windows needs a compiler for some wheels — install **Microsoft Visual C++ Build
Tools** first if a wheel fails to build.

---

## 4. Install the extra Python packages

```powershell
pip install pygame pyserial pygrabber
```

- `pygame` — reads the ARIS controller (XInput/DirectInput on Windows)
- `pyserial` — Arduino serial
- `pygrabber` — Windows camera names for leLab's camera picker

---

## 5. Install the Arduino-arm integration

Copy the 6 patched files over the ones in `lelab/`:

```powershell
copy arduino_robot.py     lelab\arduino_robot.py
copy arduino_driver.py    lelab\arduino_driver.py
copy teleoperate_patched.py lelab\teleoperate.py
copy record_patched.py    lelab\record.py
copy calibrate_fixed.py   lelab\calibrate.py
copy gamepad_custom.py   lelab\gamepad_custom.py
```

Then make leLab's package `__init__.py` export the new device classes so
lerobot's registry can find them. Open `lelab\lelab\__init__.py` and replace
its content with:

```python
"""LeLab — FastAPI + React web interface around the LeRobot framework."""

from lelab.__version__ import __version__

from lelab.arduino_robot import (
    ArduinoFollower,
    ArduinoFollowerConfig,
    ArduinoLeader,
    ArduinoLeaderConfig,
)

__all__ = [
    "__version__",
    "ArduinoFollower",
    "ArduinoFollowerConfig",
    "ArduinoLeader",
    "ArduinoLeaderConfig",
]
```

---

## 6. Verify the pieces

**a) Arduino reachable** (in PowerShell):
```powershell
python -c "import serial; s=serial.Serial('COM5',115200,timeout=1); s.write(b'PING\n'); print(s.readline())"
```
Expect `b'PONG'`. If you do not know the COM number, run:
```powershell
python -c "from serial.tools import list_ports; [print(p.device, p.vid, p.pid) for p in list_ports.comports()]"
```
Leave the port **blank** in leLab and it auto-detects the Arduino.

**b) ARIS controller visible to pygame**:
```powershell
python -c "import pygame; pygame.init(); pygame.joystick.init(); print(pygame.joystick.get_count()); [print(pygame.joystick.Joystick(i).get_name()) for i in range(pygame.joystick.get_count())]"
```
Expect `1` and your controller's name.

If it prints `0`: the dongle is not plugged in, or another program (e.g. the
standalone `aris_controller.py`) already holds it — close that program.

---

## 7. Run

```powershell
lelab
```

Open http://localhost:8000

**First time:** go to the robot you named (e.g. `custom6dof`) → **Calibration**
→ set the port (or leave it blank to auto-detect) → **Start** → move every joint
through its full range → **Complete Step**.

Calibration writes:
- `~/.cache/huggingface/lerobot/calibration/teleoperators/so_leader/<name>.json`
- `~/.cache/huggingface/lerobot/calibration/robots/so_follower/<name>.json`
- the robot record's `leader_config` / `follower_config`

**Then:** **Record** → the ARIS controller moves the arm, both cameras record.

---

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Calibration not found` / "missing a calibration" | Calibration never finished — redo step 7, click **Complete Step** |
| `Cannot find choice name for ArduinoFollowerConfig` | `lelab/__init__.py` not updated (step 5) |
| `could not open port COMx` | Wrong COM number, or the Arduino is on another port — run the list_ports command |
| Arm doesn't move, actions all zero | ARIS not detected by pygame — check step 6b; also make sure `aris_controller.py` is NOT running |
| `pygame sees 0 gamepads` | The ARIS dongle is not plugged in, or the controller is off — plug the dongle in and press a button on the controller |
| Camera 0 `read failed` | The browser preview still holds the camera — close the camera preview panel before recording |
| `No module named uvicorn` | `pip install uvicorn` |
| Video codec errors | Harmless; leLab falls back to another codec |

---

## 9. Files in this folder

| File | Replaces | Purpose |
|---|---|---|
| `arduino_robot.py` | new | `ArduinoFollower` + `ArduinoLeader` (LeRobot Robot/Teleoperator) |
| `arduino_driver.py` | new | serial driver for the `v8.ino` D: protocol, background reader thread |
| `teleoperate_patched.py` | `lelab/teleoperate.py` | teleop for the Arduino arm |
| `record_patched.py` | `lelab/record.py` | recording for the Arduino arm |
| `calibrate_fixed.py` | `lelab/calibrate.py` | calibration that saves JSON + robot record |
| `gamepad_custom.py` | new | standalone ARIS → Arduino bridge (for testing outside leLab) |
