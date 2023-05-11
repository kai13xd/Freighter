import os
from collections.abc import Iterable
from .devkit_tools import Project
from .config import FreighterConfig, UserEnvironment
from .constants import *
from .doltools import *
from .hooks import *
from .version import __version__
from .ansicolor import *
from argparse import _ArgumentGroup, Action, ArgumentParser, RawTextHelpFormatter
from .filelist import FileList
from shutil import rmtree

"▓" "▒" "░"

"▀" "▙" "▜" "▟" "▛"

"▘" "▝" "▖" "▗"

BANNER = f"""
{AnsiAttribute.BLINK}{HOCOTATE_RED}
{HOCOTATE_BEIGE}▗{HOCOTATE_BEIGE_BACKGROUND}                                                                                                             {AnsiAttribute.RESET}{HOCOTATE_BEIGE}▖
{HOCOTATE_BEIGE_BACKGROUND}  {HOCOTATE_RED}██████████▓▒█████████▓▒  █████████▓▒  ██▓▒    ▗▟██████▓▒   ██▓▒   ██▓▒██████▓▒    ██████████▓▒█████████▓▒    
{HOCOTATE_BEIGE_BACKGROUND}  {HOCOTATE_RED}  ██▓▒             ▜██▓▒   ██▓▒       ██▓▒   ▟██▓▒         ██▓▒   ██▓▒    ██▓▒     ██▓▒              ▜██▓▒   
{HOCOTATE_BEIGE_BACKGROUND}  {HOCOTATE_RED}  ██▓▒      ███████████▓▒  ██▓▒       ██▓▒  ▟██▓▒          ██▓▒   ██▓▒    ██▓▒     ██▓▒       ███████████▓▒  
{HOCOTATE_BEIGE_BACKGROUND}  {HOCOTATE_RED}████▓▒██▓▒         ███▓▒ ████▓▒ ██▓▒██████▓▒██▓▒     ██▓▒█████████████▓▓  █████▓▒████▓▒██▓▒         ████▓▒   
{HOCOTATE_BEIGE_BACKGROUND}  {HOCOTATE_RED}  ██▓▒      █████████▓▒    ██▓▒       ██▓▒  ▜██▓▒          ██▓▒   ██▓▒    ██▓▒     ██▓▒       █████████▓▒    
{HOCOTATE_BEIGE_BACKGROUND}  {HOCOTATE_RED}  ██▓▒      ██▓▒  ██▓▒     ██▓▒     ██████▓▒ ▜██▓▒   ██▓▒  ██▓▒   ██▓▒    ██▓▒     ██▓▒       ██▓▒  ██▓▒     
{HOCOTATE_BEIGE_BACKGROUND}  {HOCOTATE_RED}  ██▓▒      ██▓▒  ██▓▒   █████████▓▒  ██▓▒    ▝▜███████▓▒  ██▓▒   ██▓▒    ██▓▒    ██████████▓▒██▓▒  ██▓▒     
{HOCOTATE_BEIGE_BACKGROUND}                                                                                                               
{HOCOTATE_RED_BACKGROUND}                                                                                                               
{HOCOTATE_BEIGE_BACKGROUND}                                                                                                               
{AnsiAttribute.RESET}{HOCOTATE_RED}▝{HOCOTATE_RED_BACKGROUND}                                                                                                             {AnsiAttribute.RESET}{HOCOTATE_RED}▘
{AnsiAttribute.RESET}"""

DESCRIPTION = f"{BANNER}{PURPLE}{__version__}{AnsiAttribute.RESET}"
EPILOG = f"Bug Reports & Issues -> {AnsiAttribute.UNDERLINE}{CYAN}https://github.com/kai13xd/Freighter/issues{AnsiAttribute.RESET}"


class FreighterHelpFormatter(RawTextHelpFormatter):
    def __init__(self, prog, indent_increment=2, max_help_position=64, width=None):
        super().__init__(prog, indent_increment, max_help_position, width)

    # Don't really care for this as help text is already verbose enough
    def add_usage(self, usage: str | None, actions: Iterable[Action], groups: Iterable[_ArgumentGroup], prefix: str | None = None) -> None:
        return

    def add_arguments(self, actions: Iterable[Action]) -> None:
        for action in actions:
            option_strings: list[str] = []
            for option_string in action.option_strings:
                option_strings.append(
                    f'-{ORANGE}{option_string.removeprefix("-")}{AnsiAttribute.RESET}')
            action.option_strings = option_strings
            action.help = f"{CYAN}{action.help}{AnsiAttribute.RESET}"
            self.add_argument(action)


parser = ArgumentParser(description=DESCRIPTION,
                        epilog=EPILOG,
                        prefix_chars="-",
                        add_help=False,
                        formatter_class=FreighterHelpFormatter)

parser.add_argument("-h", "-help", action="help",
                    help="Shows this help prompt.")

parser.add_argument("-build",  metavar="[profile name]",
                    default="Default",
                    const="Default",
                    nargs='?',
                    help="Builds the project with the selected profile. Defaults to first profile if no arguments are passed.")

parser.add_argument("-project", metavar="[project directory]",
                    help=f"The project directory containing a {DEFAULT_CONFIG_PATH}. If this option is not passed, Freighter assumes the current working directory is the project directory")

parser.add_argument("-config", metavar="[path to TOML file]",
                    help="Overrides the default project config path.")

parser.add_argument("-userenv", metavar="[path to TOML file]",
                    help="Overrides the default user environment config path.")

parser.add_argument("-cleanup", action="store_true",
                    help="Removes temporary files folder after build")

parser.add_argument("-verbose", action="store_true",
                    help="Print extra info to the console")
args = parser.parse_args()


def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    if not args.build:
        parser.print_help()
        parser.exit()

   
    if args.userenv:
        UserEnvironment.load(args.userenv)
    else:
        UserEnvironment.load()

    if args.project:
        os.chdir(args.project)

    if args.config:
        FreighterConfig.load(args.config)
    else:
        FreighterConfig.load()

    FileList.init()
    FileList.add(FreighterConfig.project_toml_path)
    
    if args.build:
        FreighterConfig.set_project_profile(args.build)
        project = Project()
        project.build()

    if args.cleanup:
        print(f"{CYAN}Cleaning up temporary files\n")
        rmtree(FreighterConfig.project.TemporaryFilesFolder)
