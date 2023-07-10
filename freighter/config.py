from attrs import define
from os import chdir
from platform import system
from freighter.console import *
from freighter.exceptions import FreighterException
from freighter.path import Path, DirectoryPath, FilePath
from freighter.arguments import Arguments
from freighter.toml import *
from freighter.numerics import UInt
from freighter.colors import *
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
from freighter import rarc
from freighter import obj2grid
import tkinter.filedialog

PLATFORM = system()


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


@define(init=False)
class UserEnvironment(TOMLConfig):
    DevKitProPath: DirectoryPath = tomlfield(required=True)
    DolphinMaps: DirectoryPath = tomlfield()
    DolphinUserPath: DirectoryPath = tomlfield()
    SuperBMDPath: DirectoryPath = tomlfield()
    WiimmPath: DirectoryPath = tomlfield()
    RyujinxAppDataPath: DirectoryPath = tomlfield()
    BinUtilsPaths: dict[str, BinUtils] = tomlfield(required=True)

    def __init__(self) -> None:
        if not USERENVIRONMENT_PATH.exists():
            self.find_dekitppc_bin_folder()
            self.verify_binutils_paths()
            self.find_dolphin_documents_folder()
            self.verify_dolphin()
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
        self.BinUtilsPaths = dict[str, BinUtils]()
        if (self.DevKitProPath / "devkitPPC").exists():
            self.BinUtilsPaths["PowerPC"] = BinUtils.set_from_path(self.DevKitProPath / "devkitPPC/bin", "powerpc-eabi")

        if (self.DevKitProPath / "devkitA64").exists():
            self.BinUtilsPaths["AArch64"] = BinUtils.set_from_path(self.DevKitProPath / "devkitA64/bin", "aarch64-none-elf")

    def find_dekitppc_bin_folder(self) -> None:
        Console.print("Finding devKitPro folder...")
        for path in EXPECTED_DEVKITPRO_PATHS:
            if path.exists():
                self.DevKitProPath = path
                self.set_binutils(path)
                return

        Console.print(f"Freighter could not find your devkitPro folder. Expected to be found at {EXPECTED_DEVKITPRO_PATHS[0]}.\n")
        while not self.verify_binutils_paths():
            if path := open_directory_dialog("Please select your devkitPro folder."):
                self.set_binutils(path)

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
                Console.print(f"binutils for {architecture} good!")
        except:
            Console.print(f"This doesn't seem right. All or some binutils executables were not not found.")
            return False
        return True

    def verify_dolphin(self) -> bool:
        try:
            self.DolphinMaps.assert_exists()
        except:
            Console.print("This doesn't seem right. Maps folder was not found.")
            return False
        Console.print("Dolphin User path good.")
        return True


@define
class SwitchProfile(TOMLObject):
    # Required
    TitleID: str = tomlfield(default="0100e0b019974000", required=True)
    InjectionAddress: UInt = tomlfield(default=UInt(0), required=True)
    IncludeFolders: list[DirectoryPath] = tomlfield(default=[DirectoryPath("includes/")], required=True)
    SourceFolders: list[DirectoryPath] = tomlfield(default=[DirectoryPath("source/")], required=True)
    GameID: str = tomlfield(default="", required=True)
    InputDolFile: FilePath = tomlfield(default=FilePath(), required=True)
    OutputDolFile: FilePath = tomlfield(default=FilePath(), required=True)
    MainNSOPath: FilePath = tomlfield(default=FilePath("main"), required=True)

    # Optional
    TemporaryFilesFolder: DirectoryPath = tomlfield(default=DirectoryPath("temp/"))
    SymbolsFolder: DirectoryPath = tomlfield(default=DirectoryPath("symbols/"))
    LinkerScripts: list[FilePath] = tomlfield(factory=list[FilePath])
    IgnoredSourceFiles: list[FilePath] = tomlfield(factory=list[FilePath])
    IgnoreHooks: list[str] = tomlfield(factory=list[str])
    DiscardLibraryObjects: list[str] = tomlfield(factory=list[str])
    DiscardSections: list[str] = tomlfield(factory=list[str])
    StringHooks: dict[str, str] = tomlfield(factory=dict[str, str])
    CompilerArgs: list[str] = tomlfield(factory=list[str])
    GCCArgs: list[str] = tomlfield(factory=list[str])
    GPPArgs: list[str] = tomlfield(factory=list[str])
    LDArgs: list[str] = tomlfield(factory=list[str])

    @classmethod
    @property
    def default(cls):
        return cls()


@define
class GameCubeProfile(TOMLObject):
    # Required
    InjectionAddress: UInt = tomlfield(default=UInt(0x80000000), required=True, comment="The address where custom code and data will be injected into the .dol")
    IncludeFolders: list[DirectoryPath] = tomlfield(default=list[DirectoryPath](), required=True)
    SourceFolders: list[DirectoryPath] = tomlfield(default=list[DirectoryPath](), required=True)
    GameID: str = tomlfield(default="FREI01", required=True)
    InputDolFile: FilePath = tomlfield(default=DirectoryPath("main.dol"), required=True)
    OutputDolFile: FilePath = tomlfield(default=DirectoryPath("build/sys/main.dol"), required=True)

    # Optional
    SDA: UInt = tomlfield(default=UInt(0))
    SDA2: UInt = tomlfield(default=UInt(0))
    GeckoFolder: DirectoryPath = tomlfield(default=DirectoryPath("gecko/"))
    InputSymbolMap: FilePath = tomlfield(default=FilePath("GPVE01.map"))
    OutputSymbolMapPaths: list[FilePath] = tomlfield(default=list[FilePath]())
    IgnoredGeckoFiles: list[FilePath] = tomlfield(default=list[FilePath]())
    TemporaryFilesFolder: DirectoryPath = tomlfield(default=DirectoryPath("temp/"))
    SymbolsFolder: DirectoryPath = tomlfield(default=DirectoryPath("symbols/"))
    LinkerScripts: list[FilePath] = tomlfield(default=list[FilePath]())
    IgnoredSourceFiles: list[FilePath] = tomlfield(default=list[FilePath]())
    IgnoreHooks: list[str] = tomlfield(default=list[str]())
    DiscardLibraryObjects: list[str] = tomlfield(default=list[str]())
    DiscardSections: list[str] = tomlfield(default=list[str]())
    StringHooks: dict[str, str] = tomlfield(default=dict[str, str]())
    CompilerArgs: list[str] = tomlfield(default=list[str](), comment="Compiler args that apply both gcc or g++ args here")
    GCCArgs: list[str] = tomlfield(default=list[str](), comment="Put C related compiler args here")
    GPPArgs: list[str] = tomlfield(default=list[str](), comment="Put C++ related compiler args here")
    LDArgs: list[str] = tomlfield(default=list[str](), comment="Linker args go here")

    @classmethod
    @property
    def default(cls):
        return cls(InjectionAddress=UInt(0), SourceFolders=[DirectoryPath("source/")], IncludeFolders=[DirectoryPath("includes/")], GameID="FREI01", InputDolFile=FilePath("main.dol"), OutputDolFile=FilePath("build/sys/main.dol"))


@define
class Banner(TOMLObject):
    BannerImage: str = tomlfield(default="banner.png")
    Title: str = tomlfield(default="GameTitle")
    GameName: str = tomlfield(default="GameTitle")
    Maker: str = tomlfield(default="MyOrganization")
    ShortMaker: str = tomlfield(default="MyOrganization")
    Description: str = tomlfield(default="This is my game's description!")
    OutputPath: str = tomlfield(default="build/files/opening.bnr")


PROJECTLIST_PATH = FilePath(FREIGHTER_LOCALAPPDATA / "ProjectList.toml")


# TOML config for storing project paths so you can build projects without having to set the cwd
@define
class ProjectListEntry(TOMLObject):  # This should serialize to [Project.WhateverProjectName]
    ProjectPath: DirectoryPath = tomlfield(required=True)
    ConfigPath: FilePath = tomlfield(required=True)


@define
class ProjectManager(TOMLConfig):
    Projects: dict[str, ProjectListEntry] = tomlfield(required=True)

    def __init__(self):
        self.Projects = {}
        if PROJECTLIST_PATH.exists():
            self.load(PROJECTLIST_PATH)

    def has_project(self, project_name: str):
        return project_name in self.Projects.keys()

    def import_project(self) -> None:
        if (project_dir := open_directory_dialog("Please select a project folder to import it.")) is not None:
            config_path = project_dir.create_filepath("ProjectConfig.toml")
            config_path.assert_exists()
            project_config = ProjectConfig.load(config_path)
            if not self.contains_project(project_config.ProjectName):
                self.Projects[project_config.ProjectName] = ProjectListEntry(project_dir, config_path)
                self.save(PROJECTLIST_PATH)
                Console.print(f'Imported {project_config.ProjectName} from "{config_path}"')
                Console.print(f"To build {project_config.ProjectName} use the command: freighter -build {project_config.ProjectName}")
            exit(0)
        else:
            Console.print("Canceled Project import.")

    def contains_project(self, project_name: str) -> bool:
        if project_name in self.Projects.keys():
            Console.print(f"Freighter already has an imported project under the alias {project_name}", PrintType.ERROR)
            Console.print(self.Projects[project_name])
            return True
        return False

    def new_project(self) -> None:
        while (project_name := input(f"Enter the name of the project:\n{CYAN}")) and self.contains_project(project_name):
            Console.print("A project already exists under that name. Choose a different one.")

        while (project_type := input(f"{AnsiAttribute.RESET}What kind of project? Please enter one of the following options:\n{CYAN}GameCube\nSwitch\n")) is not None and project_type not in ["GameCube", "Switch"]:
            Console.print(f"{project_type} is not a valid option.")

        if not self.contains_project(project_name):
            if (project_dir := open_directory_dialog("Select a folder to initalize a new project!")) is None:
                Console.print("No folder selected. Aborting...")
                exit(0)
            chdir(project_dir)
            config_path = project_dir.create_filepath(DEFAULT_PROJECT_CONFIG_NAME)
            if config_path.exists():
                project_config = ProjectConfig.load(config_path)

                Console.print(f"A project named {project_config.ProjectName} already exists at given path. Did you mean to import it?")
                exit(0)

            if project_type == "GameCube":
                project_config = GameCubeProjectConfig.default
                project_config.ProjectName = project_name
                profile = project_config.Profiles["Debug"]
                profile.IncludeFolders[0].create()
                profile.SourceFolders[0].create()
                profile.SymbolsFolder.create()
                profile.GeckoFolder.create()
                project_config.save(config_path)

            elif project_type == "Switch":
                project_config = SwitchProjectConfig.default
                project_config.ProjectName = project_name
                profile = project_config.Profiles["Debug"]
                profile.IncludeFolders[0].create()
                profile.SourceFolders[0].create()
                profile.SymbolsFolder.create()
                project_config.save(config_path)

            self.Projects[project_name] = ProjectListEntry(project_dir, config_path)
            self.save(PROJECTLIST_PATH)
            project_dir.reveal()
            Console.print(f'Finished created new project "{project_name}"!')
            Console.print(f"To build your project use the command: freighter -build {project_name}")
        exit(0)

    def print(self):
        for project_name, project in self.Projects.items():
            print(f"{project_name}")


@define
class ProjectConfig(TOMLConfig):
    ProjectName: str = tomlfield(init=False)
    TargetArchitecture: str = tomlfield(init=False)
    ConfigPath: FilePath = tomlfield(init=False)
    SelectedProfile: GameCubeProfile | SwitchProfile = tomlfield(init=False)
    Profiles: dict[str, GameCubeProfile | SwitchProfile] = tomlfield(init=False)

    @staticmethod
    def load(config_path: FilePath):
        with open(config_path, "rb") as f:
            toml_dict = tomllib.load(f)
        target = toml_dict["TargetArchitecture"]
        config: GameCubeProjectConfig | SwitchProjectConfig
        if target == "PowerPC":
            config = TOMLConfig.from_toml_dict(GameCubeProjectConfig, toml_dict)
        elif target == "AArch64":
            config = TOMLConfig.from_toml_dict(SwitchProjectConfig, toml_dict)
        else:
            raise FreighterException("wack")
        config.ConfigPath = config_path
        return config

    def set_profile(self, profile_name: str):
        if profile_name:
            self.SelectedProfile = self.Profiles[profile_name]
        else:
            self.SelectedProfile = next(iter(self.Profiles.values()))


@define
class GameCubeProjectConfig(ProjectConfig):
    TargetArchitecture: str = tomlfield(default="PowerPC", required=True)
    ProjectName: str = tomlfield(default="MyGameCubeProject", required=True)
    BannerConfig: Banner = tomlfield(default=Banner(), required=True)
    Profiles: dict[str, GameCubeProfile] = tomlfield(default=dict[str, GameCubeProfile](), required=True)

    @classmethod
    @property
    def default(cls):
        config = cls()
        config.Profiles["Debug"] = GameCubeProfile.default
        return config


@define
class SwitchProjectConfig(ProjectConfig):
    TargetArchitecture: str = tomlfield(default="AArch64", required=True)
    ProjectName: str = tomlfield(default="MySwitchProject", required=True)
    Profiles: dict[str, SwitchProfile] = tomlfield(default=dict[str, SwitchProfile](), required=True)

    @classmethod
    @property
    def default(cls):
        object = cls()
        object.Profiles["Debug"] = SwitchProfile.default
        return object


@define
class SZSArchive(TOMLObject):
    Input: DirectoryPath = tomlfield(required=True)
    Output: FilePath = tomlfield(required=True)
    CompressionLevel: UInt = tomlfield(default=UInt(10))


@define
class BMDModel(TOMLObject):
    Input: FilePath = tomlfield(required=True)
    Output: FilePath = tomlfield(required=True)
    MaterialJSON: FilePath = tomlfield(required=True)
    ExtraArgs: list[str] = tomlfield(default=[])
    Tristrip: str = tomlfield(default="all")
    Rotate: bool = tomlfield(default=True)


@define
class Pikmin2Collision(TOMLObject):
    Input: FilePath = tomlfield(required=True)
    OutputFolder: DirectoryPath = tomlfield(required=True)
    CellSize: UInt = tomlfield(required=True)
    FlipYZ: bool = tomlfield(default=True)


@define(slots=False)
class ProjectFileBuilder(TOMLConfig):
    BMDModels: dict[str, BMDModel] = tomlfield(alias="BMDModel")
    SZSArchives: dict[str, SZSArchive] = tomlfield(alias="SZSArchive")
    Pikmin2Collisions: dict[str, Pikmin2Collision] = tomlfield(alias="Pikmin2Collision")

    def __init__(self, user_environment: UserEnvironment):
        self.user_environment = user_environment
        self.load(FilePath("ProjectFiles.toml"))

    def check_wiimm_path(self):
        if self.SZSArchives and not self.user_environment.WiimmPath:
            if wiimm_path := open_directory_dialog("Please select your Wiimm folder to continue to compress SZS archives."):
                self.user_environment.WiimmPath = wiimm_path
                self.user_environment.save(USERENVIRONMENT_PATH)
            else:
                return False
        return True

    def check_superbmd_path(self):
        if self.BMDModels and not self.user_environment.SuperBMDPath:
            if superbmd_path := open_directory_dialog("Please select your SuperBMD folder to continue the build process."):
                self.user_environment.SuperBMDPath = superbmd_path
                self.user_environment.save(USERENVIRONMENT_PATH)
            else:
                return False
        return True

    def build(self, file_manager):
        import cProfile

        self.build_bmdmodels(file_manager)

        # pr = cProfile.Profile()
        # pr.enable()
        self.build_pikmin2_collision(file_manager)
        # pr.disable()
        # pr.print_stats(sort="cumtime")

        self.build_archives(file_manager)

    def build_bmdmodels(self, file_manager):
        from freighter.filelist import File

        if not self.check_superbmd_path():
            Console.print("Skipping building BMD models as SuperBMD path is not defined.")
            return

        for name, model in self.BMDModels.items():
            model.Input.assert_exists()

            input_model_file = File(file_manager, model.Input)
            if input_model_file.is_hash_same():
                Console.print(f'[{name}] "{model.Input}" is not modified. Skipping...')
                continue
            Console.print(f"[{name}] Building BMD model...")

            args: list[str | PathLike] = [self.user_environment.SuperBMDPath.absolute() / "SuperBMD.exe", model.Input.absolute(), model.Output.absolute()]

            if model.MaterialJSON:
                model.MaterialJSON.assert_exists()
                args += ["--mat", model.MaterialJSON.absolute()]
            if model.Rotate:
                args.append("--rotate")
            if model.Tristrip:
                args += ["--tristrip", model.Tristrip]
            if model.ExtraArgs:
                args += model.ExtraArgs
            subprocess.Popen(args, shell=True, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
        Console.print("Finished building BMD models!")

    def build_pikmin2_collision(self, file_manager):
        from freighter.filelist import File

        for name, collision in self.Pikmin2Collisions.items():
            collision.Input.assert_exists()
            input_obj_file = File(file_manager, collision.Input)
            if input_obj_file.is_hash_same():
                Console.print(f'[{name}] "{collision.Input}" is not modified. Skipping...')
                continue

            Console.print("Generating Pikmin2 collision...")
            obj2grid.generate_collision(collision.Input, collision.OutputFolder, collision.CellSize, collision.FlipYZ)
            Console.print(f"[{name}]Finished generating collision!")

    def wszst_compress(self, wiims_path: DirectoryPath, arc_file: FilePath, compression_level: UInt, szs_output: FilePath):
        args = [wiims_path / "SZS/wszst", "COMPRESS", "--compr", str(compression_level), "--overwrite", arc_file, "-d", szs_output, "--yaz0"]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        os.remove(arc_file)
        return process.returncode, out, err

    def build_archives(self, file_manager):
        if not self.check_wiimm_path():
            Console.print("Skipping building SZS archives as Wiimm path is not defined.")
            return

        with ProcessPoolExecutor() as executor:
            for name, archive in self.SZSArchives.items():
                create_arc_tasks = []
                compress_tasks = []
                temp_arc_file = archive.Output.with_name("temp.arc")
                task = executor.submit(rarc.create_arc, archive.Input, temp_arc_file)
                create_arc_tasks.append(task)

                for task in as_completed(create_arc_tasks):
                    task = executor.submit(self.wszst_compress, self.user_environment.WiimmPath, temp_arc_file, archive.CompressionLevel, archive.Output)
                    compress_tasks.append(task)

                for task in as_completed(compress_tasks):
                    returncode, out, err = task.result()
                    if returncode:
                        raise FreighterException(f"Failed to compress the archive {archive.Output} {err.decode('utf-8')}")
                    else:
                        align_szs_archive(archive.Output)
                        print(out.decode("utf-8").strip())
        Console.print("Finished building archives!")


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
