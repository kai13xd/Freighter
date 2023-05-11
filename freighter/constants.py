from platform import system
from .ansicolor import *
from os import path
from pathlib import Path
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

PLATFORM = system()

GPP = "powerpc-eabi-g++.exe"
GCC = "powerpc-eabi-gcc.exe"
LD = "powerpc-eabi-ld.exe"
AR = "powerpc-eabi-ar.exe"
OBJDUMP = "powerpc-eabi-objdump.exe"
OBJCOPY = "powerpc-eabi-objcopy.exe"
NM = "powerpc-eabi-gcc-nm.exe"
READELF = "powerpc-eabi-readelf.exe"
GBD = "powerpc-eabi-gdb.exe"
CPPFLIT = "powerpc-eabi-c++filt.exe"

DEFAULT_CONFIG_PATH = "ProjectConfig.toml"


FREIGHTER_LOCALAPPDATA = path.expandvars("%LOCALAPPDATA%/Freighter/")
FREIGHTER_USERENVIRONMENT = FREIGHTER_LOCALAPPDATA + "UserEnvironment.toml"
DRIVES = [f"{drive}:" for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ"]

import setuptools_scm