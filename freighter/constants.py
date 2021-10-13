from platform import system
from colorama import Fore, Style, init

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
HEX = f"{FWHITE}0x{FLWHITE}"
# Default Paths
PLATFORM = system()
if PLATFORM == "Windows":
    DEVKITPPC = "C:/devkitPro/devkitPPC/bin/"
elif PLATFORM == "Linux":
    DEVKITPPC = "/opt/devkitpro/devkitPPC/bin/"
else:
    raise EnvironmentError(f"{PLATFORM} is not supported !")

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
