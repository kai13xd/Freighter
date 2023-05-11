from .constants import *
from .exceptions import *
import tomllib
from dataclasses import dataclass, field
from os.path import isdir, isfile, normpath, join
from os import mkdir
from pathlib import Path
from dacite import from_dict

if not isdir(FREIGHTER_LOCALAPPDATA):
    mkdir(FREIGHTER_LOCALAPPDATA)


def assert_file_exists(path: str | Path) -> str:
    path = Path(path)
    if isfile(path):
        return normpath(path).replace("\\", "/")
    raise FreighterException(
        f"Freighter could not find the file: {WARN_COLOR}'{INFO_COLOR}{path}{WARN_COLOR}'")


def assert_dir_exists(path: str | Path) -> str:
    path = Path(path)
    path = path.absolute()
    if isdir(path):
        return join(normpath(path), "").replace("\\", "/")
    raise FreighterException(
        f"Freighter could not find the folder {WARN_COLOR}'{INFO_COLOR}{path}{WARN_COLOR}'")


class UserEnvironment:
    DevKitPPCBinFolder: str = ""
    DolphinDocumentsFolder: str = ""

    @classmethod
    def load(cls, userenv_toml_path: str = "") -> None:
        if not userenv_toml_path:
            if not isfile(FREIGHTER_USERENVIRONMENT):
                cls.find_dekitppc_bin_folder()
                cls.find_dolphin_documents_folder()
                with open(FREIGHTER_USERENVIRONMENT, "w+") as f:
                    f.write(
                        f'DevKitPPCBinFolder = "{cls.DevKitPPCBinFolder}"\n')
                    f.write(
                        f'DolphinDocumentsFolder = "{cls.DolphinDocumentsFolder}"\n')
                    return
                
            userenv_toml_path = assert_file_exists(FREIGHTER_USERENVIRONMENT)
        with open(userenv_toml_path, "rb") as f:
            data = tomllib.load(f)
            if "DevKitPPCBinFolder" in data.keys():
                cls.DevKitPPCBinFolder = data["DevKitPPCBinFolder"]
            if "DolphinDocumentsFolder" in data.keys():
                cls.DolphinDocumentsFolder = data["DolphinDocumentsFolder"]
        cls.verify_paths()

    @classmethod
    def verify_paths(cls) -> None:
        if not cls.DolphinDocumentsFolder:
            cls.find_dolphin_documents_folder()
        else:
            cls.DolphinDocumentsFolder = assert_dir_exists(
                cls.DolphinDocumentsFolder)
        if not cls.DevKitPPCBinFolder:
            cls.find_dekitppc_bin_folder()
        else:
            cls.DevKitPPCBinFolder = assert_dir_exists(cls.DevKitPPCBinFolder)
            assert_file_exists(cls.DevKitPPCBinFolder + GPP)
            assert_file_exists(cls.DevKitPPCBinFolder + GCC)
            assert_file_exists(cls.DevKitPPCBinFolder + LD)
            assert_file_exists(cls.DevKitPPCBinFolder + AR)
            assert_file_exists(cls.DevKitPPCBinFolder + OBJDUMP)
            assert_file_exists(cls.DevKitPPCBinFolder + OBJCOPY)
            assert_file_exists(cls.DevKitPPCBinFolder + NM)
            assert_file_exists(cls.DevKitPPCBinFolder + READELF)
            assert_file_exists(cls.DevKitPPCBinFolder + GBD)
            assert_file_exists(cls.DevKitPPCBinFolder + CPPFLIT)

    @classmethod
    def find_dekitppc_bin_folder(cls) -> None:
        if PLATFORM == "Windows":
            path = ""
            for drive in DRIVES:
                path = f"{drive}/devkitPro/devkitPPC/bin/"
                if isdir(path):
                    break
                else:
                    path = ""
            cls.DevKitPPCBinFolder = assert_dir_exists(path)
        elif PLATFORM == "Linux":
            cls.DevKitPPCBinFolder = "/opt/devkitpro/devkitPPC/bin/"
        else:
            raise EnvironmentError(
                f"{PLATFORM} is not a supported environment!")

    @classmethod
    def find_dolphin_documents_folder(cls) -> None:
        if PLATFORM == "Windows":
            cls.DolphinDocumentsFolder = assert_dir_exists(
                str(Path.home()) + "/Documents/Dolphin Emulator/")
        elif PLATFORM == "Linux":
            cls.DolphinDocumentsFolder = str(
                Path.home()) + "/.local/share/dolphin-emu/"
        else:
            raise FreighterException(
                f"{PLATFORM} is not a supported environment!")


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
        assert_file_exists(self.InputDolFile)
        assert_file_exists(self.InputSymbolMap)
        for folder in self.IncludeFolders:
            assert_dir_exists(folder)
        for folder in self.SourceFolders:
            assert_dir_exists(folder)
        assert_dir_exists(self.GeckoFolder)

        if self.SymbolsFolder:
            assert_dir_exists(self.SymbolsFolder)
        for file in self.LinkerScripts:
            assert_file_exists(file)


class FreighterConfig():
    default_project: ProjectProfile
    project: ProjectProfile
    profiles = dict[str, ProjectProfile]()
    project_toml_path: str

    @classmethod
    def load(cls, project_toml_path: str = ""):
        cls.project_toml_path = project_toml_path
        if not project_toml_path:
            cls.project_toml_path = assert_file_exists(DEFAULT_CONFIG_PATH)

        with open(cls.project_toml_path, "rb") as f:
            tomlconfig = tomllib.load(f)

        for name, profile in tomlconfig["ProjectProfile"].items():
            cls.profiles[name] = from_dict(
                data_class=ProjectProfile, data=profile)

        # Set the default profile as the first entry in the TOML
        cls.default_project = next(iter(cls.profiles.values()))

    @classmethod
    def set_project_profile(cls, profile_name: str) -> None:
        if profile_name == "Default":
            cls.project = cls.default_project
        else:
            cls.project = cls.profiles[profile_name]
        cls.project.verify_paths()
