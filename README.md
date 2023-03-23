# Hey there, Kai here

Freighter is toolkit made for compiling C, C++, or ASM using devkitPro for injecting code and data sections into GameCube/Wii DOL executables. This is an extension of Yoshi2's C-Kit I worked on around middle of 2019 because I wanted to utilize the elegance and stricter typing of C++.

# Installation
>
> ### ⚠️  **Make sure you are using the latest version of [Python 3.11](https://www.python.org/downloads/).**

Simply install using `pip` on your console of choice:

* Windows: `py -m pip install freighter`
* Unix & Such: `python3 -m pip install freighter`

Dependencies should automatically be downloaded from PyPi.

## If you are running Freighter locally you will need to install these package dependencies with `pip`

```
pip install colorama
pip install dacite
pip install dolreader
pip install pyelftools
pip install geckolibs
```

# Reccommendations

* [Window's Terminal](https://github.com/microsoft/terminal): It's a nice command-line manager that looks modern, has tabs, and support of emoji unicode characters. ✨
* [VSCode](https://code.visualstudio.com/): My go to code editor. Supports Intellisense and it's what I exclusively use. It's got a huge list of extensions that make coding a breeze.

# Configuration

Freighter operates between a python file and a TOML configuration file.

## ProjectConfig.toml

Subject to major changes

```toml
# The default ProjectProfile to use as fallback
DefaultProjectProfile = "Debug"

# You can specify a UserEnviornment that will tell Freighter where important paths are.
# Currently Freighter derieves your profile by your computer's username
[UserEnvironment.Kai]
UseProjectProfile = "Debug"
DolphinDocumentsFolder = "C:/Users/Kai/Documents/Dolphin Emulator"
DevKitPPCFolder = "C:/devkitPro/devkitPPC/bin/"

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

## Example build.py

I am considering removing the use of .py file for building and make Freighter completely commandline based.

```py
from freighter import Project

if __name__ == "__main__":
    # Specify the config to use
    project = Project("ProjectConfig.toml")

    # Write a b instruction that points to this symbol's address
    # NOTE: Symbols with C-linkage (declared extern "C") don't need their parameters within ()
    project.hook_branch("cringe", 0x800992C8)

    # Write a bl to this symbol's address at each of these addresses
    project.hook_branchlink("OnUpdateDoStuff(Game::BaseGameSection &)", 0x80102040, 0x8036D7E8, 0x80387F74)

    # Write this symbol's address to a specific location. Useful for overriding vtable pointers.
    project.hook_pointer("doMyStuffInstead(GameObject *, int)", 0x802B6708)

    # Build 
    project.build()
```

# Credits

 **[Yoshi2 (RenolY2)](https://github.com/RenolY2)**: The OG who made C-kit who made alot of the tools for Pikmin 2 and MKDD. He helped raise baby Kai when he was first learning hex and figuring out how pointers worked. He made a ton of tools that operate on Gamecube era gamefiles and really made the modding scene pop off. Thank you!

**[Minty Meeo](https://github.com/Minty-Meeo)**: Mostly found around the Pikmin 1 scene but recently has been working on stuff on Pikmin 2. He has made alot of great changes to C-kit such as relocating the stack frame and cleaning up the code for injection hooks.

**YoshiFirebird**: This man helped me ALOT way back when I was first learning C++. He originally had the nice idea of using the `#pragma` keyword where C-kit would preprocess the source file and import the injection address wherever it found it. Saved time having to backtrack to the build.py when I wanted to adjust the codecave site. Also doesn't make intellisense yell at you hah.
