import os
import subprocess
import tkinter.filedialog
from concurrent.futures import ProcessPoolExecutor, as_completed
from os import chdir
from platform import system
from typing import Self, NoReturn

from attrs import define
from freighter import obj2grid, rarc
from freighter.exceptions import FreighterException
from freighter.logging import *
from freighter.numerics import UInt, ULong
from freighter.path import DirectoryPath, FilePath
from freighter.toml import *

PLATFORM = system()

FREIGHTER_LOCALAPPDATA = DirectoryPath.expandvars("%LOCALAPPDATA%/Freighter/")
if not FREIGHTER_LOCALAPPDATA.exists:
    FREIGHTER_LOCALAPPDATA.create()


DEFAULT_PROJECT_CONFIG_NAME = "ProjectConfig.toml"

EXPECTED_DEVKITPRO_PATHS = list[DirectoryPath]()
EXPECTED_DOLPHIN_USERPATH: DirectoryPath

if PLATFORM == "Windows":
    DRIVES = ["C:", "D:", "E:", "F:", "G:", "H:", "I:", "J:", "K:", "L:", "M:", "N:", "O:", "P:", "Q:", "R:", "S:", "T:", "U:", "V:", "W:", "X:", "Y:", "Z:"]
    for drive in DRIVES:
        EXPECTED_DEVKITPRO_PATHS.append(DirectoryPath(f"{drive}/devkitPro/"))
    EXPECTED_DOLPHIN_USERPATH = DirectoryPath.home() / "Documents/Dolphin Emulator"
elif PLATFORM == "Linux":
    EXPECTED_DEVKITPRO_PATHS.append(DirectoryPath("/opt/devkitpro/devkitPPC/bin/"))
    EXPECTED_DOLPHIN_USERPATH = DirectoryPath.home() / ".local/share/dolphin-emu/"
else:
    raise FreighterException(f"Configuring Freighter for your system platform ({PLATFORM}) is not supported.")


def open_file_dialog(dialog_title: str) -> FilePath | None:
    if path := tkinter.filedialog.askopenfilename(title=dialog_title):
        return FilePath(path)
    else:
        return None


def open_directory_dialog(dialog_title: str) -> DirectoryPath | None:
    if path := tkinter.filedialog.askdirectory(title=dialog_title):
        return DirectoryPath(path)
    else:
        return None


@define
class BinUtils(TOMLObject):
    GPP: FilePath = tomlfield(required=True)
    GCC: FilePath = tomlfield(required=True)
    LD: FilePath = tomlfield(required=True)
    AR: FilePath = tomlfield(required=True)
    OBJDUMP: FilePath = tomlfield(required=True)
    OBJCOPY: FilePath = tomlfield(required=True)
    NM: FilePath = tomlfield(required=True)
    READELF: FilePath = tomlfield(required=True)
    GBD: FilePath = tomlfield(required=True)
    CPPFLIT: FilePath = tomlfield(required=True)

    @classmethod
    def set_from_path(cls, binutils_path: DirectoryPath, arch_prefix):
        return cls(
            GPP=FilePath(binutils_path / f"{arch_prefix}-g++.exe"),
            GCC=FilePath(binutils_path / f"{arch_prefix}-gcc.exe"),
            LD=FilePath(binutils_path / f"{arch_prefix}-ld.exe"),
            AR=FilePath(binutils_path / f"{arch_prefix}-ar.exe"),
            OBJDUMP=FilePath(binutils_path / f"{arch_prefix}-objdump.exe"),
            OBJCOPY=FilePath(binutils_path / f"{arch_prefix}-objcopy.exe"),
            NM=FilePath(binutils_path / f"{arch_prefix}-gcc-nm.exe"),
            READELF=FilePath(binutils_path / f"{arch_prefix}-readelf.exe"),
            GBD=FilePath(binutils_path / f"{arch_prefix}-gdb.exe"),
            CPPFLIT=FilePath(binutils_path / f"{arch_prefix}-c++filt.exe"),
        )


@define(init=False, kw_only=True)
class UserEnvironmentConfig(TOMLConfigFile):
    DevKitProPath: DirectoryPath = tomlfield()
    DolphinMaps: DirectoryPath = tomlfield()
    DolphinUserPath: DirectoryPath = tomlfield()
    SuperBMDPath: DirectoryPath = tomlfield()
    WiimmPath: DirectoryPath = tomlfield()
    RyujinxAppDataPath: DirectoryPath = tomlfield()
    BinUtilsPaths: dict[str, BinUtils] = tomlfield(comment="Contains paths to various binutils executables.")

    def __comment__(self) -> str:
        return "gay sex"

    def __init__(self, path: FilePath):
        super().__init__(path)
        self.find_dekitppc_bin_folder()
        self.verify_binutils_paths()
        self.find_dolphin_documents_folder()
        self.verify_dolphin()

    def set_binutils(self, devkitpro_path: DirectoryPath):
        self.DevKitProPath = devkitpro_path
        self.BinUtilsPaths = dict[str, BinUtils]()

        devkitPPC_path = self.DevKitProPath / "devkitPPC/bin"
        if (devkitPPC_path).exists:
            self.BinUtilsPaths["PowerPC"] = BinUtils.set_from_path(devkitPPC_path, "powerpc-eabi")

        devkitA64_path = self.DevKitProPath / "devkitA64/bin"
        if devkitA64_path.exists:
            self.BinUtilsPaths["AArch64"] = BinUtils.set_from_path(devkitA64_path, "aarch64-none-elf")

    def find_dekitppc_bin_folder(self) -> None:
        Logger.info("Finding devKitPro folder...")
        for path in EXPECTED_DEVKITPRO_PATHS:
            if path.exists:
                self.DevKitProPath = path
                self.set_binutils(path)
                return

        Logger.info(f"Freighter could not find your devkitPro folder. Expected to be found at {EXPECTED_DEVKITPRO_PATHS[0]}.\n")
        while not self.verify_binutils_paths():
            if path := open_directory_dialog("Please select your devkitPro folder."):
                self.set_binutils(path)

    def set_dolphin_paths(self, dolphin_user_path: DirectoryPath):
        self.DolphinUserPath = dolphin_user_path
        self.DolphinMaps = self.DolphinUserPath / "Maps"

    def find_dolphin_documents_folder(self) -> None:
        Logger.info("Finding Dolphin user folder...")
        if EXPECTED_DOLPHIN_USERPATH.exists:
            self.set_dolphin_paths(EXPECTED_DOLPHIN_USERPATH)
            return

        Logger.info(f"Freighter could not find your Dolphin User folder. Expected to be found at {EXPECTED_DOLPHIN_USERPATH}.\n")

        while not self.verify_dolphin():
            if path := open_directory_dialog("Please select your Dolphin User folder."):
                self.set_dolphin_paths(path)

    def verify_binutils_paths(self) -> bool:
        # If these fail then something got deleted or moved from the bin folder
        try:
            for architecture, binutils in self.BinUtilsPaths.items():
                binutils.GPP.assert_exists()
                binutils.GCC.assert_exists()
                binutils.LD.assert_exists()
                binutils.AR.assert_exists()
                binutils.OBJDUMP.assert_exists()
                binutils.OBJCOPY.assert_exists()
                binutils.NM.assert_exists()
                binutils.READELF.assert_exists()
                binutils.GBD.assert_exists()
                binutils.CPPFLIT.assert_exists()
                Logger.info(f"binutils for {architecture} good!")
        except:
            Logger.info(f"This doesn't seem right. All or some binutils executables were not not found.")
            return False
        return True

    def verify_dolphin(self) -> bool:
        try:
            self.DolphinMaps.assert_exists()
        except:
            Logger.info("This doesn't seem right. Maps folder was not found.")
            return False
        Logger.info("Dolphin User path good.")
        return True


@define
class ProjectProfile(TOMLObject):
    # Required
    InputBinary: FilePath = tomlfield(
        required=True,
    )
    OutputBinary: FilePath = tomlfield(
        required=True,
    )
    InjectionAddress: ULong = tomlfield(
        default=ULong(0),
        required=True,
        comment="The address where custom code and data will be injected into the .dol",
    )
    IncludeFolders: list[DirectoryPath] = tomlfield(
        default=list[DirectoryPath](),
        required=True,
        comment="Directory paths containing source files",
    )
    SourceFolders: list[DirectoryPath] = tomlfield(
        default=list[DirectoryPath](),
        required=True,
        comment="Directory paths containing header files",
    )

    # Optional
    Libraries: list[str] = tomlfield(
        factory=list,
        comment="Paths to library objects to link with",
    )
    LinkerScripts: list[FilePath] = tomlfield(
        factory=list,
        comment="Paths to linkerscripts to link with",
    )
    SymbolsFolder: DirectoryPath = tomlfield(
        default=DirectoryPath("symbols/"),
        comment="Directory path containing symbol definitions.",
    )
    DiscardLibraryObjects: list[str] = tomlfield(
        factory=list,
        comment="Library object files to discard during linking",
    )
    DiscardSections: list[str] = tomlfield(
        factory=list,
        comment="Sections to discard during linking",
    )
    IgnoredSourceFiles: list[FilePath] = tomlfield(
        factory=list,
        comment="List of source file paths to tell Freighter not to compile and link with",
    )
    IgnoredHooks: list[str] = tomlfield(
        factory=list,
        comment="List of #pragma hooks to ignore after link phase",
    )
    TemporaryFilesFolder: DirectoryPath = tomlfield(
        default=DirectoryPath("temp/"),
        comment="Directory path to output temporary build artifacts to a different folder",
    )
    StringHooks: dict[str, str] = tomlfield(
        factory=dict,
        comment="A table of strings to inject into final binary at a specific address",
    )
    CompilerArgs: list[str] = tomlfield(
        factory=list,
        comment="Compiler args that apply both gcc or g++ args here",
    )
    GCCArgs: list[str] = tomlfield(
        factory=list,
        comment="Put C related compiler args here",
    )
    GPPArgs: list[str] = tomlfield(
        factory=list,
        comment="Put C++ related compiler args here",
    )
    LDArgs: list[str] = tomlfield(
        factory=list,
        comment="Linker args go here",
    )


@define
class SwitchProfile(ProjectProfile):
    # Required
    TitleID: str = tomlfield(
        default="0100e0b019974000",
        required=True,
    )

    @classmethod
    @property
    def default(cls):
        return cls()


@define
class Banner(TOMLObject):
    BannerImage: str = tomlfield(
        required=True,
        default="banner.png",
        comment="Path to a 96 x 32 image file",
    )
    Title: str = tomlfield(
        required=True,
        default="GameTitle",
        comment="",
    )
    GameTitle: str = tomlfield(
        required=True,
        default="GameTitle",
        comment="Game title displayed in GC Bios/Dolphin",
    )
    Maker: str = tomlfield(
        required=True,
        default="MyOrganization",
        comment="Your name, organization, or group",
    )
    ShortMaker: str = tomlfield(
        required=True,
        default="MyOrganization",
        comment="Optionally shortened Maker name",
    )
    Description: str = tomlfield(
        required=True,
        default="This is my game's description!",
        comment="Game description displayed in GC Bios/Dolphin",
    )
    OutputPath: str = tomlfield(
        default="build/files/opening.bnr",
        comment="Changes the output of the .bnr file",
    )


@define
class GameCubeProfile(ProjectProfile):
    # Required
    GameID: str = tomlfield(
        required=True,
        default="FREI01",
        comment="A 6-character string to represent the game id",
    )
    InputBinary: FilePath = tomlfield(
        required=True,
        default=DirectoryPath("main.dol"),
    )
    OutputBinary: FilePath = tomlfield(
        required=True,
        default=DirectoryPath("build/sys/main.dol"),
    )

    # Optional
    SDA: UInt = tomlfield(
        default=UInt(0),
        comment="Defines the SDA (r2) register value",
    )
    SDA2: UInt = tomlfield(
        default=UInt(0),
        comment="Defines the SDA2 (r13) register value",
    )
    GeckoFolder: DirectoryPath = tomlfield(
        default=DirectoryPath("gecko/"),
    )
    InputSymbolMap: FilePath = tomlfield(
        default=FilePath("GPVE01.map"),
        comment="Path to a CodeWarrior map file Freighter will use to append new symbols to aid debugging with Dolphin emulator",
    )
    OutputSymbolMapPaths: list[FilePath] = tomlfield(
        default=list[FilePath](),
        comment="File paths to place generated CodeWarrior map.",
    )
    IgnoredGeckoFiles: list[FilePath] = tomlfield(
        default=list[FilePath](),
        comment="Any gecko txt files that should be ignored when patched into the .dol",
    )

    @classmethod
    @property
    def default(cls):
        return cls(
            InjectionAddress=ULong(0),
            SourceFolders=[DirectoryPath("source/")],
            IncludeFolders=[DirectoryPath("includes/")],
            GameID="FREI01",
            InputBinary=FilePath("main.dol"),
            OutputBinary=FilePath("build/sys/main.dol"),
        )


PROJECTLIST_PATH = FilePath(FREIGHTER_LOCALAPPDATA / "ProjectList.toml")


# TOML config for storing project paths so you can build projects without having to set the cwd
@define
class ProjectListEntry(TOMLObject):  # This should serialize to [Project.WhateverProjectName]
    ProjectPath: DirectoryPath = tomlfield(
        required=True,
    )
    ConfigPath: FilePath = tomlfield(
        required=True,
    )


@define(init=False)
class ProjectListConfig(TOMLConfigFile):
    Projects: dict[str, ProjectListEntry] = tomlfield(
        default={},
        required=True,
    )

    def has_project(self, project_name: str):
        if project_name in self.Projects.keys():
            return True
        else:
            debug_string = []
            debug_string.append(f"{project_name} is not a stored Project")
            debug_string.append("Available Projects:")
            for project_name, project in self.Projects.items():
                debug_string.append(f"\t{project_name}")
            Logger.info("\n".join(debug_string))

    def import_project(self) -> NoReturn:
        if (project_dir := open_directory_dialog("Please select a project folder to import.")) is not None:
            config_path = project_dir.make_filepath("ProjectConfig.toml")
            config_path.assert_exists()

            if not (project_config := ProjectConfig.load_dynamic(config_path)):
                Logger.error(f'Failed to imported "{config_path}" as a ProjectConfig!')
                os._exit(0)
            project_name = project_config.ProjectName
            if project_name in self.Projects.keys():
                Logger.error(f"Freighter already has an imported project under the alias {project_name}\n{self.Projects[project_name]}")
                os._exit(0)

            self.Projects[project_name] = ProjectListEntry(project_dir, config_path)
            self.save()
            Logger.info(f'Imported {project_name} from "{config_path}"\nTo build {project_name} use the command: freighter -build {project_name}')
        else:
            Logger.info("Canceled Project import.")
        os._exit(0)

    def new_project(self) -> NoReturn:
        inquiry = f"Enter the name of the project:\n{CYAN}"
        while (project_name := input(inquiry)) and self.has_project(project_name):
            Logger.info("A project already exists under that name. Choose a different one.")

        inquiry = f"{AnsiAttribute.RESET}What kind of project? Please enter one of the following options:\n{CYAN}GameCube\nSwitch\n"
        while (project_type := input(inquiry)) is not None and project_type not in ["GameCube", "Switch"]:
            Logger.info(f"{project_type} is not a valid option.")

        if not self.has_project(project_name):
            if (project_dir := open_directory_dialog("Select a folder to initalize a new project!")) is None:
                Logger.info("No folder selected. Aborting...")
                exit(0)
            chdir(project_dir)
            config_path = project_dir.make_filepath(DEFAULT_PROJECT_CONFIG_NAME)
            if config_path.exists:
                project_config = ProjectConfig.load_dynamic(config_path)

                Logger.info(f"A project named {project_config.ProjectName} already exists at given path. Did you mean to import it?")
                exit(0)

            if project_type == "GameCube":
                project_config = GameCubeProjectConfig.default
                project_config.ProjectName = project_name
                profile = project_config.Profiles["Debug"]
                profile.IncludeFolders[0].create()
                profile.SourceFolders[0].create()
                profile.SymbolsFolder.create()
                profile.GeckoFolder.create()

            elif project_type == "Switch":
                project_config = SwitchProjectConfig.default
                project_config.ProjectName = project_name
                profile = project_config.Profiles["Debug"]
                profile.IncludeFolders[0].create()
                profile.SourceFolders[0].create()
                profile.SymbolsFolder.create()

            self.Projects[project_name] = ProjectListEntry(project_dir, config_path)
            self.save()
            project_dir.reveal()
            Logger.info(f'Finished created new project "{project_name}"!')
            Logger.info(f"To build your project use the command: freighter -build {project_name}")
        exit(0)


@define(init=False, kw_only=True)
class ProjectConfig(TOMLConfigFile):
    SelectedProfile: GameCubeProfile | SwitchProfile = tomlfield(
        serialize=False,
    )
    Profiles: dict[str, GameCubeProfile | SwitchProfile] = tomlfield(
        init=False,
    )
    ProjectName: str = tomlfield(
        default="",
    )
    TargetArchitecture: str = tomlfield(
        default="",
    )

    @staticmethod
    def load_dynamic(config_path: FilePath, profile_name: str | None = None) -> "GameCubeProjectConfig | SwitchProjectConfig ":
        with open(config_path, "rb") as f:
            toml_dict = tomllib.load(f)

        target = toml_dict["TargetArchitecture"]
        config: GameCubeProjectConfig | SwitchProjectConfig

        if target == "PowerPC":
            config = GameCubeProjectConfig.load_from_dict(config_path, toml_dict)
        elif target == "AArch64":
            config = SwitchProjectConfig.load_from_dict(config_path, toml_dict)
        else:
            raise FreighterException(f"{config_path} is not a valid ProjectConfig")

        if profile_name:
            config.SelectedProfile = config.Profiles[profile_name]
        else:
            config.SelectedProfile = next(iter(config.Profiles.values()))
        return config


@define()
class GameCubeProjectConfig(ProjectConfig):
    TargetArchitecture: str = tomlfield(
        default="PowerPC",
        required=True,
    )
    ProjectName: str = tomlfield(
        default="MyGameCubeProject",
        required=True,
    )
    BannerConfig: Banner = tomlfield(
        default=Banner(),
        required=True,
    )
    Profiles: dict[str, GameCubeProfile] = tomlfield(
        default=dict[str, GameCubeProfile](),
        required=True,
    )

    @classmethod
    @property
    def default(cls):
        config = cls()
        config.Profiles["Debug"] = GameCubeProfile.default
        return config


@define
class SwitchProjectConfig(ProjectConfig):
    TargetArchitecture: str = tomlfield(
        default="AArch64",
        required=True,
    )
    ProjectName: str = tomlfield(
        default="MySwitchProject",
        required=True,
    )
    Profiles: dict[str, SwitchProfile] = tomlfield(
        default=dict[str, SwitchProfile](),
        required=True,
    )

    @classmethod
    @property
    def default(cls):
        object = cls()
        object.Profiles["Debug"] = SwitchProfile.default
        return object


@define
class SZSArchive(TOMLObject):
    Input: DirectoryPath = tomlfield(
        required=True,
    )
    Output: FilePath = tomlfield(
        required=True,
    )
    CompressionLevel: ULong = tomlfield(
        default=ULong(10),
    )


@define
class BMDModel(TOMLObject):
    Input: FilePath = tomlfield(
        required=True,
    )
    Output: FilePath = tomlfield(
        required=True,
    )
    MaterialJSON: FilePath = tomlfield(
        required=True,
    )
    ExtraArgs: list[str] = tomlfield(
        default=[],
    )
    Tristrip: str = tomlfield(
        default="all",
    )
    Rotate: bool = tomlfield(
        default=True,
    )


@define
class Pikmin2Collision(TOMLObject):
    Input: FilePath = tomlfield(
        required=True,
    )
    OutputFolder: DirectoryPath = tomlfield(
        required=True,
    )
    CellSize: ULong = tomlfield(
        required=True,
    )
    FlipYZ: bool = tomlfield(
        default=False,
    )


@define
class TaskConfig(TOMLObject):
    user_environment: UserEnvironmentConfig = tomlfield(
        serialize=False,
    )
    BMDModels: dict[str, BMDModel] = tomlfield(
        factory=dict,
        alias="BMDModel",
    )
    SZSArchives: dict[str, SZSArchive] = tomlfield(
        factory=dict,
        alias="SZSArchive",
    )
    Pikmin2Collisions: dict[str, Pikmin2Collision] = tomlfield(
        factory=dict,
        alias="Pikmin2Collision",
    )

    def check_wiimm_path(self):
        if self.SZSArchives and not self.user_environment.WiimmPath:
            if wiimm_path := open_directory_dialog("Please select your Wiimm folder to continue to compress SZS archives."):
                self.user_environment.WiimmPath = wiimm_path
                self.user_environment.save()
            else:
                return False
        return True

    def check_superbmd_path(self):
        if self.BMDModels and not self.user_environment.SuperBMDPath:
            if superbmd_path := open_directory_dialog("Please select your SuperBMD folder to continue the build process."):
                self.user_environment.SuperBMDPath = superbmd_path
                self.user_environment.save()
            else:
                return False
        return True

    def build(self, file_manager):
        self.build_bmdmodels(file_manager)
        self.build_pikmin2_collision(file_manager)
        self.build_archives(file_manager)

    def build_bmdmodels(self, file_manager):
        from freighter.filemanager import File

        if not self.check_superbmd_path():
            Logger.info("Skipping building BMD models as SuperBMD path is not defined.")
            return

        for name, model in self.BMDModels.items():
            model.Input.assert_exists()

            input_model_file = File(file_manager, model.Input)
            if input_model_file.is_hash_same():
                Logger.info(f'[{name}] "{model.Input}" is not modified. Skipping...')
                continue
            Logger.info(f"[{name}] Building BMD model...")

            args: list[str | PathLike] = [self.user_environment.SuperBMDPath.absolute / "SuperBMD.exe", model.Input.absolute, model.Output.absolute]

            if model.MaterialJSON:
                model.MaterialJSON.assert_exists()
                args += ["--mat", model.MaterialJSON.absolute]
            if model.Rotate:
                args.append("--rotate")
            if model.Tristrip:
                args += ["--tristrip", model.Tristrip]
            if model.ExtraArgs:
                args += model.ExtraArgs
            subprocess.Popen(args, shell=True, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
        Logger.info("Finished building BMD models!")

    def build_pikmin2_collision(self, file_manager):
        from freighter.filemanager import File

        for name, collision in self.Pikmin2Collisions.items():
            collision.Input.assert_exists()
            input_obj_file = File(file_manager, collision.Input)
            if input_obj_file.is_hash_same():
                Logger.info(f'[{name}] "{collision.Input}" is not modified. Skipping...')
                continue

            Logger.info("Generating Pikmin2 collision...")
            obj2grid.generate_collision(collision.Input, collision.OutputFolder, collision.CellSize, collision.FlipYZ)
            Logger.info(f"[{name}]Finished generating collision!")

    def wszst_compress(self, wiims_path: DirectoryPath, arc_file: FilePath, compression_level: ULong, szs_output: FilePath):
        args = [wiims_path / "SZS/wszst", "COMPRESS", "--compr", str(compression_level), "--overwrite", arc_file, "-d", szs_output, "--yaz0"]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        os.remove(arc_file)
        return process.returncode, out, err

    def build_archives(self, file_manager):
        if not self.check_wiimm_path():
            Logger.info("Skipping building SZS archives as Wiimm path is not defined.")
            return

        with ProcessPoolExecutor() as executor:
            for name, archive in self.SZSArchives.items():
                # create_arc_tasks = []
                compress_tasks = []
                temp_arc_file = archive.Output.with_name("temp.arc")
                # task = executor.submit(rarc.create_arc, archive.Input, temp_arc_file)
                # create_arc_tasks.append(task)
                rarc.create_arc(archive.Input, temp_arc_file)

                task = executor.submit(self.wszst_compress, self.user_environment.WiimmPath, temp_arc_file, archive.CompressionLevel, archive.Output)
                compress_tasks.append(task)

                for task in as_completed(compress_tasks):
                    returncode, out, err = task.result()
                    if returncode:
                        raise FreighterException(f"Failed to compress the archive {archive.Output} {err.decode('utf-8')}")
                    else:
                        align_szs_archive(archive.Output)
                        print(out.decode("utf-8").strip())
        Logger.info("Finished building archives!")


def align_szs_archive(szs_archive: FilePath):
    with open(szs_archive, "rb") as f:
        archive_bytes = f.read()
        f.close()
    align = 32
    additions = (align - (len(archive_bytes) % align)) % align
    necessary_alignment = len(archive_bytes) % 32
    bb = bytearray(archive_bytes)
    bb.extend(0 for _ in range(additions))
    with open(szs_archive, "wb") as f:
        f.write(bb)
