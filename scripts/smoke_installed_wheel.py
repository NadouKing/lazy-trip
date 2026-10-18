"""Run with an installed environment, from outside all source checkouts.

Example: <fresh-venv-python> <checkout>/scripts/smoke_installed_wheel.py
This script does not launch browsers or inspect credentials.
"""

import importlib
import importlib.metadata
import json
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    checkout = Path(__file__).resolve().parents[1]
    packages = {}
    for module_name, distribution in (("lazy_trip", "lazy-trip"),
                                      ("xiaohongshu_tools", "xiaohongshu-tools"),
                                      ("dazhongdianping_tools", "dazhongdianping-tools")):
        module = importlib.import_module(module_name)
        source = Path(module.__file__).resolve()
        if source.is_relative_to(checkout.parent):
            raise RuntimeError(f"{module_name} is imported from a source checkout")
        packages[distribution] = importlib.metadata.version(distribution)
    from lazy_trip.cli import main as cli
    with TemporaryDirectory() as folder:
        target = Path(folder) / "request.json"
        assert cli(["init", "--out", str(target)]) == 0
        assert json.loads(target.read_text(encoding="utf-8"))["city"] == ""
    print(json.dumps({"installedWheelSmoke": "passed", "packages": packages}, indent=2))


if __name__ == "__main__":
    main()
