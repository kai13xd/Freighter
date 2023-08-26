from argparse import ONE_OR_MORE, Action, ArgumentParser, RawTextHelpFormatter, _ArgumentGroup
from collections.abc import Iterable
from attrs import define

from freighter import __version__
from freighter.path import DirectoryPath
from freighter.colors import *


"▓▒░"

"▀▙▜▟▛"

"▘▝▖▗"


BANNER = f"""
{HOCOTATE_BEIGE}▗{HOCOTATE_BEIGE.background}                                                                                                             {AnsiAttribute.RESET}{HOCOTATE_BEIGE}▖{HOCOTATE_RED}{AnsiAttribute.BLINK}
{HOCOTATE_BEIGE.background}  ██████████▓▒█████████▓▒  █████████▓▒  ██▓▒    ▗▟██████▓▒   ██▓▒   ██▓▒██████▓▒    ██████████▓▒█████████▓▒    
{HOCOTATE_BEIGE.background}    ██▓▒             ▜██▓▒   ██▓▒       ██▓▒   ▟██▓▒         ██▓▒   ██▓▒    ██▓▒     ██▓▒              ▜██▓▒   
{HOCOTATE_BEIGE.background}    ██▓▒      ███████████▓▒  ██▓▒       ██▓▒  ▟██▓▒          ██▓▒   ██▓▒    ██▓▒     ██▓▒       ███████████▓▒  
{HOCOTATE_BEIGE.background}  ████▓▒██▓▒         ███▓▒ ████▓▒ ██▓▒██████▓▒██▓▒     ██▓▒█████████████▓▓  █████▓▒████▓▒██▓▒         ████▓▒   
{HOCOTATE_BEIGE.background}    ██▓▒      █████████▓▒    ██▓▒       ██▓▒  ▜██▓▒          ██▓▒   ██▓▒    ██▓▒     ██▓▒       █████████▓▒    
{HOCOTATE_BEIGE.background}    ██▓▒      ██▓▒  ██▓▒     ██▓▒     ██████▓▒ ▜██▓▒   ██▓▒  ██▓▒   ██▓▒    ██▓▒     ██▓▒       ██▓▒  ██▓▒     
{HOCOTATE_BEIGE.background}    ██▓▒      ██▓▒  ██▓▒   █████████▓▒  ██▓▒    ▝▜███████▓▒  ██▓▒   ██▓▒    ██▓▒    ██████████▓▒██▓▒  ██▓▒     
{HOCOTATE_BEIGE.background}                                                                                                               
{HOCOTATE_BEIGE.background}                                                                                                               
{HOCOTATE_BEIGE.background}                                                                                                               
{AnsiAttribute.RESET}{HOCOTATE_RED}▝{HOCOTATE_RED.background}                                                                                                             {AnsiAttribute.RESET}{HOCOTATE_RED}▘
{AnsiAttribute.RESET}"""

DESCRIPTION = f"{BANNER}{PURPLE}v{__version__}{AnsiAttribute.RESET}"
EPILOG = f"Bug Reports & Issues -> {AnsiAttribute.UNDERLINE}{CYAN}https://github.com/kai13xd/Freighter/issues{AnsiAttribute.RESET}\n"


class FreighterHelpFormatter(RawTextHelpFormatter):
    def __init__(self, prog, indent_increment=2, max_help_position=4, width=200):
        super().__init__(prog, indent_increment, max_help_position, width)

    # Don't really care for this as help text is already verbose enough
    def add_usage(self,a,b,c) -> None:
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
    @define
    class BuildArg:
        project_name: str
        profile_name: str = ""

    new: bool = False
    build: BuildArg | None = None
    importarg: DirectoryPath | None = None
    clean: bool = False
    reset: bool = False
    verbose: bool = False
    debug: bool = False
    appdata: bool = False
    parser = ArgumentParser(description=DESCRIPTION, epilog=EPILOG, add_help=False, prefix_chars="-", formatter_class=FreighterHelpFormatter)

    @classmethod
    def parse_args(cls) -> None:
        cls.parser.add_argument("-help", action="store_true", help="Shows the help prompt.")

        cls.parser.add_argument("-new", action="store_true", help="Generates a new project.")

        cls.parser.add_argument(
            "-build",
            metavar="<Project Name> [Profile]",
            nargs=ONE_OR_MORE,
            help="Builds the project with the selected profile.\nDefaults to first profile in the config if no arguments are passed.",
        )
        cls.parser.add_argument("-import", action="store_true", dest="importarg", help="Opens a filedialog to import a project directory into Freighter's ProjectManager.")

        cls.parser.add_argument("-clean", action="store_true", help="Removes all temporary files and resets the cache. Useful if Freighter throws an error about missing symbols if the filecache becomes bad.")

        cls.parser.add_argument("-verbose", action="store_true", help="Print verbose information to the console")
        cls.parser.add_argument("-debug", action="store_true", help="Print debug and verbose information to the console")
        cls.parser.add_argument("-reset", action="store_true", help="Reconfigures your UserEnvironment.toml")
        cls.parser.add_argument("-appdata", action="store_true", help="Reveals the Freighter AppData folder")
        parsed_args = cls.parser.parse_args()

        cls.help = parsed_args.help

        if parsed_args.build:
            cls.build = cls.BuildArg(*parsed_args.build)

        cls.new = parsed_args.new
        cls.importarg = parsed_args.importarg

        cls.clean = parsed_args.clean
        cls.verbose = parsed_args.verbose
        cls.debug = parsed_args.debug
        cls.reset = parsed_args.reset
        cls.appdata = parsed_args.appdata

    @classmethod
    def print_help(cls):
        cls.parser.print_help()
        exit(0)


Arguments.parse_args()
