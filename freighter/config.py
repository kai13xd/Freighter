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

FILE_NOT_EXISTS = f"Freighter could not find the file: {WARN_COLOR}'{INFO_COLOR}"


def file_exists(path: str | Path, throw=False) -> str:
    path = Path(path)
    if isfile(path):
        return normpath(path).replace("\\", "/")
    if throw:
        raise FreighterException(FILE_NOT_EXISTS + f"{path}{WARN_COLOR}'")
    else:
        print(FILE_NOT_EXISTS + f"{path}{WARN_COLOR}'")
    return ""


DIR_NOT_EXISTS = f"Freighter could not find the folder {WARN_COLOR}'{INFO_COLOR}"


def dir_exists(path: str | Path, throw=False) -> str:
    path = Path(path)
    if isdir(path):
        return join(normpath(path), "").replace("\\", "/")
    if throw:
        raise FreighterException(DIR_NOT_EXISTS + f"{path}{WARN_COLOR}'")
    else:
        print(DIR_NOT_EXISTS + f"{path}{WARN_COLOR}'")
    return ""


@dataclass
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

    @classmethod
    def load(cls, reset: bool = False) -> None:
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
            exit(0)

    @classmethod
    def set_binutils(cls):
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
                        cls.DevKitProPath = path
                        cls.set_binutils()
                        return
        elif PLATFORM == "Linux":
            expected_path = f"/opt/devkitpro/devkitPPC/bin/"
            cls.DevKitProPath = expected_path
            cls.set_binutils()
            return

        cls.DevKitProPath = input(f"Freighter could not find your devkitPro folder. Expected to be found at {expected_path}.\n Input the path to set it:") +"/"
        cls.set_binutils()
        while not cls.verify_devkitpro():
            cls.DevKitProPath = input(f"Try again:") +"/"
            cls.set_binutils()

    @classmethod
    def find_dolphin_documents_folder(cls) -> None:
        print("Finding Dolphin user folder...")
        expected_path = ""
        if PLATFORM == "Windows":
            expected_path = str(Path.home().as_posix()) + "/Documents/Dolphin Emulator/"
            cls.DolphinUserPath = dir_exists(expected_path)
            cls.DolphinMaps = cls.DolphinUserPath + "Maps/"
            return
        elif PLATFORM == "Linux":
            expected_path = "/.local/share/dolphin-emu/"
            cls.DolphinUserPath = str(Path.home().as_posix()) + expected_path
            cls.DolphinMaps = cls.DolphinUserPath + "Maps/"
            return
        cls.DolphinUserPath = input(f"Freighter could not find your Dolphin folder. Expected to be found at {expected_path}.\n Input the path to set it:") +"/"
        while not cls.verify_dolphin():
            cls.DolphinUserPath = input("Try again:") +"/"

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
class ProjectProfile:
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


class FreighterConfig:
    default_project: ProjectProfile
    project: ProjectProfile
    profiles = dict[str, ProjectProfile]()
    project_toml_path: str

    @classmethod
    def load(cls, project_toml_path: str = ""):
        cls.project_toml_path = project_toml_path
        if not project_toml_path:
            cls.project_toml_path = file_exists(DEFAULT_CONFIG_PATH, True)

        with open(cls.project_toml_path, "rb") as f:
            tomlconfig = tomllib.load(f)

        for name, profile in tomlconfig["ProjectProfile"].items():
            cls.profiles[name] = from_dict(data_class=ProjectProfile, data=profile)

        # Set the default profile as the first entry in the TOML
        cls.default_project = next(iter(cls.profiles.values()))

    @classmethod
    def set_project_profile(cls, profile_name: str) -> None:
        if profile_name == "Default":
            cls.project = cls.default_project
        else:
            cls.project = cls.profiles[profile_name]
        cls.project.verify_paths()
