from __future__ import annotations

import re
from datetime import datetime
from functools import wraps
import time
from io import TextIOWrapper
from typing import Any, Callable
from freighter import __version__
from freighter.ansicolor import AnsiAttribute, AnsiTrueColor
from freighter.path import DirectoryPath
from enum import Enum
import cProfile
import sys
import threading

WHITE = AnsiTrueColor(255, 255, 255)
CYAN = AnsiTrueColor(35, 220, 212)
YELLOW = AnsiTrueColor(230, 230, 0)
ORANGE = AnsiTrueColor(245, 200, 67)
RED = AnsiTrueColor(255, 77, 88)
GREEN = AnsiTrueColor(78, 242, 91)
PURPLE = AnsiTrueColor(143, 148, 255)
MAGENTA = AnsiTrueColor(240, 117, 240)
HOCOTATE_RED = AnsiTrueColor(251, 58, 43)
HOCOTATE_BEIGE = AnsiTrueColor(240, 217, 136)

COMPILING = f"🛠️{AnsiAttribute.BOLD}{ORANGE}Compiling{AnsiAttribute.RESET}"
ERROR = f"🚫{AnsiAttribute.BOLD}{RED} Error  {AnsiAttribute.RESET}"
SUCCESS = f"✅{AnsiAttribute.BOLD}{GREEN} Success{AnsiAttribute.RESET}"
LINKING = f"📦{AnsiAttribute.BOLD}{GREEN} Linking{AnsiAttribute.RESET}"
LINKED = f"✅{AnsiAttribute.BOLD}{GREEN} Linked{AnsiAttribute.RESET}"
ANALYZING = f"🔎{AnsiAttribute.BOLD}{ORANGE} Analyzing{AnsiAttribute.RESET}"

FREIGHTER_LOG_FOLDER = DirectoryPath.expandvars("%LOCALAPPDATA%/Freighter/logs")
FREIGHTER_LOG_FOLDER.create()


class LogLevel(Enum):
    Info = 0
    Debug = 1
    Warning = 2
    Error = 3
    Exception = 4
    Performance = 5


LogPrefix = {
    LogLevel.Info: ["[Info]", f"{AnsiAttribute.BOLD}[{CYAN}Info{AnsiAttribute.RESET}]{CYAN}"],
    LogLevel.Debug: ["[Debug]", f"{AnsiAttribute.BOLD}[{MAGENTA}Debug{AnsiAttribute.RESET}]{MAGENTA}"],
    LogLevel.Warning: ["[Warn]", f"{AnsiAttribute.BOLD}[{ORANGE}Warn{AnsiAttribute.RESET}]{ORANGE}"],
    LogLevel.Error: ["[Error]", f"{AnsiAttribute.BOLD}[{RED}Error{AnsiAttribute.RESET}]{RED}"],
    LogLevel.Exception: ["[Exception]", f"{AnsiAttribute.BOLD}[{RED}Exception{AnsiAttribute.RESET}]{RED}"],
    LogLevel.Performance: ["[Performance]", f"{AnsiAttribute.BOLD}[{PURPLE}Performance{AnsiAttribute.RESET}]{PURPLE}"],
}

RE_STRING = re.compile(r'"(.*?)"')
RE_STRING2 = re.compile(r"'(.*?)'")
RE_REPLACE_STRING = rf'{ORANGE}"{CYAN}\1{ORANGE}"{AnsiAttribute.RESET}'
RE_REPLACE_STRING2 = rf"{ORANGE}'{CYAN}\1{ORANGE}'{AnsiAttribute.RESET}"
RE_HEX = re.compile(r"(0[xX])([0-9a-fA-F]+)")
RE_REPLACE_HEX = rf"{CYAN}\1{GREEN}\2{AnsiAttribute.RESET}"
RE_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", re.VERBOSE)


class Logger:
    enabled_logs: set[LogLevel]
    start_time: datetime = datetime.utcnow()
    log_name: str = ""
    _log: TextIOWrapper | None = None

    @staticmethod
    def __init__(enabled_logs: set[LogLevel]):
        Logger.enabled_logs = enabled_logs
        date_string = Logger.start_time.strftime("%Y-%m-%d_%H-%M-%S")
        Logger.log_name = f"Freighter-{__version__}_{date_string}.log"
        Logger._log = FREIGHTER_LOG_FOLDER.make_filepath(Logger.log_name).open_as_text()

    @staticmethod
    def format(loglevel: LogLevel, obj: Any) -> tuple[str, str]:
        delta_time = Logger.get_delta_time()
        log_string = str(obj)

        # Colorize print string
        print_string = RE_STRING.sub(RE_REPLACE_STRING, log_string)
        print_string = RE_STRING2.sub(RE_REPLACE_STRING2, print_string)
        print_string = RE_HEX.sub(RE_REPLACE_HEX, print_string)

        # Remove ansi escapes for log string that are written to file
        log_string = RE_ANSI_ESCAPE.sub("", f"{log_string}")

        # Prefix the log strings
        log_prefix, print_prefix = LogPrefix[loglevel]

        log_string = f"{delta_time} {log_prefix} {log_string}\n"
        print_string = f"{delta_time} {print_prefix} {print_string}{AnsiAttribute.RESET}\n"

        return print_string, log_string

    @staticmethod
    def get_delta_time():
        seconds = (datetime.utcnow() - Logger.start_time).total_seconds()
        hours = int(seconds // 3600)
        seconds -= hours
        minutes = int(seconds // 60)
        seconds = seconds - minutes
        return f"{hours:02}:{minutes:02}:{seconds:.3f}"

    @staticmethod
    def info(obj: Any) -> None:
        if not Logger._log or LogLevel.Info not in Logger.enabled_logs:
            return
        print_string, log_string = Logger.format(LogLevel.Info, obj)
        sys.stdout.write(print_string)
        Logger._log.write(log_string)

    @staticmethod
    def debug(obj: Any) -> None:
        if not Logger._log or LogLevel.Debug not in Logger.enabled_logs:
            return
        print_string, log_string = Logger.format(LogLevel.Debug, obj)
        sys.stdout.write(print_string)
        Logger._log.write(log_string)

    @staticmethod
    def warn(obj: Any) -> None:
        if not Logger._log or LogLevel.Warning not in Logger.enabled_logs:
            return
        print_string, log_string = Logger.format(LogLevel.Warning, obj)
        sys.stdout.write(print_string)
        Logger._log.write(log_string)

    @staticmethod
    def error(obj: Any) -> None:
        if not Logger._log or LogLevel.Error not in Logger.enabled_logs:
            return
        print_string, log_string = Logger.format(LogLevel.Error, obj)
        sys.stdout.write(print_string)
        Logger._log.write(log_string)

    @staticmethod
    def exception(obj: Any) -> None:
        if not Logger._log or LogLevel.Exception not in Logger.enabled_logs:
            return
        print_string, log_string = Logger.format(LogLevel.Exception, obj)
        sys.stdout.write(print_string)
        Logger._log.write(log_string)

    @staticmethod
    def performance(obj: Any) -> None:
        if not Logger._log or LogLevel.Performance not in Logger.enabled_logs:
            return
        print_string, log_string = Logger.format(LogLevel.Performance, obj)
        sys.stdout.write(print_string)
        Logger._log.write(log_string)


from typing import Callable, ParamSpec, Concatenate, TypeVar

Parameters = ParamSpec("Parameters")
ReturnType = TypeVar("ReturnType")
Function = Callable[Parameters, ReturnType]
DecoratedFunction = Callable[Concatenate[str, Parameters], ReturnType]


def performance_profile(function: Function) -> DecoratedFunction | Function:
    from freighter.arguments import Arguments

    # Create a wrapper if profiling is enabled other return the method
    if Arguments.profiler:
        if Arguments.extensive_profiling:

            def extensive_profiling_wrapper(*args, **kwargs):
                Logger.performance(f"Profiling {function.__module__}.{function.__qualname__}...")
                profiler = cProfile.Profile()
                result = profiler.runcall(function, *args, **kwargs)
                Logger.performance(f"{function.__qualname__} in module {function.__module__}\n")
                profiler.print_stats(sort="cumtime")
                return result

            return extensive_profiling_wrapper
        else:

            def profiling_wrapper(*args, **kwargs):
                Logger.performance(f"Profiling {function.__module__}.{function.__qualname__}...")
                start_time = time.perf_counter()
                result = function(*args, **kwargs)
                total_time = time.perf_counter() - start_time
                Logger.performance(f"{function.__module__}.{function.__qualname__} took {total_time:.6f} seconds to run.\n")
                return result

            return profiling_wrapper

    else:
        return function
