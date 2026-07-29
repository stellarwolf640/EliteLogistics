import json
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
python_text = (root / "backend/src/elite_logistics/version.py").read_text()
version = re.search(r'APP_VERSION = "([^"]+)"', python_text).group(1)
pyproject = re.search(r'^version = "([^"]+)"', (root / "backend/pyproject.toml").read_text(), re.M).group(1)
frontend = json.loads((root / "frontend/package.json").read_text())["version"]
tag = next((arg.removeprefix("v") for arg in sys.argv[1:] if arg.startswith("v")), version)
values = {"version.py": version, "pyproject.toml": pyproject, "package.json": frontend, "tag": tag}
if len(set(values.values())) != 1:
    raise SystemExit(f"ION version mismatch: {values}")
print(version)
