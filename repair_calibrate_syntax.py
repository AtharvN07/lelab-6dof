from pathlib import Path

p = Path("lelab/calibrate.py")
s = p.read_text(encoding="utf-8")

bad = r"\n    def _complete_calibration(self):"
good = "\n    def _complete_calibration(self):"

if bad not in s:
    print("Exact escaped-newline pattern not found; checking alternatives.")
    bad2 = r"\\n    def _complete_calibration(self):"
    if bad2 not in s:
        raise SystemExit("Pattern not found. File unchanged; show lines 475-490.")
    s = s.replace(bad2, good, 1)
else:
    s = s.replace(bad, good, 1)

p.write_text(s, encoding="utf-8")
print("Repaired escaped newline before _complete_calibration.")
