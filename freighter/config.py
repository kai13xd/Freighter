import tomllib
import os
from dataclasses import dataclass
from typing import Optional
from dacite import from_dict
from platform import system
from os.path import isdir, isfile
from pathlib import Path
from .constants import *


def assert_file_exists(path: str) -> str:
    if isfile(path):
        return path
    raise Exception(f"{FLRED}Freighter could not find the file: '{FLCYAN + path + FLRED}'")


def assert_dir_exists(path: str) -> str:
    if isdir(path):
        return path
    raise Exception(f"{FLRED}Freighter could not find the folder '{FLCYAN + path + FLRED}'")


@dataclass
class UserEnvironment:
    UseProjectProfile: str = ""
    DevKitPPCPath: Optional[str] = ""
    DolphinDocumentsPath: Optional[str] = ""


@dataclass
class CompilerArgs:
    CommonArgs: Optional[list[str]]
    GCCArgs: Optional[list[str]]
    GPPArgs: Optional[list[str]]
    LDArgs: Optional[list[str]]


@dataclass
class ProjectProfile:
    # Required
    Name: str
    GameID: str
    InputDolFile: str

    # Optional
    SDA: Optional[int]
    SDA2: Optional[int]
    InjectionAddress: Optional[int]
    SymbolMapOutputPaths: Optional[list[str]]
    LinkerScripts: Optional[list[str]]
    IncludeFolders: Optional[list[str]]
    SourceFolders: Optional[list[str]]
    CommonArgs: Optional[list[str]]
    GCCArgs: Optional[list[str]]
    GPPArgs: Optional[list[str]]
    LDArgs: Optional[list[str]]
    IgnoredSourceFiles: Optional[list[str]]
    OutputDolFile = "build/sys/main.dol"
    EntryFunction: Optional[str] = ""
    VerboseOutput: Optional[bool] = False
    InputSymbolMap: Optional[str] = ""
    BuildPath: Optional[str] = "build/"
    TemporaryFilesFolder: str = "build/temp/"
    GeckoFolder: Optional[str] = "gecko/"
    SymbolsFolder: Optional[str] = "symbols/"
    AutoImport: Optional[bool] = True
    CleanUpTemporaryFiles: Optional[bool] = True


class FreighterConfig:
    user: str = os.getlogin()
    project_profile: ProjectProfile
    user_env: UserEnvironment
    project_profiles = dict[str, ProjectProfile]()
    user_environments = dict[str, UserEnvironment]()

    def __init__(self, toml_filepath: str) -> None:
        with open(assert_file_exists(toml_filepath), "rb") as f:
            tomlconfig = tomllib.load(f)

            if "UserEnvironment" in tomlconfig.keys():
                for name, user_env in tomlconfig["UserEnvironment"].items():
                    self.user_environments[name] = from_dict(data_class=UserEnvironment, data=user_env)
            else:
                self.user_env = UserEnvironment()
            for name, profile in tomlconfig["ProjectProfile"].items():
                self.project_profiles[name] = from_dict(data_class=ProjectProfile, data=profile)

            self.user_env.UseProjectProfile = default_profile_name = tomlconfig["DefaultProjectProfile"]
            if self.user_environments:
                self.user_env = self.user_environments[self.user]
                user_profile_name = self.user_env.UseProjectProfile
                if user_profile_name not in self.project_profiles.keys():
                    print(f"User Project Profile '{user_profile_name}' does not exist! Using default '{default_profile_name}' instead.")
                else:
                    self.project_profile = self.project_profiles[user_profile_name]
            else:
                self.project_profile = self.project_profiles[default_profile_name]

        platform = system()
        try:
            if self.user_env.DolphinDocumentsPath:
                assert_dir_exists(self.user_env.DolphinDocumentsPath)
            else:
                if platform == "Windows":
                    self.user_env.DolphinDocumentsPath = assert_dir_exists(str(Path.home()) + "/Documents/Dolphin Emulator/")
                elif platform == "Linux":
                    self.user_env.DolphinDocumentsPath = assert_dir_exists(str(Path.home()) + "/.local/share/dolphin-emu/")
                else:
                    raise EnvironmentError(f"{platform} is not a supported environment!")
        except:
            print(
                f'{FLYELLOW}[Warning] Could not find your Dolphin Maps folder at "{FLCYAN + self.user_env.DolphinDocumentsPath + FLYELLOW}"\n'
                + f'In the "{FLCYAN + toml_filepath + FLYELLOW}" under {FLWHITE}[UserEnvironment.{self.user}]{FLYELLOW} set {FLWHITE}DolphinDocumentsPath = "{FLYELLOW}Insert corrected path{FLYELLOW}{FLWHITE}".'
            )
        try:
            if self.user_env.DevKitPPCPath:
                assert_dir_exists(self.user_env.DevKitPPCPath)
            else:
                if platform == "Windows":
                    self.user_env.DevKitPPCPath = assert_dir_exists("C:/devkitPro/devkitPPC/bin/")
                elif platform == "Linux":
                    self.user_env.DevKitPPCPath = assert_dir_exists("/opt/devkitpro/devkitPPC/bin/")
                else:
                    raise EnvironmentError(f"{platform} is not a supported environment!")
        except:
            raise EnvironmentError(
                f'{FLRED} Could not find your DevKitPPC "bin/" folder at "{FLCYAN + self.user_env.DevKitPPCPath + FLRED}"\n'
                + f'In the "{FLCYAN + toml_filepath + FLRED}" under {FLWHITE}[UserEnvironment.{self.user}]{FLRED} set {FLWHITE}DolphinDocumentsPath = "{FLYELLOW}Insert corrected path{FLRED}{FLWHITE}".'
            )
        assert_file_exists(self.user_env.DevKitPPCPath + GPP)
        assert_file_exists(self.user_env.DevKitPPCPath + GCC)
        assert_file_exists(self.user_env.DevKitPPCPath + LD)
        assert_file_exists(self.user_env.DevKitPPCPath + AR)
        assert_file_exists(self.user_env.DevKitPPCPath + OBJDUMP)
        assert_file_exists(self.user_env.DevKitPPCPath + OBJCOPY)
        assert_file_exists(self.user_env.DevKitPPCPath + NM)
        assert_file_exists(self.user_env.DevKitPPCPath + READELF)
        assert_file_exists(self.user_env.DevKitPPCPath + GBD)
        assert_file_exists(self.user_env.DevKitPPCPath + CPPFLIT)
