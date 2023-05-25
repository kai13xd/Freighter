import re
from enum import IntEnum
from typing import Any
from freighter.colors import *
from freighter.ansicolor import ansi_format


Compiling = ansi_format("🛠️ Compiling!", GREEN, AnsiAttribute.BOLD)
Error = ansi_format("❌ Error:", ORANGE, AnsiAttribute.BOLD)
Success = ansi_format("✔️ Success!", GREEN, AnsiAttribute.BOLD)
Linked = ansi_format("✔️ Linked!", GREEN, AnsiAttribute.BOLD)


class PrintType(IntEnum):
    ERROR = 0
    WARN = 1
    INFO = 2
    VERBOSE = 3
    DEBUG = 4


class Console:
    info = f"{AnsiAttribute.RESET}[{AnsiAttribute.BOLD}{CYAN}Info{AnsiAttribute.RESET}] "
    warn = f"{AnsiAttribute.RESET}[{AnsiAttribute.BOLD}{ORANGE}Warn{AnsiAttribute.RESET}] "
    verbose = f"{AnsiAttribute.RESET}[{AnsiAttribute.BOLD}{PURPLE}Verbose{AnsiAttribute.RESET}] "

    re_string = r'"(.*)"'
    re_replace_string = rf'{ORANGE}"{CYAN}\1{ORANGE}"{AnsiAttribute.RESET}'
    re_hex = r"(0x)([0-9a-f].* )"
    re_replace_hex = rf"{PURPLE}\1{GREEN}\2{AnsiAttribute.RESET}"

    @staticmethod
    def print(obj: Any, type=PrintType.INFO) -> None:
        from freighter.arguments import Arguments

        if type is PrintType.VERBOSE and not Arguments.verbose:
            return
        string = str(obj)
        string = re.sub(Console.re_string, Console.re_replace_string, string)
        string = re.sub(Console.re_hex, Console.re_replace_hex, string)

        if type == PrintType.INFO:
            print(Console.info + string)
        elif type == PrintType.WARN:
            print(Console.warn + string)
        elif type == PrintType.VERBOSE:
            print(Console.verbose + string)
