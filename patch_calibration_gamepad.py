from pathlib import Path

p = Path("lelab/calibrate.py")
s = p.read_text(encoding="utf-8")

def replace_once(old, new, label):
    global s
    count = s.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly one match, found {count}. "
            "No file changes have been written."
        )
    s = s.replace(old, new, 1)

replace_once(
    "from .arduino_driver import ArduinoRobotDriver\n",
    "from .arduino_driver import ArduinoRobotDriver\n"
    "from .arduino_robot import ArduinoLeader, ArduinoLeaderConfig, CONTINUOUS_MOTORS\n",
    "imports",
)

replace_once(
    "        self.device: ArduinoRobotDriver | None = None\n",
    "        self.device: ArduinoRobotDriver | None = None\n"
    "        self.gamepad_leader: ArduinoLeader | None = None\n"
    "        self._gamepad_stop = threading.Event()\n"
    "        self._gamepad_thread: threading.Thread | None = None\n",
    "manager fields",
)

replace_once(
    "            self.device.connect()\n\n"
    "            if self.stop_calibration:\n",
    "            self.device.connect()\n"
    "            # Share the calibration driver's serial connection; never open COM9 twice.\n"
    "            self.gamepad_leader = ArduinoLeader(\n"
    "                ArduinoLeaderConfig(port=request.port)\n"
    "            )\n"
    "            self.gamepad_leader.share_driver(self.device)\n\n"
    "            if self.stop_calibration:\n",
    "shared driver setup",
)

replace_once(
    "        self._recording_active = True\n"
    "        prev_positions: dict[str, int] = dict(self._start_positions)\n\n"
    "        while not self._step_complete.is_set() and not self.stop_calibration:\n",
    "        self._recording_active = True\n"
    "        prev_positions: dict[str, int] = dict(self._start_positions)\n"
    "        self._gamepad_stop.clear()\n"
    "        self._gamepad_thread = threading.Thread(\n"
    "            target=self._calibration_gamepad_loop,\n"
    "            name=\"calibration-gamepad-control\",\n"
    "            daemon=True,\n"
    "        )\n"
    "        self._gamepad_thread.start()\n\n"
    "        while not self._step_complete.is_set() and not self.stop_calibration:\n",
    "start gamepad during recording",
)

replace_once(
    "        if self.stop_calibration:\n"
    "            logger.info(\"Range recording step cancelled due to stop request\")\n",
    "        self._gamepad_stop.set()\n"
    "        if self._gamepad_thread and self._gamepad_thread.is_alive():\n"
    "            self._gamepad_thread.join(timeout=1.0)\n"
    "        self._gamepad_thread = None\n\n"
    "        if self.stop_calibration:\n"
    "            logger.info(\"Range recording step cancelled due to stop request\")\n",
    "stop gamepad after recording",
)

replace_once(
    "    def _complete_calibration(self):\n",
    "    def _calibration_gamepad_loop(self):\n"
    "        \"\"\"Move the arm slowly from the gamepad during range recording.\"\"\"\n"
    "        leader = self.gamepad_leader\n"
    "        driver = self.device\n"
    "        if leader is None or driver is None:\n"
    "            logger.error(\"Calibration gamepad is not initialized\")\n"
    "            return\n\n"
    "        logger.info(\"Calibration gamepad control active; approx. 1 degree per active joint per frame\")\n"
    "        while not self._gamepad_stop.is_set() and not self.stop_calibration:\n"
    "            try:\n"
    "                action = leader.get_action()\n"
    "                deltas = []\n"
    "                for motor in CONTINUOUS_MOTORS:\n"
    "                    value = float(action.get(f\"{motor}.pos\", 0.0))\n"
    "                    # Use direction only: one degree per control frame, not the normal 3-degree step.\n"
    "                    if abs(value) < 0.15:\n"
    "                        deltas.append(0)\n"
    "                    else:\n"
    "                        deltas.append(1 if value > 0 else -1)\n"
    "                driver.send_delta(deltas, getattr(driver, \"gripper_wire\", 0))\n"
    "            except Exception:\n"
    "                logger.exception(\"Calibration gamepad control failed\")\n"
    "                break\n"
    "            time.sleep(0.12)\n"
    "        logger.info(\"Calibration gamepad control stopped\")\n\n"
    "    def _complete_calibration(self):\n",
    "gamepad loop method",
)

replace_once(
    "    def _cleanup_device(self):\n"
    "        if self.device:\n",
    "    def _cleanup_device(self):\n"
    "        self._gamepad_stop.set()\n"
    "        if self._gamepad_thread and self._gamepad_thread.is_alive():\n"
    "            self._gamepad_thread.join(timeout=1.0)\n"
    "        self._gamepad_thread = None\n"
    "        if self.gamepad_leader:\n"
    "            try:\n"
    "                self.gamepad_leader.disconnect()\n"
    "            except Exception:\n"
    "                logger.exception(\"Error disconnecting calibration gamepad\")\n"
    "            self.gamepad_leader = None\n"
    "        if self.device:\n",
    "cleanup",
)

p.write_text(s, encoding="utf-8")
print("PATCH APPLIED:", p)
