import tomllib
from dataclasses import dataclass, field
from os import mkdir, remove
from os.path import isdir, isfile, join, normpath
from pathlib import Path
from dacite import from_dict

from .constants import *
from .exceptions import *

if not isdir(FREIGHTER_LOCALAPPDATA):
    mkdir(FREIGHTER_LOCALAPPDATA)


def file_exists(path: str | Path, throw=False, verbose=False) -> str:
    path = Path(path).as_posix()
    if isfile(path):
        if verbose:
            console_print(f'{ORANGE}File Found "{path}"!')
        return normpath(path).replace("\\", "/")
    if throw:
        raise FreighterException(f'The file "{path}{WARN_COLOR}" does not exist')
    else:
        console_print(f'The file "{path}{WARN_COLOR}" does not exist')
    return ""


def dir_exists(path: str | Path, throw=False, verbose=False) -> str:
    path = Path(path).as_posix()
    if isdir(path):
        if verbose:
            console_print(f'{ORANGE}Directory Found "{path}"!')
        return join(normpath(path), "").replace("\\", "/")
    if throw:
        raise FreighterException(f'The directory "{path}{WARN_COLOR}" does not exist')
    else:
        console_print(f'The directory "{path}{WARN_COLOR}" does not exist')
    return ""


class UserEnvironment:
    DevKitProPath = ""
    GPP = ""
    GCC = ""
    LD = ""
    AR = ""
    OBJDUMP = ""
    OBJCOPY = ""
    NM = ""
    READELF = ""
    GBD = ""
    CPPFLIT = ""
    DolphinUserPath = ""
    DolphinMaps = ""

    def __new__(cls, reset: bool = False) -> None:
        if reset:
            print("Resetting UserEnvironment...")
            if isfile(FREIGHTER_USERENVIRONMENT):
                remove(FREIGHTER_USERENVIRONMENT)

        if not file_exists(FREIGHTER_USERENVIRONMENT):
            cls.find_dekitppc_bin_folder()
            cls.verify_devkitpro()
            print("devKitPro path good.")
            cls.find_dolphin_documents_folder()
            cls.verify_dolphin()
            print("Dolphin User path good.")
            cls.write_toml()
        else:
            with open(FREIGHTER_USERENVIRONMENT, "rb") as f:
                for key, value in tomllib.load(f).items():
                    setattr(cls, key, value)
            cls.verify_devkitpro()
            cls.verify_dolphin()

        if reset:
            print("Finished")
            print(f"Saved to {FREIGHTER_USERENVIRONMENT}")
            exit(0)

    @classmethod
    def set_binutils(cls, devkitpro_path: str):
        cls.DevKitProPath = devkitpro_path
        cls.GPP = cls.DevKitProPath + "devkitPPC/bin/powerpc-eabi-g++.exe"
        cls.GCC = cls.DevKitProPath + "devkitPPC/bin/powerpc-eabi-gcc.exe"
        cls.LD = cls.DevKitProPath + "devkitPPC/bin/powerpc-eabi-ld.exe"
        cls.AR = cls.DevKitProPath + "devkitPPC/bin/powerpc-eabi-ar.exe"
        cls.OBJDUMP = cls.DevKitProPath + "devkitPPC/bin/powerpc-eabi-objdump.exe"
        cls.OBJCOPY = cls.DevKitProPath + "devkitPPC/bin/powerpc-eabi-objcopy.exe"
        cls.NM = cls.DevKitProPath + "devkitPPC/bin/powerpc-eabi-gcc-nm.exe"
        cls.READELF = cls.DevKitProPath + "devkitPPC/bin/powerpc-eabi-readelf.exe"
        cls.GBD = cls.DevKitProPath + "devkitPPC/bin/powerpc-eabi-gdb.exe"
        cls.CPPFLIT = cls.DevKitProPath + "devkitPPC/bin/powerpc-eabi-c++filt.exe"

    @classmethod
    def find_dekitppc_bin_folder(cls) -> None:
        print("Finding devKitPro folder...")
        expected_path = ""
        if PLATFORM == "Windows":
            expected_path = "C:/devkitPro/"
            cls.DevKitProPath = dir_exists(expected_path)
            if not cls.DevKitProPath:
                drives = ["D:", "E:", "F:", "G:", "H:", "I:", "J:", "K:", "L:", "M:", "N:", "O:", "P:", "Q:", "R:", "S:", "T:", "U:", "V:", "W:", "X:", "Y:", "Z:"]
                path = ""
                for drive in drives:
                    path = f"{drive}/devkitPro/"
                    if dir_exists(path):
                        cls.set_binutils(path)
                        return
        elif PLATFORM == "Linux":
            expected_path = f"/opt/devkitpro/devkitPPC/bin/"
            cls.set_binutils(expected_path)
            return

        cls.set_binutils(input(f"Freighter could not find your devkitPro folder. Expected to be found at {expected_path}.\n Input the path to set it:") + "/")
        while not cls.verify_devkitpro():
            cls.set_binutils(input(f"Try again:") + "/")

    @classmethod
    def set_dolphin_paths(cls, dolphin_user_path: str):
        cls.DolphinUserPath = dolphin_user_path
        cls.DolphinMaps = cls.DolphinUserPath + "Maps/"

    @classmethod
    def find_dolphin_documents_folder(cls) -> None:
        print("Finding Dolphin user folder...")
        expected_path = ""
        if PLATFORM == "Windows":
            expected_path = str(Path.home().as_posix()) + "/Documents/Dolphin Emulator/"
            cls.set_dolphin_paths(dir_exists(expected_path))
            return
        elif PLATFORM == "Linux":
            expected_path = "/.local/share/dolphin-emu/"
            cls.set_dolphin_paths(str(Path.home().as_posix()) + expected_path)
            return
        cls.set_dolphin_paths(input(f"Freighter could not find your Dolphin User folder. Expected to be found at {expected_path}.\n Input the path to set it:") + "/")
        while not cls.verify_dolphin():
            cls.set_dolphin_paths(input("Try again:") + "/")

    @classmethod
    def verify_devkitpro(cls) -> bool:
        if not dir_exists(cls.DevKitProPath):
            return False
        # If these fail then something got deleted or moved from the bin folder
        try:
            file_exists(cls.GPP, True)
            file_exists(cls.GCC, True)
            file_exists(cls.LD, True)
            file_exists(cls.AR, True)
            file_exists(cls.OBJDUMP, True)
            file_exists(cls.OBJCOPY, True)
            file_exists(cls.NM, True)
            file_exists(cls.READELF, True)
            file_exists(cls.GBD, True)
            file_exists(cls.CPPFLIT, True)

        except:
            print("This doesn't seem right. All or some binutils executables were not not found.")
            return False
        return True

    @classmethod
    def verify_dolphin(cls) -> bool:
        if not dir_exists(cls.DolphinUserPath):
            return False
        try:
            dir_exists(cls.DolphinMaps, True)

        except:
            print("This doesn't seem right. Maps folder was not found.")
            return False
        return True

    @classmethod
    def write_toml(cls) -> None:
        cls_vars = {key: value for key, value in cls.__dict__.items() if not key.startswith("__") and not isinstance(value, classmethod)}
        with open(FREIGHTER_USERENVIRONMENT, "w+") as f:
            for key, value in cls_vars.items():
                f.write(f'{key} = "{value}"\n')


@dataclass
class Profile:
    ProjectName: str
    GameID: str
    InjectionAddress: int
    InputDolFile: str
    OutputDolFile: str
    IncludeFolders: list[str]
    SourceFolders: list[str]

    # Optional
    DefaultProjectProfile: str = ""
    SDA: int = 0
    SDA2: int = 0
    GeckoFolder: str = "gecko/"
    SymbolsFolder: str = ""
    LinkerScripts: list[str] = field(default_factory=list[str])
    TemporaryFilesFolder: str = field(default="temp/")
    InputSymbolMap: str = ""
    OutputSymbolMapPaths: list[str] = field(default_factory=list[str])
    StringHooks: dict[str, str] = field(default_factory=dict[str, str])
    CleanUpTemporaryFiles: bool = False
    VerboseOutput: bool = False

    IgnoredSourceFiles: list[str] = field(default_factory=list[str])
    IgnoredGeckoFiles: list[str] = field(default_factory=list[str])
    IgnoreHooks: list[str] = field(default_factory=list[str])
    DiscardLibraryObjects: list[str] = field(default_factory=list[str])
    DiscardSections: list[str] = field(default_factory=list[str])

    CompilerArgs: list[str] = field(default_factory=list[str])
    GCCArgs: list[str] = field(default_factory=list[str])
    GPPArgs: list[str] = field(default_factory=list[str])
    LDArgs: list[str] = field(default_factory=list[str])

    def verify_paths(self):
        file_exists(self.InputDolFile)
        file_exists(self.InputSymbolMap)
        for folder in self.IncludeFolders:
            dir_exists(folder)
        for folder in self.SourceFolders:
            dir_exists(folder)
        dir_exists(self.GeckoFolder)

        if self.SymbolsFolder:
            dir_exists(self.SymbolsFolder)
        for file in self.LinkerScripts:
            file_exists(file)


@dataclass
class Banner:
    BannerImage: str
    Title: str
    GameName: str
    Maker: str
    ShortMaker: str
    Description: str
    OutputPath: str


class FreighterConfig:
    banner_config: Banner
    default_project: Profile
    profile: Profile
    profiles = dict[str, Profile]()
    project_toml_path: str

    @classmethod
    def __init__(cls, project_toml_path: str = ""):
        cls.profiles
        cls.project_toml_path = project_toml_path
        if not project_toml_path:
            cls.project_toml_path = file_exists(DEFAULT_CONFIG_PATH, True)

        with open(cls.project_toml_path, "rb") as f:
            tomlconfig = tomllib.load(f)

        cls.banner_config = from_dict(data_class=Banner,data=tomlconfig["Banner"])

        for name, profile in tomlconfig["Profile"].items():
            cls.profiles[name] = from_dict(data_class=Profile, data=profile)

        # Set the default profile as the first entry in the TOML
        cls.default_project = next(iter(cls.profiles.values()))
        cls.profile = cls.default_project

    @classmethod
    def set_project_profile(cls, profile_name: str) -> None:
        if profile_name == "Default" or profile_name == None:
            cls.profile = cls.default_project
        else:
            cls.profile = cls.profiles[profile_name]
        cls.profile.verify_paths()
