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

import tkinter.filedialog

PLATFORM = system()

DEFAULT_FOLDERS = {
    "GECKO": DirectoryPath("gecko/"),
    "SOURCE": DirectoryPath("source/"),
    "INCLUDE": DirectoryPath("include/"),
    "SYMBOLS": DirectoryPath("symbols/"),
    "BUILD": DirectoryPath("build/"),
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
    SuperBMDPath: FilePath

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
        USERENVIRONMENT_PATH.delete(True)
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

        Console.print(f"Freighter could not find your devkitPro folder. Expected to be found at {EXPECTED_DEVKITPRO_PATHS[0]}.\n")
        while not self.verify_devkitpro():
            path = DirectoryPath(tkinter.filedialog.askdirectory(title="Please select your devkitPro folder."))
            self.set_binutils(DirectoryPath(path))

    def set_dolphin_paths(self, dolphin_user_path: DirectoryPath):
        self.DolphinUserPath = dolphin_user_path
        self.DolphinMaps = self.DolphinUserPath / "Maps"

    def find_dolphin_documents_folder(self) -> None:
        Console.print("Finding Dolphin user folder...")
        if EXPECTED_DOLPHIN_USERPATH.exists():
            self.set_dolphin_paths(EXPECTED_DOLPHIN_USERPATH)
            return

        Console.print(f"Freighter could not find your Dolphin User folder. Expected to be found at {EXPECTED_DOLPHIN_USERPATH}.\n")

        while not self.verify_dolphin():
            path = DirectoryPath(tkinter.filedialog.askdirectory(title="Please select your Dolphin User folder."))
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
    TemporaryFilesFolder: DirectoryPath = DirectoryPath("temp/")
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
class ProjectManager(TOMLConfig):
    Projects: dict[str, Project]

    def __init__(self):
        self.Projects = {}
        if PROJECTLIST_PATH.exists():
            self.load(PROJECTLIST_PATH)

    def import_project(self) -> None:
        project_dir = DirectoryPath(tkinter.filedialog.askdirectory(title="Please select a project folder."))
        config_path = project_dir.create_filepath("ProjectConfig.toml")
        config_path.assert_exists()
        project_config = ProjectConfig()
        project_config.load(config_path)
        if not self.contains_project(project_config.ProjectName):
            self.Projects[project_config.ProjectName] = Project(project_dir, config_path)
            self.save(PROJECTLIST_PATH)
            Console.print(f'Imported {project_config.ProjectName} from "{config_path}"', PrintType.INFO)
        exit(0)

    def contains_project(self, project_name: str) -> bool:
        if project_name in self.Projects.keys():
            Console.print(f"Freighter already has an imported project under the alias {project_name}", PrintType.ERROR)
            Console.print(self.Projects[project_name])
            return True
        return False

    def new_project(self, args: Arguments.NewArg) -> None:
        if not args:
            return

        if not self.contains_project(args.project_name):
            project_dir = args.project_path.absolute()
            project_dir.create()

            chdir(project_dir)
            config_path = project_dir.create_filepath(DEFAULT_PROJECT_CONFIG_NAME)
            if config_path.exists():
                project_config = ProjectConfig()
                project_config.load(config_path)
                Console.print(f"A project named {project_config.ProjectName} already exists at given path. Did you mean to import it?")
                exit(0)

            project_config = ProjectConfig.default(args.project_name)

            for default_path in DEFAULT_FOLDERS.values():
                default_path.create()

            project_config.save(config_path)
            self.Projects[args.project_name] = Project(project_dir, config_path)
            self.save(PROJECTLIST_PATH)

        exit(0)

    def print(self):
        for project_name, project in self.Projects.items():
            print(f"{project_name}")


@dataclass
class ProjectConfig(TOMLConfig):
    ProjectName: str = ""
    BannerConfig: Banner = field(default_factory=Banner)
    Profiles: dict[str, Profile] = field(default_factory=dict[str, Profile])

    def init(self, config_path: FilePath, profile_name: str):
        self.config_path = config_path
        self.load(self.config_path)

        if profile_name:
            self.selected_profile = self.Profiles[profile_name]
        else:
            self.selected_profile = next(iter(self.Profiles.values()))
            self.selected_profile.verify_paths()

    @classmethod
    def default(cls, project_name):
        profiles = dict[str, Profile]()
        profiles["Debug"] = Profile.default
        return cls(project_name, Banner(), profiles)


import subprocess


@dataclass
class BMDModel(TOMLObject):
    Input: FilePath
    Output: FilePath
    MaterialJSON: FilePath
    Tristrip: str = "all"
    Rotate: bool = True


@dataclass
class ProjectFileBuilder(TOMLConfig):
    ToolPath: FilePath = FilePath("D:/Pikmin1Remake/tools/SuperBMD/SuperBMD.exe")
    BMDModels: dict[str, BMDModel] = field(default_factory=dict[str, BMDModel])

    def __init__(self):
        self.load(FilePath("ProjectFiles.toml"))

    def build(self, file_manager):
        from freighter.filelist import File

        for name, model in self.BMDModels.items():
            model.Input.assert_exists()

            input_model_file = File(file_manager, model.Input)
            if input_model_file.is_hash_same():
                Console.print(f'[{name}] "{model.Input}" is not modified. Skipping...')
                continue
            Console.print(f"[{name}] Building BMD model...")
            args: list[str | PathLike] = [self.ToolPath.absolute(), model.Input.absolute(), model.Output.absolute()]

            model.Output.assert_exists()
            if model.MaterialJSON:
                model.MaterialJSON.assert_exists()
                args += ["--mat", model.MaterialJSON.absolute()]
            if model.Rotate:
                args.append("--rotate")
            if model.Tristrip:
                args += ["--tristrip", model.Tristrip]

            subprocess.Popen(args, shell=True, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
