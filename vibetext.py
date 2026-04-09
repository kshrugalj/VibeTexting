import os
import sys


repo_root = os.path.dirname(os.path.abspath(__file__))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from vibetexting.cli import main


if __name__ == "__main__":
    raise SystemExit(main())