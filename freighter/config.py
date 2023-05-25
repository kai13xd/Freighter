import tomllib
from dataclasses import dataclass, field
from os import chdir, remove
from os.path import isdir, isfile
from platform import system
from typing import ClassVar
from freighter.console import Console
from freighter.exceptions import FreighterException
from freighter.path import Path, DirectoryPath, FilePath
from freighter.arguments import Arguments
from freighter.toml import *
from freighter.numerics import UInt

PLATFORM = system()

DEFAULT_FOLDERS = {
    "GECKO": DirectoryPath("gecko/"),
    "SOURCE": DirectoryPath("source/"),
    "INCLUDE": DirectoryPath("include/"),
    "SYMBOLS": DirectoryPath("symbols/"),
    "BUILD": DirectoryPath("build/"),
    "TEMP": DirectoryPath("temp/"),
}

FREIGHTER_LOCALAPPDATA = DirectoryPath.expandvars("%LOCALAPPDATA%/Freighter/")
if not FREIGHTER_LOCALAPPDATA.exists():
    FREIGHTER_LOCALAPPDATA.create()
USERENVIRONMENT_PATH = FilePath(FREIGHTER_LOCALAPPDATA / "UserEnvironment.toml")
DEFAULT_PROJECT_CONFIG_NAME = str("ProjectConfig.toml")

EXPECTED_DEVKITPRO_PATHS = list[DirectoryPath]()
EXPECTED_DOLPHIN_USERPATH: DirectoryPath

if PLATFORM == "Windows":
    DRIVES = ["C:", "D:", "E:", "F:", "G:", "H:", "I:", "J:", "K:", "L:", "M:", "N:", "O:", "P:", "Q:", "R:", "S:", "T:", "U:", "V:", "W:", "X:", "Y:", "Z:"]
    for drive in DRIVES:
        EXPECTED_DEVKITPRO_PATHS.append(DirectoryPath(f"{drive}/devkitPro/"))
    EXPECTED_DOLPHIN_USERPATH = Path.home / "Documents/Dolphin Emulator"
elif PLATFORM == "Linux":
    EXPECTED_DEVKITPRO_PATHS.append(DirectoryPath("/opt/devkitpro/devkitPPC/bin/"))
    EXPECTED_DOLPHIN_USERPATH = DirectoryPath(Path.home / ".local/share/dolphin-emu/")
else:
    raise FreighterException(f"Configuring Freighter for your system platform ({PLATFORM}) is not supported.")


@dataclass(init=False)
class UserEnvironment(TOMLConfig):
    DevKitProPath: DirectoryPath
    GPP: FilePath
    GCC: FilePath
    LD: FilePath
    AR: FilePath
    OBJDUMP: FilePath
    OBJCOPY: FilePath
    NM: FilePath
    READELF: FilePath
    GBD: FilePath
    CPPFLIT: FilePath
    DolphinUserPath: DirectoryPath
    DolphinMaps: DirectoryPath

    def __init__(self) -> None:
        if not USERENVIRONMENT_PATH.exists():
            self.find_dekitppc_bin_folder()
            self.verify_devkitpro()
            Console.print("devKitPro path good.")
            self.find_dolphin_documents_folder()
            self.verify_dolphin()
            Console.print("Dolphin User path good.")
            self.save(USERENVIRONMENT_PATH)
        else:
            self.load(USERENVIRONMENT_PATH)

    @classmethod
    def reset(cls):
        Console.print("Resetting UserEnvironment...")
        if isfile(USERENVIRONMENT_PATH):
            remove(USERENVIRONMENT_PATH)
        user_environment = UserEnvironment()

        Console.print("Finished")
        user_environment.save(USERENVIRONMENT_PATH)
        exit(0)

    def set_binutils(self, devkitpro_path: DirectoryPath):
        self.DevKitProPath = devkitpro_path
        self.GPP = FilePath(devkitpro_path / "devkitPPC/bin/powerpc-eabi-g++.exe")
        self.GCC = FilePath(devkitpro_path / "devkitPPC/bin/powerpc-eabi-gcc.exe")
        self.LD = FilePath(devkitpro_path / "devkitPPC/bin/powerpc-eabi-ld.exe")
        self.AR = FilePath(devkitpro_path / "devkitPPC/bin/powerpc-eabi-ar.exe")
        self.OBJDUMP = FilePath(devkitpro_path / "devkitPPC/bin/powerpc-eabi-objdump.exe")
        self.OBJCOPY = FilePath(devkitpro_path / "devkitPPC/bin/powerpc-eabi-objcopy.exe")
        self.NM = FilePath(devkitpro_path / "devkitPPC/bin/powerpc-eabi-gcc-nm.exe")
        self.READELF = FilePath(devkitpro_path / "devkitPPC/bin/powerpc-eabi-readelf.exe")
        self.GBD = FilePath(devkitpro_path / "devkitPPC/bin/powerpc-eabi-gdb.exe")
        self.CPPFLIT = FilePath(devkitpro_path / "devkitPPC/bin/powerpc-eabi-c++filt.exe")

    def find_dekitppc_bin_folder(self) -> None:
        Console.print("Finding devKitPro folder...")
        for path in EXPECTED_DEVKITPRO_PATHS:
            if path.exists():
                self.DevKitProPath = path
                self.set_binutils(path)
                return
        path = input(f"Freighter could not find your devkitPro folder. Expected to be found at {EXPECTED_DEVKITPRO_PATHS[0]}.\n Input the path to set it:")
        self.set_binutils(DirectoryPath(path))

        while not self.verify_devkitpro():
            path = input(f"Try again:")
            self.set_binutils(DirectoryPath(path))

    def set_dolphin_paths(self, dolphin_user_path: DirectoryPath):
        self.DolphinUserPath = dolphin_user_path
        self.DolphinMaps = self.DolphinUserPath / "Maps"

    def find_dolphin_documents_folder(self) -> None:
        Console.print("Finding Dolphin user folder...")
        if EXPECTED_DOLPHIN_USERPATH.exists():
            self.set_dolphin_paths(EXPECTED_DOLPHIN_USERPATH)
            return
        path = input(f"Freighter could not find your Dolphin User folder. Expected to be found at {EXPECTED_DOLPHIN_USERPATH}.\n Input the path to set it:") + "/"
        self.set_dolphin_paths(DirectoryPath(path))
        while not self.verify_dolphin():
            path = input("Try again:")
            self.set_dolphin_paths(DirectoryPath(path))

    def verify_devkitpro(self) -> bool:
        # If these fail then something got deleted or moved from the bin folder
        try:
            self.GPP.assert_exists()
            self.GCC.assert_exists()
            self.LD.assert_exists()
            self.AR.assert_exists()
            self.OBJDUMP.assert_exists()
            self.OBJCOPY.assert_exists()
            self.NM.assert_exists()
            self.READELF.assert_exists()
            self.GBD.assert_exists()
            self.CPPFLIT.assert_exists()
        except:
            Console.print("This doesn't seem right. All or some binutils executables were not not found.")
            return False
        return True

    def verify_dolphin(self) -> bool:
        try:
            self.DolphinMaps.assert_exists()
        except:
            Console.print("This doesn't seem right. Maps folder was not found.")
            return False
        return True


@dataclass
class Profile(TOMLObject):
    # Required
    GameID: str
    InjectionAddress: UInt
    InputDolFile: FilePath
    OutputDolFile: FilePath
    IncludeFolders: list[DirectoryPath]
    SourceFolders: list[DirectoryPath]

    # Optional
    SDA: UInt = field(default_factory=UInt)
    SDA2: UInt = field(default_factory=UInt)
    GeckoFolder: DirectoryPath = DEFAULT_FOLDERS["GECKO"]
    SymbolsFolder: DirectoryPath = DEFAULT_FOLDERS["SYMBOLS"]
    LinkerScripts: list[FilePath] = field(default_factory=list[FilePath])
    TemporaryFilesFolder: DirectoryPath = DEFAULT_FOLDERS["TEMP"]
    InputSymbolMap: FilePath = field(default=FilePath(""))
    OutputSymbolMapPaths: list[FilePath] = field(default_factory=list[FilePath])
    StringHooks: dict[str, str] = field(default_factory=dict[str, str])

    IgnoredSourceFiles: list[FilePath] = field(default_factory=list[FilePath])
    IgnoredGeckoFiles: list[FilePath] = field(default_factory=list[FilePath])
    IgnoreHooks: list[str] = field(default_factory=list[str])
    DiscardLibraryObjects: list[str] = field(default_factory=list[str])
    DiscardSections: list[str] = field(default_factory=list[str])

    CompilerArgs: list[str] = field(default_factory=list[str])
    GCCArgs: list[str] = field(default_factory=list[str])
    GPPArgs: list[str] = field(default_factory=list[str])
    LDArgs: list[str] = field(default_factory=list[str])

    @classmethod
    @property
    def default(cls):
        return cls("FREI01", UInt(), FilePath("main.dol"), FilePath("build/sys/main.dol"), [DirectoryPath("source/")], [DirectoryPath("includes/")])

    def verify_paths(self):
        self.InputDolFile.assert_exists()
        self.InputSymbolMap.assert_exists()
        for folder in self.IncludeFolders:
            folder.assert_exists()
        for folder in self.SourceFolders:
            folder.assert_exists()


@dataclass
class Banner(TOMLObject):
    BannerImage: str = "banner.png"
    Title: str = "GameTitle"
    GameName: str = "GameTitle"
    Maker: str = "MyOrganization"
    ShortMaker: str = "MyOrganization"
    Description: str = "This is my game's description!"
    OutputPath: str = "build/files/opening.bnr"


PROJECTLIST_PATH = FilePath(FREIGHTER_LOCALAPPDATA / "ProjectList.toml")


# TOML config for storing project paths so you can build projects without having to set the cwd
@dataclass
class Project(TOMLObject):  # This should serialize to [Project.WhateverProjectName]
    ProjectPath: DirectoryPath
    ConfigPath: FilePath


@dataclass
class ProjectListConfig(TOMLConfig):
    Projects: dict[str, Project]

    def __init__(self):
        self.Projects = {}
        if PROJECTLIST_PATH.exists():
            self.load(PROJECTLIST_PATH)

    def add_project(self, project_path: DirectoryPath):
        if not project_path:
            return

        config_path = project_path.create_filepath("ProjectConfig.toml")
        project_config = ProjectConfig()
        project_config.load(config_path)

        self.Projects[project_config.ProjectName] = Project(project_path, config_path)
        self.save(PROJECTLIST_PATH)

    def new_project(self, args: Arguments.NewArg):
        if not args:
            return
        project_path = args.project_path.absolute()
        chdir(project_path)

        if isfile(DEFAULT_PROJECT_CONFIG_NAME):
            Console.print("A project already exists in the current working directory. Aborting.")
            exit(0)
        banner = Banner()
        config = Profile.default

        for default_path in DEFAULT_FOLDERS.values():
            default_path.create()

        config_path = project_path.create_filepath(DEFAULT_PROJECT_CONFIG_NAME)

        self.Projects[args.project_name] = Project(project_path, config_path)

        with open(DEFAULT_PROJECT_CONFIG_NAME, "w+") as f:
            f.write(banner.toml_string + config.toml_string)
        self.save(PROJECTLIST_PATH)


@dataclass
class ProjectConfig(TOMLConfig):
    config_path: ClassVar[FilePath]
    selected_profile: ClassVar[Profile]
    ProjectName: str = ""
    BannerConfig: Banner = field(default_factory=Banner)
    Profiles: dict[str, Profile] = field(default_factory=dict[str, Profile])

    def init(self, config_path: FilePath, profile_name: str):
        ProjectConfig.config_path = config_path
        self.load(ProjectConfig.config_path)

        if profile_name:
            ProjectConfig.selected_profile = self.Profiles[profile_name]
        else:
            ProjectConfig.selected_profile = next(iter(self.Profiles.values()))
            ProjectConfig.selected_profile.verify_paths()

    @classmethod
    @property
    def default_toml_string(cls) -> str:
        return Banner().toml_string + Profile.default.toml_string
