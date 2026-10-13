"""Installed service entry; -I excludes user site-packages and environment paths."""
import sys

sys.path.insert(0, "/usr/lib/deepcool-linux")
from deepcool_linux.cli import main

raise SystemExit(main(["run"]))
