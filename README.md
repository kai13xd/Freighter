# Okay, what's Freighter?
### Hey there, Kai here.
Freighter is toolkit made for compiling C, C++, or ASM using DevkitPPC for injecting new code/data sections into GameCube/Wii \*.dol executables. This is an extension of Yoshi2's C-Kit I worked on around middle of 2019 because I was abhorred with the methods modders used abusing C.
# Credits
 **[Yoshi2 (RenolY2)](https://github.com/RenolY2)**: The OG who made C-kit who made alot of the tools for Pikmin 2 and MKDD. He helped raise baby Kai when he was first learning hex and figuring out how pointers worked. He made a ton of tools that operate on Gamecube era gamefiles and really made the modding scene pop off. Thank you!

**[Minty Meeo](https://github.com/Minty-Meeo)**: Mostly found around the Pikmin 1 scene but recently has been working on stuff on Pikmin 2. He has made alot of great changes to C-kit such as relocating the stack frame and cleaning up the code for injection hooks.

**YoshiFirebird**: This man helped me ALOT way back when I was first learning C++. He originally had the nice idea of using the `#pragma` keyword where C-kit would preprocess the source file and import the injection address wherever it found it. Saved time having to backtrack to the build.py when I wanted to adjust the codecave site. Also doesn't make intellisense yell at you hah.
# How do install?
> ### ⚠️  **Make sure you are using the latest version of [Python 3.10](https://www.python.org/downloads/).**

Simply install using `pip` on your console of choice:
* Windows: `py -m pip install freighter`
* Unix & Such: `python3 -m pip install freighter`

Dependencies should automatically be downloaded from PyPi.
## Optionals
* [Window's Terminal](https://github.com/microsoft/terminal): It's a nice command-line manager that looks modern, has tabs, and support of emoji unicode characters. ✨ 
* [VSCode](https://code.visualstudio.com/): My go to code editor. Supports Intellisense and it's what I exclusively use. It's got a huge list of extensions that make coding a breeze.

# What next?

Next just create a `build.py` inside your work directory and import the `Project` class.

# Example build.py

Better documentation will come.. when I feel like it.

```py
from freighter import Project

# Pick your poison (compiler args)
common_args = [
    "-O3",
    "-fno-asynchronous-unwind-tables",
    "-fno-exceptions",
]

gcc_args = [
    "-std=c17",  # The C standard to compile with
]

gpp_args = [
    "-std=gnu++2b",  # The C++ standard to compile with
]

ld_args = [
    "-gc-sections",  # Runs garbage collector on unused sections
    # "-print-gc-sections", # Shows what symbols are getting thrown out
]

if __name__ == "__main__":
    # Name your project and it's GameID
    project = Project("MyMod", "GPVE01")

    # Assign compiler args to the project
    project.common_args = common_args
    project.gcc_args = gcc_args
    project.gpp_args = gpp_args
    project.ld_args = ld_args

    # Setting an entry function is essential for -gc-sections to work it's magic. Make sure this function has
    # C linkage
    project.set_entry_function("Entry")

    # If you're lucky to have a Codewarrior map, Freighter can append new symbols for debugging in Dolphin
    project.set_symbol_map("GPVE01.map")

    # You can manually define symbols in a linkerscript file.
    project.add_linkerscript("c_symbols.ld")

    # Add additional map outputs with this method
    project.add_map_output("build/files/GPVE01.map")

    # Imports manually defined symbols in .txt foles found within this folder
    project.add_symbols_folder("symbols/")

    # Use these methods so Freighter doesn't compile these files
    project.ignore_file("source/test.c")
    project.ignore_file("source/test.cpp")

    # You can also add source files explicitly if you want
    project.add_asm_file("itWork.s")
    project.add_c_file("uglyCode.c")
    project.add_cpp_file("coolHacks.cpp")

    # Write a b instruction that points to this symbol's address
    # NOTE: Symbols with C-linkage (declared extern "C") don't need their parameters within ()
    project.hook_branch("cringe", 0x800992C8)

    # Write a bl to this symbol's address at each of these addresses
    project.hook_branchlink("OnUpdateDoStuff(Game::BaseGameSection &)", 0x80102040, 0x8036D7E8, 0x80387F74)

    # Write this symbol's address to a specific location. Useful for overriding vtable pointers.
    project.hook_pointer("doMyStuffInstead(GameObject *, int)", 0x802B6708)

    # Specify the input .dol file and injection location for your code/data
    project.build("pikmin2.dol", 0x80520E00, verbose=True, clean_up=True)
```
