from .ansicolor import *
import re
from enum import IntEnum

HOCOTATE_RED = AnsiTrueColor(251, 58, 43)
HOCOTATE_RED_BACKGROUND = AnsiTrueColor(251, 58, 43, is_background=True)
HOCOTATE_BEIGE = AnsiTrueColor(240, 217, 136)
HOCOTATE_BEIGE_BACKGROUND = AnsiTrueColor(240, 217, 136, is_background=True)

WHITE = AnsiTrueColor(255, 255, 255)
CYAN = AnsiTrueColor(25, 230, 192)
ORANGE = AnsiTrueColor(255, 210, 77)
RED = AnsiTrueColor(255, 77, 88)
GREEN = AnsiTrueColor(25, 230, 25)
PURPLE = AnsiTrueColor(147, 110, 221)

INFO_COLOR = CYAN
WARN_COLOR = ORANGE
ERROR_COLOR = RED
SUCCESS_COLOR = GREEN
PURPLE_COLOR = PURPLE

COMPILING = ansi_format("🛠️ Compiling!", WARN_COLOR, AnsiAttribute.BOLD)
ERROR = ansi_format("❌ Error:", ERROR_COLOR, AnsiAttribute.BOLD)
SUCCESS = ansi_format("✔️ Success!", SUCCESS_COLOR, AnsiAttribute.BOLD)
LINKED = ansi_format("✔️ Linked!", SUCCESS_COLOR, AnsiAttribute.BOLD)
HEX = f"{PURPLE_COLOR}0x{SUCCESS_COLOR}"


RE_STRING = r'"(.*)"'
RE_STRING_REPLACE = rf'{ORANGE}"{CYAN}\1{ORANGE}"{AnsiAttribute.RESET}'

RE_HEX = r"(0x)([0-9a-f].* )"
RE_HEX_REPLACE = rf"{PURPLE}\1{GREEN}\2{AnsiAttribute.RESET}"


FREIGHTER = f"{AnsiAttribute.BOLD}{HOCOTATE_RED}Freighter{AnsiAttribute.RESET}"
INFO = f"{AnsiAttribute.RESET}[{AnsiAttribute.BOLD}{CYAN}Info{AnsiAttribute.RESET}] "
WARN = f"{AnsiAttribute.RESET}[{AnsiAttribute.BOLD}{ORANGE}WARN{AnsiAttribute.RESET}] "


class PrintType(IntEnum):
    ERROR = 0
    WARN = 1
    INFO = 2
    VERBOSE = 3


def console_print(string: str, type=PrintType.INFO) -> None:
    from .cli import Arguments

    if not Arguments.verbose and type == PrintType.VERBOSE:
        return
    string = re.sub(RE_STRING, RE_STRING_REPLACE, string)
    string = re.sub(RE_HEX, RE_HEX_REPLACE, string)
    if type == "Info":
        print(INFO + string)
    if type == "Warn":
        print(WARN + string)
