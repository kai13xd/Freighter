from freighter.colors import *
from freighter.console import Console
import sys


class FreighterException(Exception):
    def __init__(self, message):
        Console.print(f"{RED}{AnsiAttribute.BLINK}Raised Exception{AnsiAttribute.RESET}: {message}{AnsiAttribute.RESET}")
        sys.exit(1)
