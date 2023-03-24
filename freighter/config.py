import tomllib
import os
from dataclasses import dataclass, field
from dacite import from_dict
from platform import system
from os.path import isdir, isfile, normpath, join
from pathlib import Path
from .constants import *


def assert_file_exists(path: str) -> str:
    if isfile(path):
        return normpath(path).replace("\\", "/")
    raise Exception(f"{FLRED}Freighter could not find the file: '{FLCYAN + path + FLRED}'")


def assert_dir_exists(path: str) -> str:
    if isdir(path):
        return join(normpath(path), "").replace("\\", "/")
    raise Exception(f"{FLRED}Freighter could not find the folder '{FLCYAN + path + FLRED}'")


PLATFORM = system()


@dataclass(frozen=True)
class UserEnvironment:
    DevKitPPCBinFolder: str = field(default="")
    DolphinDocumentsFolder: str = field(default="")

    def __post_init__(self):
        if not self.DolphinDocumentsFolder:
            self.find_dolphin_documents_folder()
        else:
            object.__setattr__(self,"DolphinDocumentsFolder", assert_dir_exists(self.DolphinDocumentsFolder))
        if not self.DevKitPPCBinFolder:
            self.find_dekitppc_bin_folder()
        else:
            object.__setattr__(self,"DevKitPPCBinFolder", assert_dir_exists(self.DevKitPPCBinFolder))
            assert_file_exists(self.DevKitPPCBinFolder + GPP)
            assert_file_exists(self.DevKitPPCBinFolder + GCC)
            assert_file_exists(self.DevKitPPCBinFolder + LD)
            assert_file_exists(self.DevKitPPCBinFolder + AR)
            assert_file_exists(self.DevKitPPCBinFolder + OBJDUMP)
            assert_file_exists(self.DevKitPPCBinFolder + OBJCOPY)
            assert_file_exists(self.DevKitPPCBinFolder + NM)
            assert_file_exists(self.DevKitPPCBinFolder + READELF)
            assert_file_exists(self.DevKitPPCBinFolder + GBD)
            assert_file_exists(self.DevKitPPCBinFolder + CPPFLIT)

    def find_dekitppc_bin_folder(self):
        try:
            if PLATFORM == "Windows":
                object.__setattr__(self,"DevKitPPCBinFolder", assert_dir_exists("C:/devkitPro/devkitPPC/bin/"))
            elif PLATFORM == "Linux":
                object.__setattr__(self,"DevKitPPCBinFolder", assert_dir_exists("/opt/devkitpro/devkitPPC/bin/"))
            else:
                raise EnvironmentError(f"{PLATFORM} is not a supported environment!")
        except:
            raise EnvironmentError(f'{FLRED} Could not find your DevKitPPC "bin/" folder"\n')

    def find_dolphin_documents_folder(self):
        try:
            if PLATFORM == "Windows":
                object.__setattr__(self, "DolphinDocumentsPath", assert_dir_exists(str(Path.home()) + "/Documents/Dolphin Emulator/"))
            elif PLATFORM == "Linux":
                object.__setattr__(self, "DolphinDocumentsPath", str(Path.home()) + "/.local/share/dolphin-emu/")
            else:
                raise EnvironmentError(f"{PLATFORM} is not a supported environment!")
        except:
            print(f'{FLYELLOW}[Warning] Could not find your Dolphin Maps folder')




@dataclass()
class ProjectProfile:
    # Required
    Name: str
    GameID: str
    InputDolFile: str
    OutputDolFile: str
    InjectionAddress: int

    # Optional
    SDA: int
    SDA2: int
    CommonArgs: list[str] = field(default_factory=list[str])
    GCCArgs: list[str] = field(default_factory=list[str])
    GPPArgs: list[str] = field(default_factory=list[str])
    LDArgs: list[str] = field(default_factory=list[str])
    IncludeFolders: list[str] = field(default_factory=list[str])
    SourceFolders: list[str] = field(default_factory=list[str])
    SymbolMapOutputPaths: list[str] = field(default_factory=list[str])
    LinkerScripts: list[str] = field(default_factory=list[str])
    IgnoredSourceFiles: list[str] = field(default_factory=list[str])
    TemporaryFilesFolder: str = field(default="build/temp/")
    EntryFunction: str = ""
    VerboseOutput: bool = False
    InputSymbolMap: str = ""
    BuildPath: str = field(default="build/")
    GeckoFolder: str = field(default="gecko/")
    SymbolsFolder: str = field(default="symbols/")
    AutoImport: bool = True
    CleanUpTemporaryFiles: bool = True


class FreighterConfig:
    project_profile: ProjectProfile
    user_env: UserEnvironment
    project_profiles = dict[str, ProjectProfile]()

    def __init__(self, project_toml_filepath: str, userenv_toml_filepath: str = "") -> None:
        with open(assert_file_exists(project_toml_filepath), "rb") as f:
            tomlconfig = tomllib.load(f)
            for name, profile in tomlconfig["ProjectProfile"].items():
                self.project_profiles[name] = from_dict(data_class=ProjectProfile, data=profile)
            default_profile_name = tomlconfig["DefaultProjectProfile"]
            self.project_profile = self.project_profiles[default_profile_name]
        if userenv_toml_filepath:
            with open(assert_file_exists(userenv_toml_filepath), "rb") as f:
                user_env = tomllib.load(f)
                self.user_env = from_dict(data_class=UserEnvironment, data=user_env)
