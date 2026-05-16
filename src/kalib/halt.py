"""Using for halt the program with error code 127, usage, just:

from kalib import halt
"""

import sys
from logging import getLogger

getLogger(__name__).exception("halt")
sys.exit(127)
