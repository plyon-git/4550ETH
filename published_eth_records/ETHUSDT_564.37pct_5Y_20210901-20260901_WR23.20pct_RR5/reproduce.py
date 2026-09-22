"""Replay this immutable historical record, never a live order."""
from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parent.parent
raise SystemExit(subprocess.call([sys.executable,str(root/'reproduce.py'),'--case','564.37']+sys.argv[1:]))
