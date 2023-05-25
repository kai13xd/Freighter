from freighter.colors import *

import sys


class FreighterException(Exception):
    def __init__(self, message):
        print(f"{ORANGE}{AnsiAttribute.BLINK}Raised Exception{AnsiAttribute.RESET}: {CYAN}{message}{AnsiAttribute.RESET}")
        sys.exit(1)
