import re
from typing import Any
from freighter.colors import *
from freighter.ansicolor import ansi_format


COMPILING = f"🛠️{AnsiAttribute.BOLD}{ORANGE}Compiling{AnsiAttribute.RESET}"
ERROR = f"🚫{AnsiAttribute.BOLD}{RED} Error  {AnsiAttribute.RESET}"
SUCCESS = f"✅{AnsiAttribute.BOLD}{GREEN} Success{AnsiAttribute.RESET}"
LINKING = f"📦{AnsiAttribute.BOLD}{GREEN} Linking{AnsiAttribute.RESET}"
LINKED = f"✅{AnsiAttribute.BOLD}{GREEN} Linked{AnsiAttribute.RESET}"
ANALYZING = f"🔎{AnsiAttribute.BOLD}{ORANGE} Analyzing{AnsiAttribute.RESET}"

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
    def formatString(obj:Any)->str:
        string = str(obj)
        string = Console.re_string.sub(Console.re_replace_string, string)
        string = Console.re_string2.sub(Console.re_replace_string2, string)
        string = Console.re_hex.sub(Console.re_replace_hex, string)
        return string
    
    @staticmethod
    def print(obj: Any) -> None:
        print(f"{Console.formatString(obj)}{AnsiAttribute.RESET}")

    
    @staticmethod
    def printInfo(obj: Any) -> None:
        print(f"{Console.info + Console.formatString(obj)}{AnsiAttribute.RESET}")
   
    @staticmethod
    def printWarn(obj: Any) -> None:
        print(f"{Console.warn + Console.formatString(obj)}{AnsiAttribute.RESET}")
        
    @staticmethod
    def printError(obj: Any) -> None:
        print(f"{Console.error + Console.formatString(obj)}{AnsiAttribute.RESET}")
        
    @staticmethod
    def printDebug(obj: Any) -> None:
        from freighter.arguments import Arguments
        if Arguments.debug:
            print(f"{Console.debug + Console.formatString(obj)}{AnsiAttribute.RESET}")

    @staticmethod
    def printVerbose(obj: Any) -> None:
        from freighter.arguments import Arguments
        if Arguments.verbose:
            print(f"{Console.verbose + Console.formatString(obj)}{AnsiAttribute.RESET}")