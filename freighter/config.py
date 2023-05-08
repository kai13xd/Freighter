import tomllib
from dataclasses import dataclass, field
from dacite import from_dict
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


@dataclass(frozen=True)
class UserEnvironment:
    SelectedProfile: str = field(default="")
    DevKitPPCBinFolder: str = field(default="")
    DolphinDocumentsFolder: str = field(default="")

    def __post_init__(self):
        if not self.DolphinDocumentsFolder:
            self.find_dolphin_documents_folder()
        else:
            object.__setattr__(self, "DolphinDocumentsFolder", assert_dir_exists(self.DolphinDocumentsFolder))
        if not self.DevKitPPCBinFolder:
            self.find_dekitppc_bin_folder()
        else:
            object.__setattr__(self, "DevKitPPCBinFolder", assert_dir_exists(self.DevKitPPCBinFolder))
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
                path = ""
                drives = [f"{drive}:" for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ"]
                for drive in drives:
                    path = f"{drive}/devkitPro/devkitPPC/bin/"
                    if isdir(path):
                        break
                    else:
                        path = ""
                object.__setattr__(self, "DevKitPPCBinFolder", assert_dir_exists(path))
            elif PLATFORM == "Linux":
                object.__setattr__(self, "DevKitPPCBinFolder", assert_dir_exists("/opt/devkitpro/devkitPPC/bin/"))
            else:
                raise EnvironmentError(f"{PLATFORM} is not a supported environment!")
        except:
            raise EnvironmentError(f'{FLRED} Could not find your DevKitPPC "bin/" folder"\n')

    def find_dolphin_documents_folder(self):
        try:
            if PLATFORM == "Windows":
                object.__setattr__(self, "DolphinDocumentsFolder", assert_dir_exists(str(Path.home()) + "/Documents/Dolphin Emulator/"))
            elif PLATFORM == "Linux":
                object.__setattr__(self, "DolphinDocumentsFolder", str(Path.home()) + "/.local/share/dolphin-emu/")
            else:
                raise EnvironmentError(f"{PLATFORM} is not a supported environment!")
        except:
            print(f"{FLYELLOW}[Warning] Could not find your Dolphin Maps folder")


@dataclass()
class ProjectProfile:
    # Required
    ProjectName: str
    GameID: str
    InjectionAddress: int
    InputDolFile: str
    OutputDolFile: str
    IncludeFolders: list[str]
    SourceFolders: list[str]

    # Optional
    SDA: int = 0
    SDA2: int = 0
    GeckoFolder: str = field(default="gecko/")
    SymbolsFolder: str = field(default="symbols/")
    LinkerScripts: list[str] = field(default_factory=list[str])
    TemporaryFilesFolder: str = field(default="temp/")
    InputSymbolMap: str = ""
    OutputSymbolMapPaths: list[str] = field(default_factory=list[str])

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

    def __repr__(self) -> str:
        return self.ProjectName


class FreighterConfig:
    project: ProjectProfile
    user_env: UserEnvironment
    config_path: str

    def __init__(self, project_toml_path: str = "", userenv_toml_path: str = "") -> None:
        FreighterConfig.project_profiles = dict[str, ProjectProfile]()

        if not project_toml_path:
            FreighterConfig.config_path = assert_file_exists(DEFAULT_CONFIG_PATH)

        if not userenv_toml_path:
            userenv_toml_path = assert_file_exists(DEFAULT_USERENV_PATH)

        with open(FreighterConfig.config_path, "rb") as f:
            tomlconfig = tomllib.load(f)
            for name, profile in tomlconfig["ProjectProfile"].items():
                FreighterConfig.project_profiles[name] = from_dict(data_class=ProjectProfile, data=profile)
            default_profile_name = tomlconfig["DefaultProjectProfile"]
            FreighterConfig.project = FreighterConfig.project_profiles[default_profile_name]

        if userenv_toml_path:
            with open(userenv_toml_path, "rb") as f:
                user_env = tomllib.load(f)
                FreighterConfig.user_env = from_dict(data_class=UserEnvironment, data=user_env)
                if FreighterConfig.user_env.SelectedProfile:
                    FreighterConfig.project = FreighterConfig.project_profiles[FreighterConfig.user_env.SelectedProfile]
        else:
            FreighterConfig.user_env = UserEnvironment()

        # Use the ProjectName as the base directory
        # os.chdir(project_name) # This seems to mess up spawning child processes

        project_name = FreighterConfig.project.ProjectName
        
        FreighterConfig.project.InputDolFile = assert_file_exists(f"{project_name}/{FreighterConfig.project.InputDolFile}")
        FreighterConfig.project.InputSymbolMap = assert_file_exists(f"{project_name}/{FreighterConfig.project.InputSymbolMap}")
        FreighterConfig.project.SourceFolders = [i.replace(i, assert_dir_exists(f"{project_name}/{i}")) for i in FreighterConfig.project.SourceFolders]
        FreighterConfig.project.IncludeFolders = [i.replace(i, assert_dir_exists(f"{project_name}/{i}")) for i in FreighterConfig.project.IncludeFolders]
        
        FreighterConfig.project.GeckoFolder = f"{project_name}/{FreighterConfig.project.GeckoFolder}"
        FreighterConfig.project.SymbolsFolder = f"{project_name}/{FreighterConfig.project.SymbolsFolder}"

        FreighterConfig.project.TemporaryFilesFolder = f"{project_name}/{FreighterConfig.project.TemporaryFilesFolder}"
        FreighterConfig.project.OutputDolFile = f"{project_name}/{FreighterConfig.project.OutputDolFile}"
        FreighterConfig.project.LinkerScripts = [i.replace(i, assert_file_exists(f"{project_name}/{i}")) for i in FreighterConfig.project.LinkerScripts]

        FreighterConfig.project.IgnoredSourceFiles = [i.replace(i, f"{project_name}/{i}") for i in FreighterConfig.project.IgnoredSourceFiles]

        from .filelist import FileList, File

        FileList.init()
        File(FreighterConfig.config_path)


# Singleton init
FreighterConfig()
