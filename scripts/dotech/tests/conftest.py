"""Hace importables los scripts de scripts/dotech/ desde sus tests."""

import sys
from pathlib import Path

DIR_SCRIPTS = Path(__file__).resolve().parent.parent
if str(DIR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DIR_SCRIPTS))
