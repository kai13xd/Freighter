# About Freighter

Freighter is command-line based toolkit for setting up and building C/C++ projects using devkitPro for injecting custom code into GameCube/Wii DOL executables. This is a heavily modified fork of Yoshi2's C-Kit that add features such as:

- Project management using TOML configuration files
- Incremental build support utilizing multiprocessing

# Installation

> ### Ensure you are using the latest version of `Python 3.11 or greater` -> https://www.python.org/downloads/).\*\*

This package is made available through PyPi:

- Windows: `py -m pip install freighter`
- Unix & Such: `python3 -m pip install freighter`

# Reccommendations

- [Window's Terminal](https://github.com/microsoft/terminal): Supports ANSI color codes and unicode emoji characters that Freighter uses to colorize the console ouput.
- [VSCode](https://code.visualstudio.com/)

# Configuration

Freighter is a command line based tool that uses TOML configuration format for your C/C++ projects.

## ProjectConfig.toml

```toml
# The default ProjectProfile to use as fallback
DefaultProjectProfile = "Debug"



# This defines a ProjectProfile that passes all important project information about
# how to build your source files to Freighter
[ProjectProfile.Debug]
Name = "MyModdingProject"
GameID = "GAME01"
InputSymbolMap = "GPVE01.map"
SDA = 0x8051C5C0
SDA2 = 0x8051E2A0
EntryFunction = "Entry"
InputDolFile = "main.dol"
InjectionAddress = 0x80520E00
OutputDolFile = "build/sys/main.dol"
SymbolMapOutputPaths = ["build/files/Pikmin2UP.map"]
LinkerScripts = ["linkerscript.ld"]
SourceFolders = ["souce/"]
IncludeFolders = ["source/headers/"]
IgnoredSourceFiles = ["source/some.c", "souce/some.cpp"]
VerboseOutput = true
CleanUpTemporaryFiles = false
CommonArgs = [
    "-O3",
    "-fno-exceptions",
    "-Wall",

]
GCCArgs = [
    "-std=c17", # The C standard to compile with
]
GPPArgs = [
    "-std=gnu++2b", # The C++ standard to compile with
]
LDArgs = [
    "-print-gc-sections",   # Shows what symbols are getting thrown out
]
```
## UserEnv.toml

```toml
# While Freighter does it's best to find external tools you can define explicit paths if they are installed in a non-default way
DolphinDocumentsFolder = "C:/Users/Kai/Documents/Dolphin Emulator"
DevKitPPCFolder = "F:/devkitPro/devkitPPC/bin/"
```

# Credits

**[Yoshi2 (RenolY2)](https://github.com/RenolY2)**: The OG who made C-kit who made alot of the tools for Pikmin 2 and MKDD. He helped raise baby Kai when he was first learning hex and figuring out how pointers worked. He made a ton of tools that operate on Gamecube era gamefiles and really made the modding scene pop off. Thank you!

**[Minty Meeo](https://github.com/Minty-Meeo)**: Mostly found around the Pikmin 1 scene but recently has been working on stuff on Pikmin 2. He has made alot of great changes to C-kit such as relocating the stack frame and cleaning up the code for injection hooks.

**YoshiFirebird**: This man helped me ALOT way back when I was first learning C++. He originally had the nice idea of using the `#pragma` keyword where C-kit would preprocess the source file and import the injection address wherever it found it. Saved time having to backtrack to the build.py when I wanted to adjust the codecave site. Also doesn't make intellisense yell at you hah.
