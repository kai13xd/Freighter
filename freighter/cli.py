import os
from sys import exit
from argparse import Action, ArgumentParser, Namespace, RawTextHelpFormatter, _ArgumentGroup, ONE_OR_MORE
from collections.abc import Callable, Iterable, Sequence
from shutil import rmtree
from typing import Any
from .config import *

from .ansicolor import *
from .config import FreighterConfig, UserEnvironment
from .console import *
from .project import FreighterProject
from .doltools import *
from .filelist import FileList, File
from .hooks import *
from .version import __version__

"▓▒░"

"▀▙▜▟▛"

"▘▝▖▗"

BANNER = f"""
{HOCOTATE_BEIGE}▗{HOCOTATE_BEIGE_BACKGROUND}                                                                                                             {AnsiAttribute.RESET}{HOCOTATE_BEIGE}▖{HOCOTATE_RED}{AnsiAttribute.BLINK}
{HOCOTATE_BEIGE_BACKGROUND}  ██████████▓▒█████████▓▒  █████████▓▒  ██▓▒    ▗▟██████▓▒   ██▓▒   ██▓▒██████▓▒    ██████████▓▒█████████▓▒    
{HOCOTATE_BEIGE_BACKGROUND}    ██▓▒             ▜██▓▒   ██▓▒       ██▓▒   ▟██▓▒         ██▓▒   ██▓▒    ██▓▒     ██▓▒              ▜██▓▒   
{HOCOTATE_BEIGE_BACKGROUND}    ██▓▒      ███████████▓▒  ██▓▒       ██▓▒  ▟██▓▒          ██▓▒   ██▓▒    ██▓▒     ██▓▒       ███████████▓▒  
{HOCOTATE_BEIGE_BACKGROUND}  ████▓▒██▓▒         ███▓▒ ████▓▒ ██▓▒██████▓▒██▓▒     ██▓▒█████████████▓▓  █████▓▒████▓▒██▓▒         ████▓▒   
{HOCOTATE_BEIGE_BACKGROUND}    ██▓▒      █████████▓▒    ██▓▒       ██▓▒  ▜██▓▒          ██▓▒   ██▓▒    ██▓▒     ██▓▒       █████████▓▒    
{HOCOTATE_BEIGE_BACKGROUND}    ██▓▒      ██▓▒  ██▓▒     ██▓▒     ██████▓▒ ▜██▓▒   ██▓▒  ██▓▒   ██▓▒    ██▓▒     ██▓▒       ██▓▒  ██▓▒     
{HOCOTATE_BEIGE_BACKGROUND}    ██▓▒      ██▓▒  ██▓▒   █████████▓▒  ██▓▒    ▝▜███████▓▒  ██▓▒   ██▓▒    ██▓▒    ██████████▓▒██▓▒  ██▓▒     
{HOCOTATE_BEIGE_BACKGROUND}                                                                                                               
{HOCOTATE_RED_BACKGROUND}                                                                                                               
{HOCOTATE_BEIGE_BACKGROUND}                                                                                                               
{AnsiAttribute.RESET}{HOCOTATE_RED}▝{HOCOTATE_RED_BACKGROUND}                                                                                                             {AnsiAttribute.RESET}{HOCOTATE_RED}▘
{AnsiAttribute.RESET}"""

DESCRIPTION = f"{BANNER}{PURPLE}v{__version__}{AnsiAttribute.RESET}"
EPILOG = f"Bug Reports & Issues -> {AnsiAttribute.UNDERLINE}{CYAN}https://github.com/kai13xd/Freighter/issues{AnsiAttribute.RESET}\n"


class FreighterHelpFormatter(RawTextHelpFormatter):
    def __init__(self, prog, indent_increment=2, max_help_position=4, width=200):
        super().__init__(prog, indent_increment, max_help_position, width)

    # Don't really care for this as help text is already verbose enough
    def add_usage(self, usage: str | None, actions: Iterable[Action], groups: Iterable[_ArgumentGroup], prefix: str | None = None) -> None:
        return

    def add_arguments(self, actions: Iterable[Action]) -> None:
        for action in actions:
            option_strings: list[str] = []
            for option_string in action.option_strings:
                option_strings.append(f'-{ORANGE}{option_string.removeprefix("-")}{AnsiAttribute.RESET}')
            action.option_strings = option_strings
            action.help = f"{CYAN}{action.help}{AnsiAttribute.RESET}"
            self.add_argument(action)


class Arguments:
    parser = ArgumentParser(description=DESCRIPTION, epilog=EPILOG, formatter_class=FreighterHelpFormatter, prefix_chars="-")
    build: str
    new: list[str]
    clean: bool
    project: None
    config: None
    reset: bool
    verbose: bool

    @classmethod
    def parse_args(cls) -> None:
        cls.parser.add_argument("-help", action="store_true", help="Shows the help prompt.")

        cls.parser.add_argument("-new", metavar="<Project Name> [Path]", nargs=ONE_OR_MORE, help="Generates a new project at the current working directory with the specified project name.")

        cls.parser.add_argument(
            "-build",
            metavar="profile name",
            const="Default",
            nargs="?",
            help="Builds the project with the selected profile.\nDefaults to first profile if no arguments are passed.",
        )

        cls.parser.add_argument(
            "-project",
            metavar="[project directory]",
            help=f"The project directory containing a {DEFAULT_PROJECT_CONFIG_NAME}.\nIf this option is not passed, Freighter assumes the current working directory is the project directory",
        )

        cls.parser.add_argument("-config", metavar="[path to TOML file]", help="Overrides the default project config path.")

        cls.parser.add_argument("-clean", action="store_true", help="Removes all temporary files and resets the cache. Useful if Freighter throws an error about missing symbols if the filecache becomes bad.")

        cls.parser.add_argument("-verbose", action="store_true", help="Print extra info to the console")

        cls.parser.add_argument("-reset", action="store_true", help="Reconfigures your UserEnvironment.toml")

        args = cls.parser.parse_args()

        cls.help = args.help
        cls.new = args.new
        cls.build = args.build
        cls.project = args.project
        cls.config = args.config
        cls.clean = args.clean
        cls.verbose = args.verbose
        cls.reset = args.reset

    @classmethod
    def print_help(cls):
        cls.parser.print_help()
        exit(0)


Arguments.parse_args()


if Arguments.build or Arguments.project:
    UserEnvironment(Arguments.reset)

    try:
        if Arguments.project:
            os.chdir(Path(Arguments.project).absolute())
    except:
        pass

    FileList.init()

    if Arguments.config:
        FreighterConfig(Arguments.config)
    else:
        FreighterConfig()
    FreighterConfig.set_project_profile(Arguments.build)

    File(FreighterConfig.project_toml_path)


def main():
    if Arguments.new:
        FreighterConfig.generate_project()
        exit(0)

    os.system("cls" if os.name == "nt" else "clear")
    if not Arguments.build and not Arguments.clean:
        Arguments.print_help()

    if Arguments.clean:
        cleanup()

    if Arguments.build:
        project = FreighterProject()
        project.build()


def cleanup():
    console_print(f'{CYAN}Attempting to clean up temporary files at "{Path(FreighterConfig.profile.TemporaryFilesFolder).absolute().as_posix()}"')
    if dir_exists(FreighterConfig.profile.TemporaryFilesFolder):
        rmtree(FreighterConfig.profile.TemporaryFilesFolder)
        console_print("Removed temporary files.")
    else:
        console_print("Nothing to clean up.")
