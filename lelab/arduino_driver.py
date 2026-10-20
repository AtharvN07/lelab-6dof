"""
Arduino Mega + PCA9685 driver for the custom 6-DOF arm.

Speaks robot_controller_v8.ino's newline-terminated protocol at 115200 baud:

    PING\\n    -> PONG
    HOME\\n    -> OK:HOME:90,90,90,90,90,0
    STATE\\n   -> OK:STATE:b,s,e,w,r,g
    A:b,s,e,w,r,g\\n -> OK:A:...   (absolute servo degrees)
    D:d0,d1,d2,d3,d4,wire\\n -> OK:D:...  (delta degrees + gripper wire)

The servos have no encoder feedback, so the Arduino owns the position state:
this driver only ever sends commands and reads back what the Arduino reports.

A background reader thread owns the serial port. Every command is written
without waiting for its reply, and the reader parses the replies as they
arrive, keeping the latest joint angles in `state`. That keeps the control
loop free of blocking reads - at 30 Hz a synchronous round trip per command
would add tens of milliseconds of latency and make the arm feel laggy.
"""

import threading
import time

import serial

JOINT_NAMES = ["base", "shoulder", "elbow", "wrist", "rotate", "gripper"]

# USB vendor ids of the common Arduino boards, used to tell an Arduino apart
# from other serial devices when the port is not given explicitly.
ARDUINO_VENDOR_IDS = {
    0x2341,  # Arduino official
    0x2A03,  # Arduino (other)
    0x1A86,  # CH340 / CP210x clones
    0x10C4,  # Silicon Labs CP210x
    0x0403,  # FTDI
    0x1B4F,  # SparkFun
}


def find_arduino_port() -> str | None:
    """Return the device path of the first Arduino-like serial port.

    Works on Windows (COM3, ...), Linux (/dev/ttyUSB0, /dev/ttyACM0) and
    macOS (/dev/cu.usbmodem*). Falls back to any serial port when no Arduino
    vendor id matches, so a clone with an unusual id is still found.
    """
    try:
        from serial.tools import list_ports
    except ImportError:
        return None

    try:
        ports = list(list_ports.comports())
    except Exception:
        return None

    if not ports:
        return None

    # Prefer a port whose USB vendor id belongs to a known Arduino.
    for port in ports:
        if port.vid in ARDUINO_VENDOR_IDS:
            return port.device

    # No vendor match: take the first serial port that is a real device.
    # macOS exposes internal pseudo-ports (debug-console, Bluetooth, ...) that
    # must be skipped.
    internal = ("debug-console", "bluetooth", "wlan", "modem", "irda", "cu.debug")
    for port in ports:
        name = port.device.lower()
        if any(token in name for token in internal):
            continue
        return port.device

    return ports[0].device


class ArduinoRobotDriver:
    def __init__(self, port=None, baud=115200, timeout=1):
        # An empty port means "find the Arduino". The exact device name
        # differs per platform and per USB port, so it is resolved at connect
        # time instead of being hard-coded.
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.ser = None
        # Last commanded gripper state: 1 = close (90 deg), -1 = open (0 deg),
        # 0 = unchanged. The leader sets it; the follower applies it, because
        # the gripper is not part of lerobot's action schema.
        self.gripper_wire = 0
        # Last state read from the board, reused if a read fails.
        self._last_state: dict = {}
        self.state: dict = {}
        self._pong = False
        self._stop = threading.Event()
        self._reader: threading.Thread | None = None
        self._write_lock = threading.Lock()

    # -- connection -------------------------------------------------------

    def connect(self) -> None:
        """Open the port, start the reader thread and wait for one state."""
        if not self.port:
            self.port = find_arduino_port()
            if not self.port:
                raise RuntimeError(
                    "No Arduino serial port found. Plug in the Arduino and check "
                    "the port (Windows: Device Manager > Ports; Linux: /dev/ttyUSB*; "
                    "macOS: /dev/cu.usbmodem*)."
                )
            print(f"[Arduino] Using port {self.port}")
        self.ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
        time.sleep(2)  # let the board finish booting and print READY
        self._drain()
        self._stop.clear()
        self._reader = threading.Thread(target=self._read_loop, name="arduino-reader", daemon=True)
        self._reader.start()
        if not self._ping():
            time.sleep(1)
            if not self._ping():
                raise RuntimeError(f"Arduino did not respond on {self.port}")
        self.home()
        # Prime the state so the first observation is not empty.
        self.request_state()
        deadline = time.time() + 2.0
        while time.time() < deadline and not self.state:
            time.sleep(0.02)
        if not self.state:
            raise RuntimeError(f"Arduino did not report a state on {self.port}")

    def disconnect(self) -> None:
        self._stop.set()
        if self._reader and self._reader.is_alive():
            self._reader.join(timeout=1.0)
        self._reader = None
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    def is_open(self) -> bool:
        return self.ser is not None and self.ser.is_open

    # -- background reader ------------------------------------------------

    def _read_loop(self) -> None:
        """Read replies continuously and keep the latest state.

        Any line that is not a known reply (a boot banner, a fragment from a
        board reboot) is ignored, so a garbled line can never desynchronise
        the driver.
        """
        while not self._stop.is_set():
            if not self.ser:
                time.sleep(0.05)
                continue
            try:
                raw = self.ser.readline()
            except serial.SerialException:
                # The link dropped. Reopen in the background so the control
                # loop keeps running; the arm holds its last position.
                time.sleep(0.2)
                self._reopen()
                continue
            except Exception:
                time.sleep(0.05)
                continue

            if not raw:
                continue
            line = raw.decode("utf-8", "ignore").strip()
            if not line:
                continue

            if "OK:STATE:" in line:
                parsed = self._parse_state(line.split("OK:STATE:", 1)[1])
                if parsed:
                    self.state = parsed
                    self._last_state = parsed
            elif "PONG" in line:
                self._pong = True
            elif "OK:HOME:" in line:
                parsed = self._parse_state(line.split("OK:HOME:", 1)[1])
                if parsed:
                    self.state = parsed
                    self._last_state = parsed
            # "OK:D:" / "OK:A:" are just receipts - the state arrives with
            # the next STATE reply, so nothing to do here.

    def _reopen(self) -> bool:
        """Re-establish the serial link after the board dropped it."""
        try:
            if self.ser:
                self.ser.close()
            self.ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
            time.sleep(0.5)
            self._drain()
            return True
        except Exception:
            self.ser = None
            return False

    # -- low level helpers ------------------------------------------------

    def _drain(self) -> None:
        """Discard whatever is pending in the input buffer."""
        try:
            if self.ser:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
        except Exception:
            pass

    def _write(self, payload: bytes) -> None:
        """Write a command without waiting for its reply."""
        if not self.ser:
            return
        with self._write_lock:
            try:
                self.ser.write(payload)
                self.ser.flush()
            except serial.SerialException:
                self._reopen()

    def _ping(self) -> bool:
        """Send PING and wait for PONG (only used at connect time)."""
        self._pong = False
        self._write(b"PING\n")
        deadline = time.time() + 1.0
        while time.time() < deadline:
            if self._pong:
                return True
            time.sleep(0.01)
        return False

    def request_state(self) -> None:
        """Ask the board for its current joint angles (no wait)."""
        self._write(b"STATE\n")

    # -- public commands --------------------------------------------------

    def home(self) -> str:
        """Park every servo at 90 deg and open the gripper."""
        self._write(b"HOME\n")
        # Give the board a moment to apply it and report back.
        deadline = time.time() + 0.5
        while time.time() < deadline:
            if self.state.get("base") == 90 and self.state.get("gripper") == 0:
                break
            time.sleep(0.01)
        return "OK:HOME:" + ",".join(str(self.state.get(n, 0)) for n in JOINT_NAMES)

    def read_state(self) -> dict:
        """The latest joint angles (degrees) reported by the board.

        This never blocks: the background reader keeps `state` up to date.
        """
        if self.state:
            return dict(self.state)
        return dict(self._last_state)

    def refresh_state(self, timeout: float = 1.0) -> dict:
        """Request a fresh state and wait for it (used during calibration)."""
        before = dict(self.state)
        self.request_state()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.state and self.state != before:
                return dict(self.state)
            time.sleep(0.005)
        return dict(self.state or self._last_state)

    def send_delta(self, deltas_5, wire: int = 0) -> str:
        """Send a relative move: 5 joint deltas (degrees) + gripper wire.

        wire: 1 = close gripper (90 deg), -1 = open (0 deg), 0 = leave unchanged.

        The command is written without waiting for the reply, so the control
        loop never blocks on the serial link.
        """
        deltas = list(deltas_5)[:5]
        while len(deltas) < 5:
            deltas.append(0)
        wire = int(wire)
        self.gripper_wire = wire
        cmd = "D:" + ",".join(str(int(round(float(d)))) for d in deltas) + f",{wire}\n"
        self._write(cmd.encode())
        return cmd

    def send_absolute(self, angles_5) -> str:
        """Send an absolute move: 5 joint angles (degrees)."""
        angles = list(angles_5)[:5]
        while len(angles) < 5:
            angles.append(0)
        cmd = "A:" + ",".join(str(int(round(float(a)))) for a in angles) + "\n"
        self._write(cmd.encode())
        return cmd

    def calibrate_trim(self, ch: int) -> str:
        """Capture the current servo offset as the trim for channel `ch`."""
        self._write(f"C:{int(ch)}\n".encode())
        return f"OK:CAPTURE:{int(ch)}"

    def zero_trim(self, ch=None) -> str:
        """Zero the trim for one channel, or all of them when ch is None."""
        payload = b"Z:ALL\n" if ch is None else f"Z:{int(ch)}\n".encode()
        self._write(payload)
        return "OK:ZERO:ALL" if ch is None else f"OK:ZERO:{int(ch)}"

    @staticmethod
    def _parse_state(payload: str) -> dict:
        """Parse a comma-separated list of joint angles into a dict."""
        values = []
        for part in payload.split(","):
            part = part.strip()
            try:
                values.append(int(float(part)))
            except ValueError:
                return {}
        if len(values) < len(JOINT_NAMES):
            return {}
        return dict(zip(JOINT_NAMES, values))


if __name__ == "__main__":
    board = ArduinoRobotDriver(port=None)  # auto-detects the Arduino
    board.connect()
    print("Connected. State:", board.read_state())
    print("Delta +5/-3:", board.send_delta([5, -3, 0, 0, 0], 0))
    time.sleep(0.2)
    print("State:", board.read_state())
    board.disconnect()
