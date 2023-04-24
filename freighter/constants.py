from colorama import Fore, Style, init
from platform import system

init()

FRED = Fore.RED
FLRED = Fore.LIGHTRED_EX
FYELLOW = Fore.YELLOW
FLYELLOW = Fore.LIGHTYELLOW_EX
FBLUE = Fore.BLUE
FLBLUE = Fore.LIGHTBLUE_EX
FGREEN = Fore.GREEN
FLGREEN = Fore.LIGHTGREEN_EX
FWHITE = Fore.WHITE
FLWHITE = Fore.LIGHTWHITE_EX
FMAGENTA = Fore.MAGENTA
FLMAGENTA = Fore.LIGHTMAGENTA_EX
FCYAN = Fore.CYAN
FLCYAN = Fore.LIGHTCYAN_EX

COMPILING = f"{FYELLOW}🛠️ Compiling!"
ERROR = f"{FRED}❌ Error:{FLRED}"
SUCCESS = f"{FLGREEN}✔️ Success!"
LINKED = f"{FLGREEN}✔️ Linked!"
HEX = f"{FBLUE}0x{FLCYAN}"

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
DEFAULT_USERENV_PATH = "UserEnv.toml"
