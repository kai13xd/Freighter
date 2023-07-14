# About Freighter

Freighter is command-line based toolkit for setting up and building C/C++ projects using devkitPro for injecting custom code into GameCube/Wii DOL executables. This is a heavily modified fork of Yoshi2's C-Kit that add features such as:

- Project management using TOML configuration files
- Incremental build support utilizing multiprocessing
- Generating .bnr file to customize the banner that is read from Dolphin and the GameCube BIOS.

# Installation

> ### Ensure you are using the latest version of `Python 3.11 or greater` -> https://www.python.org/downloads/

This package is made available through PyPi:

- Windows: `py -m pip install freighter`
- Unix & Such: `python3 -m pip install freighter`

# Reccommendations

- [Window's Terminal](https://github.com/microsoft/terminal): Supports ANSI color codes and unicode emoji characters that Freighter uses to colorize the console ouput.
- [VSCode](https://code.visualstudio.com/): Personal perferred code editor that is feature rich thanks to the community.
- [Ghidra](https://ghidra-sre.org/): A GameCube modder's best friend

# Command Line

After installation open your cli of choice and enter `freighter`

## Options

```
-help : Shows the help prompt.

-new : Generates a new project.

-build <Project Name> [Profile]: Builds the project with the selected profile.
Defaults to first profile in the config if no arguments are passed.

-import : Opens a filedialog to import a project directory into Freighter's ProjectManager.

-clean : Removes all temporary files and resets the cache. Useful if Freighter throws an error about missing symbols if the filecache becomes bad.

-verbose : Print verbose information to the console

-debug : Print debug and verbose information to the console

-reset : Reconfigures your UserEnvironment.toml

-appdata : Reveals the Freighter AppData folder
```


# Project Configuration

Freighter uses TOML configuration format your modding projects.
You can generate a new project by using `freighter new ProjectName`

## ProjectConfig.toml

```toml
TargetArchitecture = "PowerPC"
ProjectName = "MyGameCubeProject"

[BannerConfig]
BannerImage = "banner.png"	# Path to a 96 x 32 image file
Title = "GameTitle"
GameTitle = "GameTitle"	# Game title displayed in GC Bios/Dolphin
Maker = "MyOrganization"	# Your name, organization, or group
ShortMaker = "MyOrganization"	# Optionally shortened Maker name
Description = "This is my game's description!"	# Game description displayed in GC Bios/Dolphin
OutputPath = "build/files/opening.bnr"	# Changes the output of the .bnr file


[Profiles.Debug]
InjectionAddress = 0x0	# The address where custom code and data will be injected into the .dol
IncludeFolders = ["includes"]	# Directory paths containing source files
SourceFolders = ["source"]	# Directory paths containing header files
GameID = "FREI01"	# A 6-character string to represent the game id
InputDolFile = "main.dol"
OutputDolFile = "build/sys/main.dol"
Libraries = []	# Paths to library objects to link with
LinkerScripts = []	# Paths to linkerscripts to link with
SymbolsFolder = "symbols"	# Directory path containing symbol definitions.
DiscardLibraryObjects = []	# Library object files to discard during linking
DiscardSections = []	# Sections to discard during linking
IgnoredSourceFiles = []	# List of source file paths to tell Freighter not to compile and link with
IgnoreHooks = []	# List of #pragma hooks to ignore after link phase
TemporaryFilesFolder = "temp"	# Directory path to output temporary build artifacts to a different folder
StringHooks = {}	# A table of strings to inject into final binary at a specific address
CompilerArgs = []	# Compiler args that apply both gcc or g++ args here
GCCArgs = []	# Put C related compiler args here
GPPArgs = []	# Put C++ related compiler args here
LDArgs = []	# Linker args go here
SDA = 0x0	# Defines the SDA (r2) register value
SDA2 = 0x0	# Defines the SDA2 (r13) register value
GeckoFolder = "gecko"
InputSymbolMap = "GPVE01.map"	# Path to a CodeWarrior map file Freighter will use to append new symbols to aid debugging with Dolphin emulator
OutputSymbolMapPaths = []	# File paths to place generated CodeWarrior map.
IgnoredGeckoFiles = []	# Any gecko txt files that should be ignored when patched into the .dol


```

# Credits

**[Yoshi2 (RenolY2)](https://github.com/RenolY2)**: The OG who made C-kit who made alot of the tools for Pikmin 2 and MKDD. He helped raise baby Kai when he was first learning hex and figuring out how pointers worked. He made a ton of tools that operate on Gamecube era gamefiles and really made the modding scene pop off. Thank you!

**[Minty Meeo](https://github.com/Minty-Meeo)**: He has made alot of great changes to C-kit such as relocating the stack frame and cleaning up the code for injection hooks.

**Yoshifirebird**: This man helped me a TON way back when I was first learning C++. He was the one who had the original idea of using the `#pragma` keyword so Freighter could preprocess the source file to extract the symbol name and the hook injection address. This is a great feature because you can write the injection address inline with your code that you can easily copy paste into Ghidra to
