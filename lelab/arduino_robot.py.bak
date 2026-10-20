"""
LeRobot-compatible Robot / Teleoperator backed by the custom 6-DOF Arduino arm.

The arm has six servos on a PCA9685 driven by an Arduino Mega running
robot_controller_v8.ino (D: delta protocol). The servos have no encoder
feedback, so the Arduino owns the position state: the host only ever sends
*deltas* (the D: command) or absolute angles (the A: command).

Joint order (identical to the firmware):
    0 base, 1 shoulder, 2 elbow, 3 wrist, 4 rotate, 5 gripper
"""

import os
import threading
import time
from dataclasses import dataclass, field

import numpy as np

from lerobot.cameras import CameraConfig, make_cameras_from_configs
from lerobot.robots.config import RobotConfig
from lerobot.robots.robot import Robot
from lerobot.teleoperators.config import TeleoperatorConfig
from lerobot.teleoperators.teleoperator import Teleoperator

from .arduino_driver import ArduinoRobotDriver

# Joint names in firmware order.
MOTOR_NAMES = ["base", "shoulder", "elbow", "wrist", "rotate", "gripper"]

# The gripper is a binary open/close servo (0 deg = open, 90 deg = closed) and
# is not a free-running joint, so it is excluded from the continuous position
# features and handled through the firmware's `wire` convention instead.
CONTINUOUS_MOTORS = MOTOR_NAMES[:5]

# Axis / button layout of the Cosmic Byte ARIS (Xbox 360 layout).
AXIS_BASE = 0
AXIS_SHOULDER = 1
AXIS_RIGHT_X = 2
AXIS_RIGHT_Y = 3
AXIS_LT = 4
AXIS_RT = 5

BTN_GRIPPER_CLOSE = 0
BTN_GRIPPER_OPEN = 1
BTN_ELBOW_DOWN = 5
BTN_ELBOW_UP = 6

STICK_DEADZONE = 0.15
TRIGGER_THRESHOLD = 0.5
# Degrees per unit of stick travel, per control frame.
DELTA_SCALE = 3.0


@RobotConfig.register_subclass("arduino_follower")
@dataclass
class ArduinoFollowerConfig(RobotConfig):
    """Config for the custom Arduino 6-DOF follower arm.

    Leave `port` empty to auto-detect the Arduino (recommended - the device
    name changes between Windows COM ports, Linux /dev/ttyUSB* and macOS
    /dev/cu.usbmodem*).
    """

    port: str = ""
    disable_torque_on_disconnect: bool = True
    max_relative_target: float | dict[str, float] | None = None
    cameras: dict[str, CameraConfig] = field(default_factory=dict)
    use_degrees: bool = True


@TeleoperatorConfig.register_subclass("arduino_leader")
@dataclass
class ArduinoLeaderConfig(TeleoperatorConfig):
    """Config for the custom Arduino 6-DOF leader (ARIS gamepad) arm.

    Leave `port` empty to auto-detect the Arduino.
    """

    port: str = ""
    disable_torque_on_disconnect: bool = True
    max_relative_target: float | dict[str, float] | None = None
    use_degrees: bool = True


class _ArduinoBusShim:
    """Minimal stand-in for lerobot's motors bus.

    `record.py` and `teleoperate.py` call `robot.bus.connect()`,
    `robot.bus.write_calibration(...)` and read `robot.bus.motors`. The
    Arduino has no register-level calibration, so the shim records the
    calibration locally and keeps the motor map for feature discovery.
    """

    def __init__(self, driver: ArduinoRobotDriver):
        self._driver = driver
        self.motors = {name: _MotorStub(name, i + 1) for i, name in enumerate(MOTOR_NAMES)}
        self._calibration = {}
        self.is_connected = False

    def connect(self, handshake: bool = True) -> None:
        self._driver.connect()
        self.is_connected = True

    def disconnect(self) -> None:
        self.is_connected = False
        self._driver.disconnect()

    def write_calibration(self, calibration) -> None:
        self._calibration = calibration

    def read_calibration(self):
        return self._calibration

    def write(self, register: str, motor: str, value) -> None:
        """No-op: the Arduino firmware has no per-motor register interface."""

    def sync_read(self, register: str, *, normalize: bool = True) -> dict:
        return self._driver.read_state()

    def reset_calibration(self) -> None:
        self._calibration = {}

    def disable_torque(self) -> None:
        pass

    def enable_torque(self) -> None:
        pass

    def configure_motors(self) -> None:
        pass

    @property
    def is_calibrated(self) -> bool:
        return bool(self._calibration)


class _MotorStub:
    """Stand-in for lerobot's Motor objects (id + model only)."""

    def __init__(self, name: str, motor_id: int):
        self.name = name
        self.id = motor_id
        self.model = "arduino_servo"


class ArduinoFollower(Robot):
    """LeRobot Robot implementation driving the custom Arduino arm."""

    config_class = ArduinoFollowerConfig
    name = "arduino_follower"

    def __init__(self, config: ArduinoFollowerConfig):
        super().__init__(config)
        self.config = config
        self._driver = ArduinoRobotDriver(port=config.port)
        self.bus = _ArduinoBusShim(self._driver)
        # `cameras` is a plain attribute: record.py and teleoperate.py both
        # read `robot.cameras` and iterate its values.
        self.cameras: dict = make_cameras_from_configs(config.cameras or {})
        # Last good frame per camera. A camera that momentarily stalls (or is
        # briefly claimed by the browser preview) must not abort the recording,
        # so the previous frame is reused instead.
        self._last_frames: dict = {}

    def _motor_features(self) -> dict[str, type]:
        return {f"{motor}.pos": float for motor in CONTINUOUS_MOTORS}

    def _cameras_ft(self) -> dict[str, tuple]:
        """Camera feature shapes, matching lerobot's SO-101 follower."""
        features: dict[str, tuple] = {}
        for name, cam in self.cameras.items():
            if getattr(cam, "use_rgb", True):
                features[name] = (cam.height, cam.width, 3)
            if getattr(cam, "use_depth", False):
                features[f"{name}_depth"] = (cam.height, cam.width, 1)
        return features

    @property
    def observation_features(self) -> dict:
        features = self._motor_features()
        features.update(self._cameras_ft())
        return features

    @property
    def action_features(self) -> dict:
        # The action schema is the 5 continuous joints. The gripper is not a
        # free-running joint, so it rides along in the D: command's `wire`
        # field rather than being a separate action channel.
        return {f"{motor}.pos": float for motor in CONTINUOUS_MOTORS}

    @property
    def is_connected(self) -> bool:
        return self._driver.ser is not None

    @property
    def is_calibrated(self) -> bool:
        return True

    def connect(self, calibrate: bool = True) -> None:
        self.bus.connect()
        for cam in self.cameras.values():
            cam.connect()

    def calibrate(self) -> None:
        """No-op: the Arduino firmware has no register-level calibration."""

    def configure(self) -> None:
        """No-op: the Arduino firmware configures itself."""

    def get_observation(self) -> dict:
        try:
            state = self._driver.read_state()
        except Exception as e:
            # A dropped USB link must not kill the recording loop; report the
            # last known state and let the next frame re-sync.
            print(f"[ArduinoFollower] observation read failed: {e}")
            state = {}
        obs = {f"{motor}.pos": float(state.get(motor, 0.0)) for motor in CONTINUOUS_MOTORS}
        # Cameras: match lerobot's SO-101 follower (read_latest, not async_read).
        # read_latest() raises when the newest frame is older than its freshness
        # limit, which happens whenever the camera stutters - reuse the last
        # good frame rather than failing the episode.
        for name, cam in self.cameras.items():
            if getattr(cam, "use_rgb", True):
                try:
                    self._last_frames[name] = cam.read_latest()
                except Exception:
                    if name not in self._last_frames:
                        # No frame at all yet - fall back to a blank frame so
                        # the dataset schema stays intact.
                        self._last_frames[name] = np.zeros(
                            (cam.height, cam.width, 3), dtype=np.uint8
                        )
                obs[name] = self._last_frames[name]
            if getattr(cam, "use_depth", False):
                try:
                    self._last_frames[f"{name}_depth"] = cam.read_latest_depth()
                except Exception:
                    if f"{name}_depth" not in self._last_frames:
                        self._last_frames[f"{name}_depth"] = np.zeros(
                            (cam.height, cam.width, 1), dtype=np.uint8
                        )
                obs[f"{name}_depth"] = self._last_frames[f"{name}_depth"]
        return obs

    def send_action(self, action: dict) -> dict:
        """Apply a RELATIVE action (lerobot convention) to the arm.

        The Arduino's D: command takes per-joint deltas in degrees, which is
        exactly what lerobot's teleoperation pipeline produces. The gripper is
        not a free-running joint, so it is not part of the action schema; the
        leader publishes the wanted gripper state on the shared driver and the
        follower forwards it as the command's `wire` field (1 = close,
        -1 = open, 0 = leave unchanged).
        """
        deltas = [float(action.get(f"{motor}.pos", 0.0)) for motor in CONTINUOUS_MOTORS]
        wire = getattr(self._driver, "gripper_wire", 0)
        try:
            # send_delta() writes without waiting for the reply, so the control
            # loop never blocks on the serial link.
            self._driver.send_delta(deltas, wire)
        except Exception as e:
            print(f"[ArduinoFollower] send_action failed: {e}")
        return action

    def disconnect(self) -> None:
        for cam in self.cameras.values():
            try:
                cam.disconnect()
            except Exception:
                pass
        self.bus.disconnect()


class ArduinoLeader(Teleoperator):
    """LeRobot Teleoperator implementation for the custom Arduino arm.

    The Cosmic Byte ARIS gaming controller drives the arm; this class reads
    the current joystick state and produces the action dictionary the follower
    consumes.

    The leader and the follower are the same physical Arduino, so only one
    process may hold the serial port. `share_driver()` lets the caller hand
    the follower's open driver to the leader, avoiding a second open() on the
    same device.
    """

    config_class = ArduinoLeaderConfig
    name = "arduino_leader"

    def __init__(self, config: ArduinoLeaderConfig):
        super().__init__(config)
        self.config = config
        self._driver = ArduinoRobotDriver(port=config.port)
        self.bus = _ArduinoBusShim(self._driver)
        self._gamepad = None
        self._gamepad_backend = None
        self._pygame_ready = False
        self._gamepad_thread: threading.Thread | None = None
        self._owns_driver = True
        self._gripper_wire = 0
        self._last_action: dict = {f"{m}.pos": 0.0 for m in CONTINUOUS_MOTORS}

    # -- driver sharing ---------------------------------------------------

    def share_driver(self, driver: ArduinoRobotDriver) -> None:
        """Reuse an already-open serial connection instead of opening it twice.

        The caller (record.py / teleoperate.py) uses this instead of
        connect(), so the gamepad search has to be started here too -
        otherwise the leader never attaches the controller and every action
        stays at zero.
        """
        self._driver = driver
        self.bus = _ArduinoBusShim(driver)
        self._owns_driver = False
        self.start_gamepad_search()

    def start_gamepad_search(self) -> None:
        """Start the background gamepad search (idempotent)."""
        if self._gamepad_thread is not None and self._gamepad_thread.is_alive():
            return
        self._gamepad_thread = threading.Thread(
            target=self._init_gamepad, name="arduino-leader-gamepad", daemon=True
        )
        self._gamepad_thread.start()

    # -- gamepad ----------------------------------------------------------

    def _init_gamepad(self) -> None:
        """Attach the ARIS controller, retrying while it is unavailable.

        macOS hands the USB gamepad to its own Xbox driver, and SDL only
        enumerates it when the controller is awake and no other process
        holds it. So this keeps scanning (a fresh SDL scan each time) in the
        background and never blocks the recording loop.
        """
        deadline = time.monotonic() + 180.0
        while time.monotonic() < deadline:
            if self._try_gamepad_backends():
                return
            time.sleep(2.0)
        print("[ArduinoLeader] Stopped looking for a gamepad")

    def _try_gamepad_backends(self) -> bool:
        """Try to attach a gamepad with whichever backend is available."""
        # --- backend 1: pygame (same code path as the standalone script) ---
        try:
            import pygame

            # SDL builds its HID device list when the joystick subsystem is
            # initialised, and `pygame.joystick.init()` is a no-op once it is
            # up. Tearing pygame down and rebuilding it each retry also
            # re-creates the SDL HID device list - but the Cosmic Byte ARIS
            # auto-sleeps, and while it sleeps macOS keeps the (useless) USB
            # dongle attached while exposing no gamepad.
            #
            # So: initialise pygame ONCE, and afterwards rely on SDL's
            # hotplug events (JOYDEVICEADDED) to notice the controller when
            # it wakes up. Tearing pygame down per retry is what made the
            # scan worse, not better.
            if not getattr(self, "_pygame_ready", False):
                pygame.init()
                pygame.joystick.init()
                self._pygame_ready = True

            # SDL builds its device list when the joystick subsystem starts
            # and does not refresh it on its own. Rebuild that list on every
            # retry so a controller that is plugged in (or woken) later is
            # picked up. This is portable - no macOS-only HID inspection.
            if getattr(self, "_pygame_ready", False):
                try:
                    pygame.joystick.quit()
                    pygame.joystick.init()
                except Exception:
                    pass

            count = pygame.joystick.get_count()
            if count > 0:
                joystick = pygame.joystick.Joystick(0)
                joystick.init()
                self._gamepad = joystick
                self._gamepad_backend = "pygame"
                print(f"[ArduinoLeader] Gamepad connected (pygame): {joystick.get_name()}")
                return True

            # Hotplug: SDL announces a controller that wakes up after init.
            try:
                pygame.event.pump()
                for event in pygame.event.get():
                    if event.type == getattr(pygame, "JOYDEVICEADDED", -1):
                        idx = getattr(event, "device_index", 0)
                        if idx < pygame.joystick.get_count():
                            joystick = pygame.joystick.Joystick(idx)
                            joystick.init()
                            self._gamepad = joystick
                            self._gamepad_backend = "pygame"
                            print(
                                f"[ArduinoLeader] Gamepad hotplugged (pygame): {joystick.get_name()}"
                            )
                            return True
            except Exception:
                pass
            print(
                "[ArduinoLeader] pygame sees 0 gamepads.\n"
                "    The Cosmic Byte ARIS is wireless: the USB dongle is plugged in, but\n"
                "    the CONTROLLER itself must be powered ON (press a button on it).\n"
                "    Also close any other program using it - e.g. the standalone\n"
                "    aris_controller.py holds the device exclusively, and then leLab\n"
                "    cannot open it.\n"
                "    Retrying every 2s for 3 minutes."
            )
        except ImportError:
            print("[ArduinoLeader] pygame not available in this interpreter - trying 'inputs'")
        except Exception as e:
            print(f"[ArduinoLeader] pygame init failed ({e}) - trying 'inputs'")

        # --- backend 2: inputs ---
        try:
            import inputs

            try:
                inputs.devices.refresh_devices()
            except Exception:
                pass
            gamepads = list(inputs.devices.gamepads)
            if gamepads:
                self._gamepad = gamepads[0]
                self._gamepad_backend = "inputs"
                print(f"[ArduinoLeader] Gamepad connected (inputs): {self._gamepad.name}")
                return True
        except ImportError:
            if not getattr(self, "_warned_no_inputs", False):
                print(
                    "[ArduinoLeader] 'inputs' not installed in this interpreter - "
                    "installing it is optional (pygame is the primary backend): "
                    "pip install inputs"
                )
                self._warned_no_inputs = True
        except Exception as e:
            print(f"[ArduinoLeader] inputs init failed: {e}")

        return False

    def _read_inputs_state(self) -> tuple[list[float], list[int]]:
        """Read the 'inputs' backend into (axes, buttons) lists.

        The 'inputs' library is event based: each event carries one axis or
        button change. The latest value per code is kept, so the result
        matches what pygame's get_axis/get_button would report.
        """
        import inputs

        axes = [0.0] * 8
        buttons = [0] * 16

        for event in inputs.get_gamepad():
            if event.ev_type == "Absolute":
                if isinstance(event.code, int) and event.code < len(axes):
                    axes[event.code] = float(event.state)
            elif event.ev_type == "Button":
                if isinstance(event.code, int) and event.code < len(buttons):
                    buttons[event.code] = int(bool(event.state))

        return axes, buttons

    # -- Teleoperator API -------------------------------------------------

    @property
    def action_features(self) -> dict:
        return {f"{motor}.pos": float for motor in CONTINUOUS_MOTORS}

    @property
    def feedback_features(self) -> dict:
        return {f"{motor}.pos": float for motor in CONTINUOUS_MOTORS}

    @property
    def is_connected(self) -> bool:
        return self._driver.ser is not None

    @property
    def is_calibrated(self) -> bool:
        return True

    def connect(self, calibrate: bool = True) -> None:
        # The bus shim opens the serial port; the gamepad is attached after.
        # When the driver is shared with the follower the port is already open.
        if self._owns_driver:
            self.bus.connect()
        else:
            self.bus.is_connected = True
        # Attach the gamepad without blocking the caller: the search runs in
        # the background so a controller plugged in later is still picked up.
        self.start_gamepad_search()

    def calibrate(self) -> None:
        """No-op: the Arduino firmware has no register-level calibration."""

    def configure(self) -> None:
        """No-op: the Arduino firmware configures itself."""

    def get_action(self) -> dict:
        """Read the gamepad and return the per-frame joint DELTAS in degrees.

        The values are relative moves (lerobot's convention), not absolute
        angles: the follower applies them to the arm's current position.
        """
        action = {f"{m}.pos": self._last_action.get(f"{m}.pos", 0.0) for m in CONTINUOUS_MOTORS}
        if self._gamepad is None:
            # The controller may have woken up since the last scan; check for
            # it here so the arm starts moving the moment it is available.
            try:
                self._try_gamepad_backends()
            except Exception:
                pass
            if self._gamepad is None:
                return action

        try:
            if self._gamepad_backend == "inputs":
                axes, buttons = self._read_inputs_state()
            else:
                import pygame

                pygame.event.pump()
                axes = [self._gamepad.get_axis(i) for i in range(self._gamepad.get_numaxes())]
                buttons = [self._gamepad.get_button(i) for i in range(self._gamepad.get_numbuttons())]

            def axis(i):
                if i >= len(axes):
                    return 0.0
                v = float(axes[i])
                return 0.0 if abs(v) < STICK_DEADZONE else v

            def pressed(i):
                return i < len(buttons) and bool(buttons[i])

            def trigger(i):
                """Triggers rest at -1 and reach +1 when pressed -> 0..1."""
                if i >= len(axes):
                    return 0.0
                return max(0.0, min(1.0, (float(axes[i]) + 1.0) / 2.0))

            # Sticks -> per-frame deltas.
            action["base.pos"] = axis(AXIS_BASE) * DELTA_SCALE
            action["shoulder.pos"] = -axis(AXIS_SHOULDER) * DELTA_SCALE
            action["wrist.pos"] = -axis(AXIS_RIGHT_Y) * DELTA_SCALE
            action["rotate.pos"] = axis(AXIS_RIGHT_X) * DELTA_SCALE

            # Elbow from the triggers, with the shoulder buttons as a fallback.
            if trigger(AXIS_RT) > TRIGGER_THRESHOLD or pressed(BTN_ELBOW_UP):
                action["elbow.pos"] = DELTA_SCALE
            elif trigger(AXIS_LT) > TRIGGER_THRESHOLD or pressed(BTN_ELBOW_DOWN):
                action["elbow.pos"] = -DELTA_SCALE
            else:
                action["elbow.pos"] = 0.0

            # Gripper: A closes, B opens. The firmware's `wire` convention is
            # absolute (1 = closed / 90 deg, -1 = open / 0 deg), so the leader
            # publishes the state on the shared driver.
            if pressed(BTN_GRIPPER_CLOSE):
                self._gripper_wire = 1
            elif pressed(BTN_GRIPPER_OPEN):
                self._gripper_wire = -1
            self._driver.gripper_wire = self._gripper_wire

            self._last_action = dict(action)
        except Exception as e:
            print(f"[ArduinoLeader] Gamepad read failed: {e}")

        return action

    def send_feedback(self, feedback: dict) -> None:
        """No-op: the Arduino arm has no feedback channel."""

    def disconnect(self) -> None:
        # Only close the port if this object opened it (see share_driver).
        if self._owns_driver:
            self.bus.disconnect()
        else:
            self.bus.is_connected = False
        if self._gamepad is not None:
            try:
                self._gamepad.quit()
            except Exception:
                pass
            self._gamepad = None
