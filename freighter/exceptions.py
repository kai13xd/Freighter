from freighter.colors import *
from freighter.console import Console
from enum import StrEnum
import sys



InvalidBranch = f""""""

class FreighterException(Exception):
    raised_exception_start = f"{RED}{AnsiAttribute.BLINK}Raised Exception{AnsiAttribute.RESET}"
    def __init__(self, message):
        Console.print(f"{self.raised_exception_start}: {message}{AnsiAttribute.RESET}")
        

class BadFunctionSignatureExecption(FreighterException):


    def __init__(self,source_file,line_number:int, line:str ):
        message =f"""{ORANGE}Bad function signature!
'{line}' found on line {line_number} in '{source_file}'

When processing #pragma inject or pointer Freighter requires:
• {CYAN}The pragma to be placed above the function definition/forward declaration.
• {CYAN}The function defintion or forward declaration to be defined outside the class within a source file.
• {CYAN}The function signature must be on a single line.

Format: {WHITE}[[{CYAN}Attributes{WHITE}]] {PURPLE}CV-type qualifiers {GREEN}Decl-Specifiers {CYAN}ReturnType {GREEN}Namespaces{WHITE}::{RED}Class{WHITE}::{YELLOW}FunctionName{WHITE}({MAGENTA}Arguments{WHITE})
Example: {WHITE}[[{CYAN}gnu::always_inline{WHITE}]] {PURPLE}volatile {GREEN}const {CYAN}void* {GREEN}FooNamespace{WHITE}::{RED}BarClass{WHITE}::{YELLOW}myFunction{MAGENTA}{WHITE}({MAGENTA}int arg1{WHITE}, {MAGENTA}void(*functionPtr)(int){WHITE}, {MAGENTA}...{WHITE}) {PURPLE}const"""
        super().__init__(message)