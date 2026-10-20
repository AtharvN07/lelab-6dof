@echo off
REM ---------------------------------------------------------------------------
REM  LeLab + custom 6-DOF Arduino arm - Windows installer
REM  Run this from the folder holding these files, in a terminal that has the
REM  repo checked out next to it (see WINDOWS_SETUP.md step 2).
REM ---------------------------------------------------------------------------
setlocal

if "%LELAB_REPO%"=="" set LELAB_REPO=leLab
if not exist "%LELAB_REPO%\lelab\arduino_robot.py" (
  echo.
  echo   Could not find "%LELAB_REPO%\lelab\".
  echo   Clone leLab first:  git clone https://github.com/huggingface/leLab.git
  echo   then re-run this script from the folder that contains it.
  echo.
  pause
  exit /b 1
)

echo.
echo == Installing the Arduino-arm integration into %LELAB_REPO% ==
copy /Y arduino_robot.py      "%LELAB_REPO%\lelab\arduino_robot.py"
copy /Y arduino_driver.py     "%LELAB_REPO%\lelab\arduino_driver.py"
copy /Y teleoperate_patched.py "%LELAB_REPO%\lelab\teleoperate.py"
copy /Y record_patched.py     "%LELAB_REPO%\lelab\record.py"
copy /Y calibrate_fixed.py    "%LELAB_REPO%\lelab\calibrate.py"
copy /Y gamepad_custom.py    "%LELAB_REPO%\lelab\gamepad_custom.py"

echo.
echo == Updating lelab\lelab\__init__.py so lerobot can find the device classes ==
> "%LELAB_REPO%\lelab\__init__.py" (
  echo """LeLab - FastAPI + React web interface around the LeRobot framework."""
  echo.
  echo from lelab.__version__ import __version__
  echo.
  echo from lelab.arduino_robot import (
  echo     ArduinoFollower,
  echo     ArduinoFollowerConfig,
  echo     ArduinoLeader,
  echo     ArduinoLeaderConfig,
  echo ^)
  echo.
  echo __all__ = [
  echo     "__version__",
  echo     "ArduinoFollower",
  echo     "ArduinoFollowerConfig",
  echo     "ArduinoLeader",
  echo     "ArduinoLeaderConfig",
  echo ]
)

echo.
echo == Installing extra Python packages ==
python -m pip install --upgrade pip
python -m pip install pygame pyserial pygrabber
python -m pip install -e "%LELAB_REPO%"

echo.
echo == Verifying the Arduino serial port ==
python -c "from serial.tools import list_ports; ps=list(list_ports.comports()); print('serial ports:', [(p.device, p.vid) for p in ps])"

echo.
echo == Verifying the gamepad ==
python -c "import pygame; pygame.init(); pygame.joystick.init(); n=pygame.joystick.get_count(); print('gamepads:', n); [print('  ', pygame.joystick.Joystick(i).get_name()) for i in range(n)]"

echo.
echo == Done. Next: ==
echo    lelab
echo    then open http://localhost:8000
echo.
pause
