from .constants import *
from types import TracebackType
import sys
import os


class FreighterException(Exception):
    def __init__(self, message):
        print(f"{ERROR_COLOR}{AnsiAttribute.BLINK}Raised Exception{AnsiAttribute.RESET}: {INFO_COLOR}{message}{AnsiAttribute.RESET}")
        sys.exit(1)
