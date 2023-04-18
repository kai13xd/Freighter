import re
import subprocess
from collections import defaultdict
from glob import glob
from concurrent.futures import ProcessPoolExecutor, as_completed
from os import makedirs, remove, removedirs
import os
from pathlib import Path
from dolreader.dol import DolFile
from dolreader.section import DataSection, Section, TextSection
from elftools.elf.elffile import ELFFile, SymbolTableSection
from geckolibs.gct import GeckoCodeTable, GeckoCommand
import sys
from dataclasses import dataclass
from time import time
from .config import *
from .constants import *
from .hooks import *
from functools import cache
import hashlib


def delete_file(filepath: str) -> bool:
    try:
        remove(filepath)
        return True
    except FileNotFoundError:
        return False


def delete_dir(path: str) -> bool:
    try:
        for file in glob(path + "*", recursive=True):
            delete_file(file)
        removedirs(path)
        return True
    except FileNotFoundError:
        return False


def strip_comments(line: str):
    return line.split("//")[0].strip()


@dataclass
class Symbol:
    name = ""
    demangled_name = ""
    section = ""
    address = 0
    hex_address = ""
    size = 0
    is_complete_constructor = False
    is_base_constructor = False
    is_undefined = True
    is_weak = False
    is_function = False
    is_data = False
    is_bss = False
    is_rodata = False
    is_c_linkage = False
    is_manually_defined = False
    is_written_to_ld = False
    source_file = ""
    library_file = ""

    def __repr__(self) -> str:
        if self.is_c_linkage:
            return self.name
        else:
            return f"{self.demangled_name}"

    def __hash__(self):
        return hash((self.name, self.demangled_name, self.address, self.address))


class Project:
    config: FreighterConfig
    project: ProjectProfile
    user_env: UserEnvironment
    bin_data: bytearray
    library_folders: str
    c_files = list[str]()
    symbols = defaultdict(Symbol)
    gecko_meta = []
    cpp_files = list[str]()
    asm_files = list[str]()
    object_files = list[str]()
    static_libs = list[str]()
    hooks = list[Hook]()

    def __init__(self, project_toml_filepath: str, userenv_toml_filepath: str = ""):
        self.config = FreighterConfig(project_toml_filepath, userenv_toml_filepath)
        self.project: ProjectProfile = self.config.project_profile
        self.user_env: UserEnvironment = self.config.user_env
        if not self.project.InjectionAddress:
            self.project.InjectionAddress = self.dol.lastSection.address + self.dol.lastSection.size
            print(
                f"{FWHITE}Base address auto-set from ROM end: {FLBLUE}{self.project.InjectionAddress:x}\n"
                f"{FWHITE}Do not rely on this feature if your DOL uses .sbss2\n"
            )
        if self.project.InjectionAddress % 32:
            print("Warning!  DOL sections must be 32-byte aligned for OSResetSystem to work properly!\n")
        if self.project.SDA and self.project.SDA2:
            self.project.CommonArgs += ["-msdata=sysv"]
            self.project.LDArgs += [f"--defsym=_SDA_BASE_={hex(self.project.SDA)}", f"--defsym=_SDA2_BASE_={hex(self.project.SDA2)}"]
        if self.project.InputSymbolMap:
            assert_file_exists(self.project.InputSymbolMap)
            self.project.SymbolMapOutputPaths.append(self.user_env.DolphinDocumentsFolder + "Maps/" + self.project.GameID + ".map")
        self.project_objfile = self.project.BuildPath + self.project.Name + ".o"
        self.gecko_table = GeckoCodeTable(self.project.GameID, self.project.Name)
        self.dol = DolFile(open(self.project.InputDolFile, "rb"))

    def dump_objdump(self, objectfile_path: str, *args: str, outpath: str = "") -> str:
        """Dumps the output from DevKitPPC's powerpc-eabi-objdump.exe to a .txt file"""
        args = (self.user_env.DevKitPPCBinFolder + OBJDUMP, objectfile_path) + args
        if not outpath:
            outpath = self.project.TemporaryFilesFolder + objectfile_path.split("/")[-1] + ".s"
        with open(outpath, "w") as f:
            subprocess.call(args, stdout=f)
        return outpath

    def dump_nm(self, object_path: str, *args: str, outpath: str = "") -> str:
        """Dumps the output from DevKitPPC's powerpc-eabi-nm.exe to a .txt file"""
        args = (self.user_env.DevKitPPCBinFolder + NM, object_path) + args
        if not outpath:
            outpath = self.project.TemporaryFilesFolder + object_path.split("/")[-1].rstrip(".o") + ".nm"
        with open(outpath, "w") as f:
            subprocess.call(args, stdout=f)
        return outpath

    def dump_readelf(self, object_path: str, *args: str, outpath: str = "") -> str:
        """Dumps the output from DevKitPPC's powerpc-eabi-readelf.exe to a .txt file"""
        args = (self.user_env.DevKitPPCBinFolder + READELF, object_path) + args
        if not outpath:
            outpath = self.project.TemporaryFilesFolder + object_path.split("/")[-1] + ".readelf"
        with open(outpath, "w") as f:
            subprocess.call(args, stdout=f)
        return outpath

    def build(self) -> None:
        os.system("cls||clear")
        build_start_time = time()
        makedirs(self.project.TemporaryFilesFolder, exist_ok=True)
        self.__get_source_files()
        self.__process_pragmas()
        compile_start_time = time()
        self.__compile()
        self.compile_time = time() - compile_start_time
        self.__load_symbol_definitions()
        self.__generate_linkerscript()
        self.__link()
        self.__process_project()
        self.__analyze_final()
        self.__save_symbol_map()
        self.bin_data = bytearray(open(self.project.TemporaryFilesFolder + self.project.Name + ".bin", "rb").read())
        print(f"{FYELLOW}Begin Patching...")
        self.__apply_gecko()
        self.__apply_hooks()
        self.__patch_osarena_low(self.dol, self.project.InjectionAddress + len(self.bin_data))
        with open(self.project.OutputDolFile, "wb") as f:
            self.dol.save(f)
        self.build_time = time() - build_start_time
        print(f"\n{FLGREEN}🎊 BUILD COMPLETE 🎊\n" f'Saved .dol to {FLCYAN}"{self.project.OutputDolFile}"{FLGREEN}!')
        if self.project.CleanUpTemporaryFiles:
            print(f"{FCYAN}Cleaning up temporary files\n")
            delete_dir(self.project.TemporaryFilesFolder)
        self.__print_extras()

    def __print_extras(self):
        with open(self.project.OutputDolFile, "rb") as f:
            md5 = hashlib.file_digest(f, "md5").hexdigest()
            sha_256 = hashlib.file_digest(f, "sha256").hexdigest()
            sha_512 = hashlib.file_digest(f, "sha512").hexdigest()
            print(f"{FLGREEN}MD5: {FLCYAN}{md5}\n{FLGREEN}SHA-256: {FLCYAN}{sha_256}\n{FLGREEN}SHA-512: {FLCYAN}{sha_512}")

        symbols = list[Symbol]()
        for symbol in self.symbols.values():
            symbols.append(symbol)
        symbols = list(set(symbols))
        symbols.sort(key=lambda x: x.size, reverse=True)
        symbols = symbols[:10]
        print(f"\nTop biggest symbols:")
        for symbol in symbols:
            print(f'{FLGREEN}{symbol}{FLCYAN} in "{FLYELLOW}{symbol.source_file}{FLCYAN}" {FLMAGENTA}{symbol.size}{FLGREEN} bytes')

        print(f"\n{FLCYAN}Compilation Time: {FLMAGENTA}{self.compile_time:.2f} {FLCYAN}seconds")
        print(f"{FLCYAN}Build Time {FLMAGENTA}{self.build_time:.2f} {FLCYAN}seconds")

    def __get_source_files(self):
        for folder in self.project.SourceFolders:
            for file in Path(folder).glob("**/*.*"):
                ext = file.suffix
                file = file.as_posix()

                if file in self.project.IgnoredSourceFiles:
                    continue
                match (ext):
                    case ".c":
                        self.c_files.append(file)
                    case ".cpp":
                        self.cpp_files.append(file)
                    case ".s":
                        self.asm_files.append(file)

    def __compile(self):
        with ProcessPoolExecutor() as executor:
            tasks = []
            for source in self.c_files + self.cpp_files:
                outpath = self.project.TemporaryFilesFolder + source.split("/")[-1] + ".o"
                self.object_files.append(outpath)
                task = executor.submit(self.compile, source, outpath, source.endswith("cpp"))
                print(f"{COMPILING} {source}")
                tasks.append(task)

            halt_compilation = False
            uncompiled_sources = []
            for task in as_completed(tasks):
                exitcode, source, out, err = task.result()
                if exitcode:
                    halt_compilation = True
                    uncompiled_sources.append(source)
                    print(f'\n{ERROR} failed to compile:{FLYELLOW}\n{err}")')
                else:
                    print(f'{SUCCESS} "{source}"{FCYAN}{out}')
                    self.__find_undefined_cpp_symbols(self.project.TemporaryFilesFolder + source.split("/")[-1] + ".o")
            if halt_compilation:
                sourceliststr = ""
                for source in uncompiled_sources:
                    sourceliststr += source + "\n"
                print(f"{FLRED}Build process halted. Please fix code errors for the following files:\n{FLCYAN}" + sourceliststr)
                sys.exit(1)

    def compile(self, input: str, output: str, is_cpp_file: bool = False) -> tuple[int, str, str, str]:
        args = []
        if is_cpp_file:
            args = [self.user_env.DevKitPPCBinFolder + GPP, "-c"] + self.project.GPPArgs
        else:
            args = [self.user_env.DevKitPPCBinFolder + GCC, "-c"] + self.project.GCCArgs
        args += self.project.CommonArgs
        for path in self.project.IncludeFolders:
            args.append("-I" + path)
        args.extend([input, "-o", output, "-fdiagnostics-color=always"])

        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        return process.returncode, input, out.decode(), err.decode()

    def __find_undefined_cpp_symbols(self, object_file: str):
        nm_file = self.dump_nm(object_file)
        print(f"{FYELLOW}Analyzing NM Output -> {FLCYAN + nm_file}...")
        source_file = object_file.replace(self.project.TemporaryFilesFolder, "").rsplit(".", 1)[0]
        with open(nm_file, "r") as f:
            for line in f.readlines():
                if line.startswith(("0", "8")):
                    line = line[8:]
                line = line.strip()
                if line == "d":  # not sure why a single 'd' gets written on a line to the nm on occasion.
                    continue
                (type, symbol_name) = line.split(" ")
                symbol = self.symbols[symbol_name]
                symbol.name = symbol_name
                if symbol_name.startswith("_Z"):
                    symbol.demangled_name = self.demangle(symbol_name)
                    if "C1" in symbol_name:  # Because Itanium ABI likes emitting two constructors we need to differentiate them
                        symbol.is_complete_constructor = True
                    elif "C2" in symbol_name:
                        symbol.is_base_constructor = True
                    self.symbols[symbol.demangled_name] = symbol
                else:
                    symbol.is_c_linkage = True
                    symbol.demangled_name = symbol_name
                if type in ["u", "U", "b"]:
                    continue
                if type == "T":
                    symbol.is_function = True
                elif type == "v":
                    symbol.is_weak = True
                elif type == "B":
                    symbol.is_bss = True
                elif type == "d":
                    symbol.is_data = True
                elif type == "r":
                    symbol.is_rodata = True
                elif type == "a":
                    symbol.is_manually_defined = True
                symbol.is_undefined = False
                if not symbol.source_file:
                    symbol.source_file = source_file
                else:  # should implement the source object/static lib better
                    symbol.library_file = source_file

    def __load_symbol_definitions(self):
        # Load symbols from a file. Supports recognizing demangled c++ symbols
        print(FYELLOW + "Loading manually defined symbols...")
        for file in Path(self.project.SymbolsFolder).glob("*.txt"):
            lines = open(file.as_posix(), "r").readlines()
            section = "." + file.stem
            for line in lines:
                line = line.rstrip().partition("//")[0]
                if line:
                    (name, address) = [x.strip() for x in line.split(" = ")]
                    if name in self.symbols:
                        symbol = self.symbols[name]
                        if symbol.source_file:  # skip this symbol because we are overriding it
                            continue
                        symbol.hex_address = address
                        symbol.address = int(address, 16)
                        symbol.is_manually_defined = True
                        symbol.section = section

    def __get_function_symbol(self, f, is_c_linkage: bool = False):
        """TODO: This function doesnt account for transforming typedefs/usings back to their primitive or original typename"""
        """Also doesn't account for namespaces that arent in the function signature"""
        while True:
            line = strip_comments(f.readline())
            if 'extern "C"' in line:
                is_c_linkage = True
            if not line:
                continue
            elif "(" in line:
                # line = re.sub(".*[\*>] ",'',line) # remove templates
                while line.startswith(("*", "&")):  # throw out trailing *'s and &'s
                    line = line[:1]
                line = re.findall("[A-Za-z0-9_:]*\(.*\)", line)[0]

                if is_c_linkage:
                    return re.sub("\(.*\)", "", line)  # c symbols have no params
                if "()" in line:
                    return line
                it = iter(re.findall('(extern "C"|[A-Za-z0-9_]+|[:]+|[<>\(\),*&])', line))
                chunks = []
                depth = 0
                for s in it:
                    if s in ["const", "volatile", "unsigned", "signed"]:
                        chunks.append(s + " ")  # add space
                        continue
                    if s.isalpha():
                        v = next(it)
                        if depth and v.isalpha():
                            chunks.append(s)
                            continue
                        else:
                            chunks.append(s)
                            s = v
                    match (s):
                        case "<":
                            depth += 1
                        case ">":
                            depth -= 1
                        case ",":
                            chunks.pop()
                            chunks.append(", ")
                            continue
                        case ")":
                            chunks.pop()
                    chunks.append(s)
                func = ""
                for s in chunks:
                    func += s
                    func = func.replace("const char", "char const")  # dumb
                return func

    def __process_pragmas(self):
        for file in self.cpp_files + self.c_files:
            if file in self.project.IgnoreHooks:
                continue
            is_c_linkage = False
            if file.endswith(".c"):
                is_c_linkage = True
            with open(file, "r", encoding="utf8") as f:
                while line := f.readline():
                    line = strip_comments(line)
                    if line.startswith("#pragma hook"):
                        branch_type, *addresses = line.removeprefix("#pragma hook").lstrip().split(" ")
                        function_symbol = self.__get_function_symbol(f, is_c_linkage)
                        match (branch_type):
                            case "bl":
                                for address in addresses:
                                    self.hook_branchlink(function_symbol, int(address, 16))
                            case "b":
                                for address in addresses:
                                    self.hook_branch(function_symbol, int(address, 16))
                            case _:
                                raise BaseException(
                                    f"\n{ERROR} Wrong branch type given in #pragma hook declaration! {FLBLUE}'{type}'{FLRED} is not supported!"
                                    + f"\nFound in {FLCYAN}{file}{FLRED}"
                                )
                    elif line.startswith("#pragma inject"):
                        inject_type, *addresses = line.removeprefix("#pragma inject").lstrip().split(" ")
                        match (inject_type):
                            case "pointer":
                                function_symbol = self.__get_function_symbol(f, is_c_linkage)
                                for address in addresses:
                                    self.hook_pointer(function_symbol, int(address, 16))
                            case "string":
                                for address in addresses:
                                    inject_string = ""
                                    self.hook_string(inject_string, int(address, 16))
                            case _:
                                raise BaseException(f"\n{ERROR}Arguments for #pragma inject are incorrect!" + f"\nFound in {FLCYAN}{file}{FLRED}")

    def __analyze_final(self):
        print(f"{FYELLOW}Dumping objdump...{FCYAN}")
        self.dump_objdump(self.project_objfile, "-tSr", "-C")
        self.__find_undefined_cpp_symbols(self.project_objfile)
        self.__analyze_readelf(self.dump_readelf(self.project_objfile, "-a", "--wide", "--debug-dump"))

    def __generate_linkerscript(self):
        linkerscript_file = self.project.TemporaryFilesFolder + self.project.Name + "_linkerscript.ld"
        with open(linkerscript_file, "w") as f:

            def write_section(section: str):
                symbols = [x for x in self.symbols.values() if x.section == section]
                if symbols == []:
                    return
                f.write(f"\t{section} ALIGN(0x20):\n\t{{\n")
                for symbol in symbols:
                    if symbol.is_manually_defined and not symbol.is_written_to_ld:
                        if not symbol.is_complete_constructor and symbol.is_base_constructor:
                            constructor_symbol_name = symbol.name.replace("C2", "C1")
                            f.write(f"\t\t{constructor_symbol_name} = {symbol.hex_address};\n")
                        f.write(f"\t\t{symbol.name} = {symbol.hex_address};\n")
                        symbol.is_written_to_ld = True
                f.write("\t}\n\n")

            if self.project.EntryFunction:
                f.write("ENTRY(" + self.project.EntryFunction + ");\n")
            if self.static_libs:
                for path in self.library_folders:
                    f.write(f'SEARCH_DIR("{path}");\n')
                group = "GROUP("
                for lib in self.static_libs:
                    group += f'"{lib}",\n\t'
                group = group[:-3]
                group += ");\n"
                f.write(group)

            f.write("SECTIONS\n{\n")
            write_section(".init")
            write_section(".text")
            write_section(".rodata")
            write_section(".data")
            write_section(".bss")
            write_section(".sdata")
            write_section(".sbss")
            write_section(".sdata2")
            write_section(".sbss2")

            f.write("\t/DISCARD/ :\n\t{\n")
            for section in self.project.DiscardSections:
                f.write(f"\t\t*({section}*);\n")
            f.write("\n")
            for lib in self.project.DiscardLibraryObjects:
                f.write(f"\t\t*{lib}(*);\n")
            f.write("\t}\n\n")

            f.write(f"\t. = 0x{self.project.InjectionAddress:4x};\n")
            f.write(
                "\t.sdata ALIGN(0x20):\n\t{\n\t\t*(.sdata*)\n\t}\n\n"
                "\t.sbss ALIGN(0x20):\n\t{\n\t\t*(.sbss*)\n\t}\n\n"
                "\t.sdata2 ALIGN(0x20):\n\t{\n\t\t*(.sdata2*)\n\t}\n\n"
                "\t.sbss2 ALIGN(0x20):\n\t{\n\t\t*(.sbss2*)\n\t}\n\n"
                "\t.rodata ALIGN(0x20):\n\t{\n\t\t*(.rodata*)\n\t}\n\n"
                "\t.data ALIGN(0x20):\n\t{\n\t\t*(.data*)\n\t}\n\n"
                "\t.bss ALIGN(0x20):\n\t{\n\t\t*(.bss*)\n\t}\n\n"
                "\t.text ALIGN(0x20):\n\t{\n\t\t*(.text*)\n\t}\n"
                "}"
            )
        self.project.LinkerScripts.append(linkerscript_file)

    def __link(self):
        print(f"{FLCYAN}Linking...{FYELLOW}")
        args = [self.user_env.DevKitPPCBinFolder + GPP]
        for arg in self.project.LDArgs:
            args.append("-Wl," + arg)
        for file in self.object_files:
            args.append(file)
        for linkerscript in self.project.LinkerScripts:
            args.append("-T" + linkerscript)
        args.extend(["-Wl,-Map", f"{self.project.TemporaryFilesFolder + self.project.Name}.map"])
        args.extend(["-o", self.project_objfile])
        if self.project.VerboseOutput:
            print(f"{FLMAGENTA}{args}")
        exit_code = subprocess.call(args, stdout=subprocess.PIPE)
        if exit_code:
            raise RuntimeError(f'{ERROR} failed to link object files"\n')
        else:
            print(f"{LINKED}{FLMAGENTA} -> {FLCYAN}{self.project.TemporaryFilesFolder + self.project.Name}.o")

    def __process_project(self):
        with open(self.project_objfile, "rb") as f:
            elf = ELFFile(f)
            with open(self.project.TemporaryFilesFolder + self.project.Name + ".bin", "wb") as data:
                for symbol in elf.iter_sections():
                    if symbol.header["sh_addr"] < self.project.InjectionAddress:
                        continue
                    # Filter out sections without SHF_ALLOC attribute
                    if symbol.header["sh_flags"] & 0x2:
                        data.seek(symbol.header["sh_addr"] - self.project.InjectionAddress)
                        data.write(symbol.data())

    def __analyze_readelf(self, path: str):
        section_map = {}
        print(f"{FYELLOW}Analyzing {FLCYAN+path}...")
        with open(path, "r") as f:
            while "  [ 0]" not in f.readline():
                pass
            id = 1
            while not (line := f.readline()).startswith("Key"):
                section_map[id] = line[7:].strip().split(" ")[0]
                id += 1
            while "Num" not in f.readline():
                pass
            f.readline()
            while (line := f.readline()) != "\n":
                (num, address, size, type, bind, vis, ndx, *name) = line.split()
                if size == "0":
                    continue
                if name[0] in self.symbols:
                    symbol = self.symbols[name[0]]
                    symbol.hex_address = "0x" + address
                    symbol.address = int(address, 16)
                    symbol.size = int(size)
                    symbol.library_file = self.project.Name + ".o"
                    if ndx == "ABS":
                        continue
                    symbol.section = section_map[int(ndx)]

    def __apply_hooks(self):
        for hook in self.hooks:
            hook.resolve(self.symbols)
            hook.apply_dol(self.dol)
            print(hook.dump_info())
        bad_symbols = list[str]()
        for hook in self.hooks:
            if not hook.good and hook.symbol_name not in bad_symbols:
                bad_symbols.append(hook.symbol_name)
        if bad_symbols:
            badlist = "\n"
            for name in bad_symbols:
                badlist += f'{FLYELLOW}{name}{FLWHITE} found in {FLCYAN}"{self.symbols[name].source_file}"\n'
            raise RuntimeError(
                f"{ERROR} C++Kit could not resolve hook addresses for the given symbols:\n{badlist}\n"
                f"{FLWHITE}Possible Reasons:{FLRED}\n"
                f"• If an entry function was specified to the linker it's possbile the function was optimized out by the compiler for being outside of the entry function's scope.\n"
                f'• Symbol definitions were missing in the {FLCYAN}"symbols"{FLRED} folder.\n\n\n'
            )
        if len(self.bin_data) > 0:
            new_section: Section
            if len(self.dol.textSections) <= DolFile.MaxTextSections:
                new_section = TextSection(self.project.InjectionAddress, self.bin_data)
            elif len(self.dol.dataSections) <= DolFile.MaxDataSections:
                new_section = DataSection(self.project.InjectionAddress, self.bin_data)
            else:
                raise RuntimeError("DOL is full! Cannot allocate any new sections.")
            self.dol.append_section(new_section)
            self.__patch_osarena_low(self.dol, self.project.InjectionAddress + len(self.bin_data))

        with open(self.project.OutputDolFile, "wb") as f:
            self.dol.save(f)

    def __apply_gecko(self):
        for gecko_txt in Path(self.project.GeckoFolder).glob("*.txt*"):
            if gecko_txt.as_posix() in self.project.IgnoredGeckoFiles:
                continue
            for child in GeckoCodeTable.from_text(open(gecko_txt, "r").read()):
                self.gecko_table.add_child(child)
        while (len(self.bin_data) % 4) != 0:
            self.bin_data += b"\x00"
        print(f"\n{FGREEN}[{FLGREEN}Gecko Codes{FGREEN}]")
        for gecko_code in self.gecko_table:
            status = f"{FLGREEN}ENABLED {FLBLUE}" if gecko_code.is_enabled() else f"{FLRED}DISABLED{FLYELLOW}"
            if gecko_code.is_enabled() == True:
                for gecko_command in gecko_code:
                    if gecko_command.codetype not in SupportedGeckoCodetypes:
                        status = "OMITTED"
            print("{:12s} ${}".format(status, gecko_code.name))
            if status == "OMITTED":
                print(f"{FLRED}Includes unsupported codetypes:")
                for gecko_command in gecko_code:
                    if gecko_command.codetype not in SupportedGeckoCodetypes:
                        print(gecko_command)
            vaddress = self.project.InjectionAddress + len(self.bin_data)
            gecko_data = bytearray()
            gecko_meta = []

            for gecko_command in gecko_code:
                if gecko_command.codetype == GeckoCommand.Type.ASM_INSERT or gecko_command.codetype == GeckoCommand.Type.ASM_INSERT_XOR:
                    if status == "UNUSED" or status == "OMITTED":
                        gecko_meta.append((0, len(gecko_command.value), status, gecko_command))
                    else:
                        self.dol.seek(gecko_command._address | 0x80000000)
                        write_branch(self.dol, vaddress + len(gecko_data))
                        gecko_meta.append(
                            (
                                vaddress + len(gecko_data),
                                len(gecko_command.value),
                                status,
                                gecko_command,
                            )
                        )
                        gecko_data += gecko_command.value[:-4]
                        gecko_data += assemble_branch(
                            vaddress + len(gecko_data),
                            gecko_command._address + 4 | 0x80000000,
                        )
            self.bin_data += gecko_data
            if gecko_meta:
                self.gecko_meta.append((vaddress, len(gecko_data), status, gecko_code, gecko_meta))
        print("\n")
        self.gecko_table.apply(self.dol)

    def __save_symbol_map(self):
        if not self.project.InputSymbolMap:
            print(f"{FLYELLOW}No input symbol map. Skipping.")
            return
        if not self.project.SymbolMapOutputPaths:
            print(f"{FLYELLOW}No paths found for symbol map output. Skipping.")
            return
        print(f"{FLCYAN}Copying symbols to map...")
        with open(self.project_objfile, "rb") as f:
            elf = ELFFile(f)
            index_to_name = {}
            index = 0
            for section in elf.iter_sections():
                index_to_name[index] = section.name
                index += 1
            symtab: SymbolTableSection = elf.get_section_by_name(".symtab")
            section_symbols = defaultdict(list)
            # Filter through the symbol table so that we only append symbols that use physical memory
            for symbol in symtab.iter_symbols():
                symbol_data = {}
                symbol_data["bind"], symbol_data["type"] = symbol.entry["st_info"].values()
                if symbol_data["type"] in ["STT_NOTYPE", "STT_FILE"]:
                    continue
                if symbol.entry["st_value"] < self.project.InjectionAddress:
                    continue
                symbol_data["address"] = symbol.entry["st_value"]
                symbol_data["size"] = symbol.entry["st_size"]
                if symbol_data["size"] == 0:
                    continue
                symbol_data["name"] = symbol.name

                symbol_data["section_index"] = symbol.entry["st_shndx"]
                if symbol_data["section_index"] in ["SHN_ABS", "SHN_UNDEF"]:
                    continue
                symbol_data["section"] = index_to_name[symbol.entry["st_shndx"]]
                if self.project.VerboseOutput:
                    print(
                        f'{FLGREEN + symbol_data["name"]} {FLMAGENTA}@ {hex(symbol_data["address"])} {FLCYAN}({index_to_name[symbol_data["section_index"]]}) {FLGREEN}Size: {str(symbol_data["size"])} bytes {FLYELLOW +symbol_data["bind"]}, {symbol_data["type"]}',
                        end=" ",
                    )
                    print(f"{FLGREEN}Added")
                section_symbols[symbol_data["section"]].append(symbol_data)
            with open(self.project.InputSymbolMap, "r+") as f:
                contents = f.readlines()
                insert_index = {}
                section = ""
                for line_index, line in enumerate(contents):
                    if "section layout" in line:
                        section = line.split(" ")[0]
                    if line == "\n":
                        insert_index[section] = line_index
                insert_offset = 0
                for section in insert_index:
                    if section in section_symbols.keys():
                        for symbol in section_symbols[section]:
                            insert_str = f'  {symbol["address"] - self.project.InjectionAddress:08X} {symbol["size"]:06X} {symbol["address"]:08X}  4 '
                            if symbol["name"] in self.symbols:
                                symbol = self.symbols[symbol["name"]]
                                insert_str += f"{symbol.demangled_name}\t {symbol.source_file} {symbol.library_file}\n"
                            contents.insert(insert_index[section] + insert_offset, insert_str)
                            insert_offset += 1
                for path in self.project.SymbolMapOutputPaths:
                    open(path, "w").writelines(contents)

    @cache
    def demangle(self, string: str):
        process = subprocess.Popen([self.user_env.DevKitPPCBinFolder + CPPFLIT, string], stdout=subprocess.PIPE)
        demangled = re.sub("\r\n", "", process.stdout.readline().decode("ascii"))
        if self.project.VerboseOutput:
            print(f" 🧼 {FBLUE+ string + FLMAGENTA} -> {FLGREEN + demangled}")
        return demangled

    def hook_branch(self, symbol: str, *addresses: int):
        """Create branch instruction(s) from the given symbol_name's absolute address to
        the address(es) given."""
        for address in addresses:
            self.hooks.append(BranchHook(address, symbol))

    def hook_branchlink(self, symbol: str, *addresses: int):
        """Create branchlink instruction(s) from the given symbol_name's absolute address to
        the address(es) given."""
        for address in addresses:
            self.hooks.append(BranchHook(address, symbol, lk_bit=True))

    def hook_pointer(self, symbol: str, *addresses: int):
        """Write the given symbol's absolute address to the location of the address(es) given."""
        for address in addresses:
            self.hooks.append(PointerHook(address, symbol))

    def hook_string(self, string, address, encoding="ascii", max_strlen=None):
        self.hooks.append(StringHook(address, string, encoding, max_strlen))

    def hook_file(self, address, filepath, start=0, end=None, max_size=None):
        self.hooks.append(FileHook(address, filepath, start, end, max_size))

    def hook_immediate16(self, address, symbol_name: str, modifier):
        self.hooks.append(Immediate16Hook(address, symbol_name, modifier))

    def hook_immediate12(self, address, w, i, symbol_name: str, modifier):
        self.hooks.append(Immediate12Hook(address, w, i, symbol_name, modifier))

    def __patch_osarena_low(self, dol: DolFile, rom_end: int):
        stack_size = 0x10000
        db_stack_size = 0x2000

        # Stacks are 8 byte aligned
        stack_addr = (rom_end + stack_size + 7 + 0x100) & 0xFFFFFFF8
        stack_end = stack_addr - stack_size
        db_stack_addr = (stack_addr + db_stack_size + 7 + 0x100) & 0xFFFFFFF8
        db_stack_end = db_stack_addr - db_stack_size

        # OSArena is 32 byte aligned
        osarena_lo = (stack_addr + 31) & 0xFFFFFFE0
        db_osarena_lo = (db_stack_addr + 31) & 0xFFFFFFE0

        # In [__init_registers]...
        dol.seek(0x80005410)
        write_lis(dol, 1, sign_extend(stack_addr >> 16, 16))
        write_ori(dol, 1, 1, stack_addr & 0xFFFF)

        # It can be assumed that the db_stack_addr value is also set somewhere.
        # However, it does not seem to matter, as the DBStack is not allocated.

        # In [OSInit]...
        # OSSetArenaLo( db_osarena_lo );
        dol.seek(0x800EB36C)
        write_lis(dol, 3, sign_extend(db_osarena_lo >> 16, 16))
        write_ori(dol, 3, 3, db_osarena_lo & 0xFFFF)

        # In [OSInit]...
        # If ( BootInfo->0x0030 == 0 ) && ( *BI2DebugFlag < 2 )
        # OSSetArenaLo( _osarena_lo );
        dol.seek(0x800EB3A4)
        write_lis(dol, 3, sign_extend(osarena_lo >> 16, 16))
        write_ori(dol, 3, 3, osarena_lo & 0xFFFF)

        # In [__OSThreadInit]...
        # DefaultThread->0x304 = db_stack_end
        dol.seek(0x800F18BC)
        write_lis(dol, 3, sign_extend(db_stack_end >> 16, 16))
        write_ori(dol, 0, 3, db_stack_end & 0xFFFF)

        # In [__OSThreadInit]...
        # DefaultThread->0x308 = _stack_end
        dol.seek(0x800F18C4)
        write_lis(dol, 3, sign_extend(stack_end >> 16, 16))
        dol.seek(0x800F18CC)
        write_ori(dol, 0, 3, stack_end & 0xFFFF)

        size = rom_end - self.project.InjectionAddress
        print(
            f"{FLCYAN}✨What's new:\n"
            f"{FLBLUE}Injected Binary Size: {FYELLOW}0x{FLYELLOW}{size:x}{FLGREEN} Bytes or {FLYELLOW}~{size/1024:.2f}{FLGREEN} KiBs\n"
            f"{FLBLUE}Injection Address @ {HEX}{self.project.InjectionAddress:x}\n"
            f"{FLBLUE}New ROM End @ {HEX}{rom_end:x}\n"
            f"{FLBLUE}Stack Moved To: {HEX}{stack_addr:x}\n"
            f"{FLBLUE}Stack End @ {HEX}{stack_end:x}\n"
            f"{FLBLUE}New OSArenaLo @ {HEX}{osarena_lo:x}\n"
            f"{FLBLUE}Debug Stack Moved To: {HEX}{db_stack_addr:x}\n"
            f"{FLBLUE}Debug Stack End @ {HEX}{db_stack_end:x}\n"
            f"{FLBLUE}New Debug OSArenaLo @ {HEX}{db_osarena_lo:x}"
        )
