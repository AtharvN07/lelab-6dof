from pathlib import Path

p = Path("lelab/calibrate.py")
s = p.read_text(encoding="utf-8")

start = '                # TEMP DEBUG: show controller actions during calibration.\n'
end = '                    self._last_gamepad_debug = now\n'

if start not in s or end not in s:
    raise SystemExit("Temporary debug block not found; file unchanged.")

i = s.index(start)
j = s.index(end, i) + len(end)

s = s[:i] + s[j:]
p.write_text(s, encoding="utf-8")
print("Removed temporary debug block.")
