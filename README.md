# Okay, what's Freighter?
Hey there, Kai here. Freighter is toolkit made for compiling C, C++, or ASM using DevkitPPC for injecting new code/data sections into GameCube/Wii \*.dol executables. This is an extension of Yoshi2's C-Kit I worked on around middle of 2019 because I was abhorred with the methods modders used abusing C.

# How do install?
Simply install using `pip` on your console of choice:

Windows:
`py -m pip install freighter`

Unix & Such:
`python3 -m pip install freighter`

It should just install all of the necessary dependencies. It better..

# What next?
Next just create a `build.py` inside your work directory and import the `Project` class. 

Freighter does it's best to automatically fetch include and source directories so that you don't have to worry about passing those arguments to the compiler.

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
    
    # Set the injection address for your code and data
    project.set_base_address(0x80520E00)
    
    # Setting an entry function is essential for -gc-sections to work it's magic. Make sure this function has 
    # C linkage
    project.set_entry_function("Entry")
    
    # If you're lucky to have a Codewarrior map, Freighter can append new symbols for debugging in Dolphin
    project.set_symbol_map("GPVE01.map") 
    
    # You can manually define symbols in a linkerscript file.
    project.add_linkerscript("c_symbols.ld")
    
    # Freighter will attempt to automatically output a .map file to your Dolphin's Map folder if it can find it
    # Add additional map outputs with this method
    project.add_map_output("build/files/GPVE01.map")

    project.add_gecko_folder("gecko/")
    project.add_symbols_folder("symbols/")

    # Freighter will attempt to auto import all source files within this folder
    project.add_source_folder("source/")

    # Freighter will remove these files added with add_source_folder
    project.ignore_c_file("source/test.c")
    project.ignore_cpp_file("source/test.cpp")

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

    # Specify the input .dol file and build
    project.build("pikmin2.dol", verbose=True, clean_up=True)
```