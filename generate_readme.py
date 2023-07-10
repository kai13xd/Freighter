from freighter.arguments import Arguments
from freighter.config import *

options = ""
for name, option in Arguments.parser._option_string_actions.items():
    metavar = option.metavar if option.metavar is not None else ""
    options += f"\n{name} {metavar}: {option.help}\n"

commandline_string = f"""# Command Line\n
After installation open your cli of choice and enter `freighter`\n
## Options\n
```{options}```
"""


if __name__ == "__main__":
    with open("README.md", "w+") as f:
        f.write(f"""# About Freighter

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

{commandline_string}

# Project Configuration

Freighter uses TOML configuration format your modding projects.
You can generate a new project by using `freighter new ProjectName`

## ProjectConfig.toml

```toml
{GameCubeProjectConfig.default}
```

# Credits

**[Yoshi2 (RenolY2)](https://github.com/RenolY2)**: The OG who made C-kit who made alot of the tools for Pikmin 2 and MKDD. He helped raise baby Kai when he was first learning hex and figuring out how pointers worked. He made a ton of tools that operate on Gamecube era gamefiles and really made the modding scene pop off. Thank you!

**[Minty Meeo](https://github.com/Minty-Meeo)**: He has made alot of great changes to C-kit such as relocating the stack frame and cleaning up the code for injection hooks.

**Yoshifirebird**: This man helped me a TON way back when I was first learning C++. He was the one who had the original idea of using the `#pragma` keyword so Freighter could preprocess the source file to extract the symbol name and the hook injection address. This is a great feature because you can write the injection address inline with your code that you can easily copy paste into Ghidra to
""")
