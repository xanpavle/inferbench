import sys
from pathlib import Path

# Ensure C:\dev\inferbench is always at the top of sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from inferbench.cli import main

if __name__ == "__main__":
    main()
