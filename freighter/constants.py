from glob import glob
from os import remove, removedirs
from os.path import isdir, isfile
from pathlib import Path
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


def assert_file_exists(path: str) -> str:
    if isfile(path):
        return path
    raise Exception(
        f"{FLRED}Freighter could not find the file: '{FLCYAN+path+FLRED}'")


def assert_dir_exists(path: str) -> str:
    if isdir(path):
        return path
    raise Exception(
        f"{FLRED}Freighter could not find the folder '{FLCYAN+path+FLRED}'")


def delete_file(filepath: str) -> bool:
    try:
        remove(filepath)
        return True
    except FileNotFoundError:
        return False


def delete_dir(path: str) -> bool:
    try:
        for file in glob(path + "*", recursive=True):
            delete_file(file)
        removedirs(path)
        return True
    except FileNotFoundError:
        return False


def get_default_source_folders() -> str:
    default_paths = ["source/", "src/", "code/"]
    folders = []
    for folder in glob("*", recursive=True):
        if folder in default_paths:
            print(f'Automatically added source folder: "{folder}"')
            folders.append(folder)
    return folders


def get_default_include_folders() -> list[str]:
    default_paths = ["include/", "includes/", "headers/"]
    folders = []
    for folder in glob("*", recursive=True):
        if folder in default_paths:
            print(f'Automatically added include folder: "{folder}"')
            folders.append(folder)
    return folders


# Default Paths
PLATFORM = system()

if PLATFORM == "Windows":
    DEVKITPPC = assert_dir_exists("C:/devkitPro/devkitPPC/bin/")
elif PLATFORM == "Linux":
    DEVKITPPC = assert_dir_exists("/opt/devkitpro/devkitPPC/bin/")
else:
    DOLPHIN_MAPS = None
    raise EnvironmentError(f"DevKitPCC bin folder could not be found! please set it {PLATFORM} is not supported! ")

GPP = assert_file_exists(DEVKITPPC+"powerpc-eabi-g++.exe")
GCC = assert_file_exists(DEVKITPPC+"powerpc-eabi-gcc.exe")
LD = assert_file_exists(DEVKITPPC+"powerpc-eabi-ld.exe")
AR = assert_file_exists(DEVKITPPC+"powerpc-eabi-ar.exe")
OBJDUMP = assert_file_exists(DEVKITPPC+"powerpc-eabi-objdump.exe")
OBJCOPY = assert_file_exists(DEVKITPPC+"powerpc-eabi-objcopy.exe")
NM = assert_file_exists(DEVKITPPC+"powerpc-eabi-gcc-nm.exe")
READELF = assert_file_exists(DEVKITPPC+"powerpc-eabi-readelf.exe")
GBD = assert_file_exists(DEVKITPPC+"powerpc-eabi-gdb.exe")
CPPFLIT = assert_file_exists(DEVKITPPC+"powerpc-eabi-c++filt.exe")


if PLATFORM == "Windows":
    DOLPHIN_MAPS = str(Path.home()) + "/Documents/Dolphin Emulator/Maps/"
elif PLATFORM == "Linux":
    DOLPHIN_MAPS = str(Path.home()) + "/.local/share/dolphin-emu/Maps/"
else:
    DOLPHIN_MAPS = None
    print(f"{FYELLOW}[Warning] Could not deduce Dolphin Maps folder.\n{FWHITE}Please set the path with the{FGREEN}add_map_output{FWHITE} method.")
