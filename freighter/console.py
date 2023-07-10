import re
from enum import IntEnum
from typing import Any
from freighter.colors import *
from freighter.ansicolor import ansi_format


COMPILING = f"🛠️{AnsiAttribute.BOLD}{ORANGE}Compiling{AnsiAttribute.RESET}"
ERROR = f"🚫{AnsiAttribute.BOLD}{RED} Error  {AnsiAttribute.RESET}"
SUCCESS = f"✅{AnsiAttribute.BOLD}{GREEN} Success{AnsiAttribute.RESET}"
LINKING = f"📦{AnsiAttribute.BOLD}{GREEN} Linking{AnsiAttribute.RESET}"
LINKED = f"✅{AnsiAttribute.BOLD}{GREEN} Linked{AnsiAttribute.RESET}"
ANALYZING = f"🔎{AnsiAttribute.BOLD}{ORANGE} Analyzing{AnsiAttribute.RESET}"


class PrintType(IntEnum):
    NORMAL = 0
    ERROR = 1
    WARN = 2
    INFO = 3
    VERBOSE = 4
    DEBUG = 5


class Console:
    error = f"{AnsiAttribute.BOLD}[{RED}Error{AnsiAttribute.RESET}] "
    info = f"{AnsiAttribute.BOLD}[{CYAN}Info{AnsiAttribute.RESET}] "
    warn = f"{AnsiAttribute.BOLD}[{ORANGE}Warn{AnsiAttribute.RESET}] "
    verbose = f"{AnsiAttribute.BOLD}[{PURPLE}Verbose{AnsiAttribute.RESET}] "
    debug = f"{AnsiAttribute.BOLD}[{MAGENTA}Debug{AnsiAttribute.RESET}] "

    re_string = re.compile(r'"(.*?)"')
    re_string2 = re.compile(r"'(.*?)'")
    re_replace_string = rf'{ORANGE}"{CYAN}\1{ORANGE}"{AnsiAttribute.RESET}'
    re_replace_string2 = rf"{ORANGE}'{CYAN}\1{ORANGE}'{AnsiAttribute.RESET}"
    re_hex = re.compile(r"(0[xX])([0-9a-fA-F]+)")
    re_replace_hex = rf"{CYAN}\1{GREEN}\2{AnsiAttribute.RESET}"

    @staticmethod
    def print(obj: Any, type=PrintType.NORMAL) -> None:
        from freighter.arguments import Arguments

        if type is PrintType.VERBOSE and not Arguments.verbose:
            return
        elif type is PrintType.DEBUG and not Arguments.debug:
            return

        string = str(obj)
        string = Console.re_string.sub(Console.re_replace_string, string)
        string = Console.re_string2.sub(Console.re_replace_string2, string)
        string = Console.re_hex.sub(Console.re_replace_hex, string)

        if type == PrintType.NORMAL:
            print(f"{string}{AnsiAttribute.RESET}")
        elif type == PrintType.INFO:
            print(f"{Console.info + string}{AnsiAttribute.RESET}")
        elif type == PrintType.ERROR:
            print(f"{Console.error + string}{AnsiAttribute.RESET}")
        elif type == PrintType.WARN:
            print(f"{Console.warn + string}{AnsiAttribute.RESET}")
        elif type == PrintType.VERBOSE:
            print(f"{Console.verbose + string}{AnsiAttribute.RESET}")
        elif type == PrintType.DEBUG:
            print(f"{Console.debug + string}{AnsiAttribute.RESET}")
