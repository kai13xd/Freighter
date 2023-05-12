import hashlib
import re
import subprocess
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import cache
from glob import glob as _glob
from os import makedirs, remove, removedirs
from pathlib import Path
from time import time
from typing import Iterator

from dolreader.dol import DolFile
from dolreader.section import DataSection, Section, TextSection
from elftools.elf.elffile import ELFFile, SymbolTableSection
from geckolibs.gct import GeckoCodeTable, GeckoCommand
from geckolibs.geckocode import AsmInsert, AsmInsertXOR

from .config import FreighterConfig, UserEnvironment, file_exists
from .constants import *
from .exceptions import FreighterException
from .filelist import FileList, ObjectFile, SourceFile, Symbol
from .hooks import *


def glob(query: str, recursive: bool = False):
    globbed = _glob(query, recursive=recursive)
    result = list[str]()
    for path in globbed:
        result.append(path.replace("\\", "/"))
    return result


def strip_comments(line: str):
    return line.split("//")[0].strip()


def _get_function_symbol(lines: Iterator[tuple[int, str]], is_c_linkage: bool = False) -> tuple[int, Iterator[tuple[int, str]], str]:
    """TODO: This function doesnt account for transforming typedefs/usings back to their primitive or original typename"""
    """Also doesn't account for namespaces that arent in the function signature"""
    while True:
        line_number, line = next(lines)
        line = strip_comments(line)
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
                # c symbols have no params
                return line_number, lines, re.sub("\(.*\)", "", line)
            if "()" in line:
                return line_number, lines, line
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
            return line_number, lines, func


class Project:
    def __init__(self):
        # Instance variables
        self.project = FreighterConfig.project  # Allows multiprocessing processes to have context
        self.bin_data: bytearray
        self.library_folders: str
        self.symbols = defaultdict(Symbol)
        self.gecko_meta = []
        self.source_files = list[SourceFile]()
        # self.asm_files = list[SourceFile]()
        self.object_files = list[ObjectFile]()
        self.static_libs = list[str]()
        self.hooks = list[Hook]()
        self.compile_time = 0
        self.demangler_process = None
        if not self.project.InjectionAddress:
            self.project.InjectionAddress = self.dol.lastSection.address + self.dol.lastSection.size
            print(f"{WHITE}Base address auto-set from end of Read-Only Memory: {INFO_COLOR}{self.project.InjectionAddress:x}\n{WHITE}Do not rely on this feature if your DOL uses .sbss2\n")

        if self.project.InjectionAddress % 32:
            print("Warning! DOL sections must be 32-byte aligned for OSResetSystem to work properly!\n")
        if self.project.SDA and self.project.SDA2:
            self.project.CompilerArgs += ["-msdata=sysv"]
            self.project.LDArgs += [
                f"--defsym=_SDA_BASE_={hex(self.project.SDA)}",
                f"--defsym=_SDA2_BASE_={hex(self.project.SDA2)}",
            ]
        if self.project.InputSymbolMap:
            self.project.OutputSymbolMapPaths.append(f"{UserEnvironment.DolphinMaps}{self.project.GameID}.map")
        if self.project.StringHooks:
            for address, string in self.project.StringHooks.items():
                self.hooks.append(StringHook(address, string))

        self.final_object_file = ObjectFile(f"{self.project.TemporaryFilesFolder}{self.project.ProjectName}.o")
        FileList.add(self.final_object_file)
        self.gecko_table = GeckoCodeTable(self.project.GameID, self.project.ProjectName)
        self.dol = DolFile(open(self.project.InputDolFile, "rb"))

    def build(self) -> None:
        build_start_time = time()
        makedirs(self.project.TemporaryFilesFolder, exist_ok=True)
        self.__get_source_files()
        self.__process_pragmas()

        compile_list = list[SourceFile]()
        for source_file in self.source_files:
            # populate the object_file list
            self.object_files.append(source_file.object_file)
            if source_file.needs_recompile():
                compile_list.append(source_file)

        # Only compile if we have sourcefiles that need to be compiled
        if compile_list:
            compile_start_time = time()
            self.__compile(compile_list)
            self.compile_time = time() - compile_start_time

            for object_file in self.object_files:
                if object_file.is_hash_same():
                    print(f"{object_file} is not modified!")
                    self.symbols.update(object_file.symbols)
                else:
                    self.__find_undefined_symbols(object_file)
        else:
            for object_file in self.object_files:
                self.symbols.update(object_file.symbols)
            self.symbols.update(self.final_object_file.symbols)

        self.__load_symbol_definitions()
        self.__generate_linkerscript()
        self.__link()
        self.__process_project()
        self.__analyze_final()
        self.__save_symbol_map()
        self.bin_data = bytearray(open(self.project.TemporaryFilesFolder + self.project.ProjectName + ".bin", "rb").read())
        print(f"{ORANGE}Begin Patching...")
        self.__apply_gecko()
        self.__apply_hooks()
        self.__patch_osarena_low(self.dol, self.project.InjectionAddress + len(self.bin_data))
        with open(self.project.OutputDolFile, "wb") as f:
            self.dol.save(f)
        self.build_time = time() - build_start_time
        print(f'\n{GREEN}🎊 BUILD COMPLETE 🎊\nSaved .dol to {INFO_COLOR}"{self.project.OutputDolFile}"{GREEN}!')

        self.__print_extras()
        self.final_object_file.calculate_hash()
        FileList.save_state()

    def __print_extras(self):
        with open(self.project.OutputDolFile, "rb") as f:
            md5 = hashlib.file_digest(f, "md5").hexdigest()
            sha_256 = hashlib.file_digest(f, "sha256").hexdigest()
            sha_512 = hashlib.file_digest(f, "sha512").hexdigest()
            print(f"{GREEN}MD5: {INFO_COLOR}{md5}\n{GREEN}SHA-256: {INFO_COLOR}{sha_256}\n{GREEN}SHA-512: {INFO_COLOR}{sha_512}")

        symbols = list[Symbol]()
        for symbol in self.symbols.values():
            symbols.append(symbol)
        symbols = list(set(symbols))
        symbols.sort(key=lambda x: x.size, reverse=True)
        symbols = symbols[:10]
        print(f"\nTop biggest symbols:")
        for symbol in symbols:
            print(f'{GREEN}{symbol}{INFO_COLOR} in "{ORANGE}{symbol.source_file}{INFO_COLOR}" {PURPLE}{symbol.size}{GREEN} bytes')

        print(f"\n{INFO_COLOR}Compilation Time: {PURPLE}{self.compile_time:.2f} {INFO_COLOR}seconds")
        print(f"{INFO_COLOR}Build Time {PURPLE}{self.build_time:.2f} {INFO_COLOR}seconds")

    def dump_objdump(self, objectfile_path: ObjectFile, *args: str, outpath: str = "") -> str:
        """Dumps the output from DevKitPPC's powerpc-eabi-objdump.exe to a .txt file"""
        args = (UserEnvironment.OBJDUMP, objectfile_path.relative_path) + args
        if not outpath:
            outpath = self.project.TemporaryFilesFolder + objectfile_path.relative_path.split("/")[-1] + ".s"
        with open(outpath, "w") as f:
            subprocess.call(args, stdout=f)
        return outpath

    def dump_nm(self, object_path: str, *args: str, outpath: str = "") -> str:
        """Dumps the output from DevKitPPC's powerpc-eabi-nm.exe to a .txt file"""
        args = (UserEnvironment.NM, object_path) + args
        if not outpath:
            outpath = self.project.TemporaryFilesFolder + object_path.split("/")[-1].rstrip(".o") + ".nm"
        with open(outpath, "w") as f:
            subprocess.call(args, stdout=f)
        return outpath

    def dump_readelf(self, object_path: ObjectFile, *args: str, outpath: str = "") -> str:
        """Dumps the output from DevKitPPC's powerpc-eabi-readelf.exe to a .txt file"""
        args = (UserEnvironment.READELF, object_path.relative_path) + args
        if not outpath:
            outpath = self.project.TemporaryFilesFolder + object_path.relative_path.split("/")[-1] + ".readelf"
        with open(outpath, "w") as f:
            subprocess.call(args, stdout=f)
        return outpath

    def __get_source_files(self):
        for folder in self.project.SourceFolders:
            for file in glob(f"{folder}/**/**.c", recursive=True) + glob(f"{folder}/**/**.cpp", recursive=True):
                if file in self.project.IgnoredSourceFiles:
                    continue
                self.source_files.append(SourceFile(Path(file)))

    def __compile(self, compile_list: list[SourceFile]):
        with ProcessPoolExecutor() as executor:
            tasks = []
            for source_file in compile_list:
                task = executor.submit(self.compile, source_file, source_file.object_file)
                print(f"{COMPILING} {source_file}")
                tasks.append(task)

            halt_compilation = False
            uncompiled_sources = []
            for task in as_completed(tasks):
                exitcode, source_file, out, err = task.result()
                if exitcode:
                    halt_compilation = True
                    uncompiled_sources.append(source_file)
                    print(f'\n{ERROR} failed to compile:{INFO_COLOR}\n{err}")')
                else:
                    print(f'{SUCCESS} "{source_file}"{INFO_COLOR}{out}')
                    source_file.object_file.set_dirty()

            if halt_compilation:
                source_file_error = ""
                for source_file in uncompiled_sources:
                    source_file_error += source_file.relative_path + "\n"
                raise Exception(f"{WARN_COLOR}Build process halted. Please fix code errors for the following files:\n{INFO_COLOR}" + source_file_error)

    def compile(self, source_file: SourceFile, output: ObjectFile) -> tuple[int, SourceFile, str, str]:
        args = []
        if source_file.extension == ".cpp":
            args = [UserEnvironment.GPP, "-c"] + self.project.GPPArgs
        else:
            args = [UserEnvironment.GCC, "-c"] + self.project.GCCArgs
        args += self.project.CompilerArgs
        for path in self.project.IncludeFolders:
            args.append("-I" + path)
        args.extend([source_file.relative_path, "-o", output.relative_path, "-fdiagnostics-color=always"])

        process = subprocess.Popen(args,shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        return process.returncode, source_file, out.decode(), err.decode()

    def __find_undefined_symbols(self, object_file: ObjectFile):
        nm_file = self.dump_nm(object_file.relative_path)
        print(f"{ORANGE}Analyzing NM Output -> {INFO_COLOR}{nm_file}")
        with open(nm_file, "r") as f:
            for line in f:
                type, symbol_name = line[8:].strip().split(" ")
                symbol = self.symbols[symbol_name]
                symbol.name = symbol_name
                if symbol_name.startswith("_Z"):
                    symbol.demangled_name = self.demangle(symbol_name)
                    if "C1" in symbol_name:  # Because Itanium ABI likes emitting two constructors we need to differentiate them
                        symbol.is_complete_constructor = True
                    elif "C2" in symbol_name:
                        symbol.is_base_constructor = True
                    self.symbols[symbol.demangled_name] = symbol
                    object_file.add_symbol(symbol)
                else:
                    symbol.is_c_linkage = True
                    symbol.demangled_name = symbol_name
                    object_file.add_symbol(symbol)
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
                    symbol.is_absolute = True
                symbol.is_undefined = False
                if not symbol.source_file:
                    if object_file.source_file_name == self.project.ProjectName:
                        symbol.source_file = ""  # Temporary workaround for symbols sourced from external libs
                    else:
                        symbol.source_file = object_file.source_file_name

    def __load_symbol_definitions(self):
        # Load symbols from a file. Supports recognizing demangled c++ symbols
        print(f"{ORANGE}Loading manually defined symbols...")
        for file in Path(self.project.SymbolsFolder).glob("*.txt"):
            with open(file.as_posix(), "r") as f:
                lines = f.readlines()

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
                        symbol.is_absolute = True
                        symbol.section = section

    def __process_pragmas(self):
        for source_file in self.source_files:
            if source_file in self.project.IgnoreHooks:
                continue
            is_c_linkage = False
            if source_file.extension == ".c":
                is_c_linkage = True

            with open(source_file, "r", encoding="utf8") as f:
                lines = enumerate(f.readlines())

            for line_number, line in lines:
                line = strip_comments(line)

                if not line.startswith("#p"):
                    continue

                line = line.removeprefix("#pragma ")
                if line.startswith("hook"):
                    branch_type, *addresses = line.removeprefix("hook ").split(" ")
                    line_number, lines, function_symbol = _get_function_symbol(lines, is_c_linkage)
                    match (branch_type):
                        case "bl":
                            for address in addresses:
                                self.hooks.append(BranchHook(address, function_symbol, True))
                        case "b":
                            for address in addresses:
                                self.hooks.append(BranchHook(address, function_symbol))
                        case _:
                            raise FreighterException(f"{branch_type} is not a valid supported branch type for #pragma hook!\n" + f"{line} Found in {INFO_COLOR}{source_file}{WARN_COLOR} on line number {line_number + 1}")
                elif line.startswith("inject"):
                    inject_type, *addresses = line.removeprefix("inject ").split(" ")
                    match (inject_type):
                        case "pointer":
                            line_number, lines, function_symbol = _get_function_symbol(lines, is_c_linkage)
                            for address in addresses:
                                self.hooks.append(PointerHook(address, function_symbol))
                        case "string":
                            for address in addresses:
                                inject_string = ""
                                self.hooks.append(StringHook(address, inject_string))
                        case _:
                            raise FreighterException(f"Arguments for {PURPLE}{line}{INFO_COLOR} are incorrect!\n" + f"{line} Found in {INFO_COLOR}{source_file}{WARN_COLOR} on line number {line_number + 1}")

    def __analyze_final(self):
        print(f"{ORANGE}Dumping objdump...{CYAN}")
        self.dump_objdump(self.final_object_file, "-tSr", "-C")
        self.__find_undefined_symbols(self.final_object_file)
        self.__analyze_readelf(self.dump_readelf(self.final_object_file, "-a", "--wide", "--debug-dump"))

    def __generate_linkerscript(self):
        written_symbols = set[Symbol]()  # Keep track of duplicates
        linkerscript_file = self.project.TemporaryFilesFolder + self.project.ProjectName + "_linkerscript.ld"
        with open(linkerscript_file, "w") as f:

            def write_section(section: str):
                symbols = [x for x in self.symbols.values() if x.section == section]
                if symbols == []:
                    return
                f.write(f"\t{section} ALIGN(0x20):\n\t{{\n")
                for symbol in symbols:
                    if symbol.is_absolute and symbol not in written_symbols:
                        if not symbol.is_complete_constructor and symbol.is_base_constructor:
                            constructor_symbol_name = symbol.name.replace("C2", "C1")
                            f.write(f"\t\t{constructor_symbol_name} = {symbol.hex_address};\n")
                        f.write(f"\t\t{symbol.name} = {symbol.hex_address};\n")
                        written_symbols.add(symbol)
                f.write("\t}\n\n")

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
        print(f"{INFO_COLOR}Linking...{ORANGE}")
        args = [UserEnvironment.GPP]
        for arg in self.project.LDArgs:
            args.append("-Wl," + arg)
        for file in self.object_files:
            args.append(file.relative_path)
        for linkerscript in self.project.LinkerScripts:
            args.append("-T" + linkerscript)
        args.extend(["-Wl,-Map", f"{self.project.TemporaryFilesFolder + self.project.ProjectName}.map"])
        args.extend(["-o", self.final_object_file.relative_path])
        if self.project.VerboseOutput:
            print(f"{PURPLE}{args}")
        exit_code = subprocess.call(args, stdout=subprocess.PIPE)
        if exit_code:
            raise RuntimeError(f'{ERROR} failed to link object files"\n')
        else:
            print(f"{LINKED}{PURPLE} -> {INFO_COLOR}{self.project.TemporaryFilesFolder + self.project.ProjectName}.o")

    def __process_project(self):
        with open(self.final_object_file, "rb") as f:
            elf = ELFFile(f)
            with open(self.project.TemporaryFilesFolder + self.project.ProjectName + ".bin", "wb") as data:
                for symbol in elf.iter_sections():
                    if symbol.header["sh_addr"] < self.project.InjectionAddress:
                        continue
                    # Filter out sections without SHF_ALLOC attribute
                    if symbol.header["sh_flags"] & 0x2:
                        data.seek(symbol.header["sh_addr"] - self.project.InjectionAddress)
                        data.write(symbol.data())

    def __analyze_readelf(self, path: str):
        section_map = {}
        print(f"{ORANGE}Analyzing {INFO_COLOR}{path}...")
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
                    symbol.library_file = self.project.ProjectName + ".o"
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
                badlist += f'{ORANGE}{name}{WHITE} found in {INFO_COLOR}"{self.symbols[name].source_file}"\n'
            raise FreighterException(
                f'{ERROR} Freighter could not resolve hook addresses for the given symbols:\n{badlist}\n{WHITE}Possible Reasons:{WARN_COLOR}\n• The cache Freighter uses for incremental builds is faulty and needs to be reset. Use -cleanup option to remove the cache.\n• If this is a C++ Symbol there may be a symbol definition missing from the {{INFO_COLOR}}"symbols"{{WARN_COLOR}} folder'
            )
        if len(self.bin_data) > 0:
            new_section: Section
            if len(self.dol.textSections) <= DolFile.MaxTextSections:
                new_section = TextSection(self.project.InjectionAddress, self.bin_data)
            elif len(self.dol.dataSections) <= DolFile.MaxDataSections:
                new_section = DataSection(self.project.InjectionAddress, self.bin_data)
            else:
                raise FreighterException("DOL is full! Cannot allocate any new sections.")
            self.dol.append_section(new_section)

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
        print(f"\n{GREEN}[{GREEN}Gecko Codes{GREEN}]")
        for gecko_code in self.gecko_table:
            status = f"{GREEN}ENABLED {INFO_COLOR}" if gecko_code.is_enabled() else f"{WARN_COLOR}DISABLED{ORANGE}"
            if gecko_code.is_enabled() == True:
                for gecko_command in gecko_code:
                    if gecko_command.codetype not in SupportedGeckoCodetypes:
                        status = "OMITTED"
            print("{:12s} ${}".format(status, gecko_code.name))
            if status == "OMITTED":
                print(f"{WARN_COLOR}Includes unsupported codetypes:")
                for gecko_command in gecko_code:
                    if gecko_command.codetype not in SupportedGeckoCodetypes:
                        print(gecko_command)
            vaddress = self.project.InjectionAddress + len(self.bin_data)
            gecko_data = bytearray()
            gecko_meta = []

            gecko_commands = [item for item in gecko_code if isinstance(item, AsmInsert) or isinstance(item, AsmInsertXOR)]

            for gecko_command in gecko_commands:
                if status == "UNUSED" or status == "OMITTED":
                    gecko_meta.append((0, len(gecko_command.value), status, gecko_command))
                else:
                    self.dol.seek(gecko_command._address | 0x80000000)
                    write_branch(self.dol, vaddress + len(gecko_data))
                    gecko_meta.append(
                        (
                            vaddress + len(gecko_data),
                            len(bytes(gecko_command.value)),
                            status,
                            gecko_command,
                        )
                    )
                    gecko_data += bytes(gecko_command.value)[:-4]
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
            print(f"{ORANGE}No input symbol map. Skipping.")
            return

        if not self.project.OutputSymbolMapPaths:
            print(f"{ORANGE}No paths found for symbol map output. Skipping.")
            return

        print(f"{INFO_COLOR}Copying symbols to map...")
        with open(self.final_object_file, "rb") as f:
            elf = ELFFile(f)
            index_to_name = {}
            index = 0
            for section in elf.iter_sections():
                index_to_name[index] = section.name
                index += 1

            section_symbols = defaultdict(list)
            symtab = elf.get_section_by_name(".symtab")
            if isinstance(symtab, SymbolTableSection):
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
                    # if self.config.VerboseOutput:
                    #     print(
                    #         f'{GREEN + symbol_data["name"]} {PURPLE}@ {hex(symbol_data["address"])} {INFO_COLOR}({index_to_name[symbol_data["section_index"]]}) {GREEN}Size: {str(symbol_data["size"])} bytes {ORANGE +symbol_data["bind"]}, {symbol_data["type"]}',
                    #         end=" ",
                    #     )
                    #     print(f"{GREEN}Added")
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
                for path in self.project.OutputSymbolMapPaths:
                    open(path, "w").writelines(contents)

    @cache
    def demangle(self, string: str) -> str:
        if not self.demangler_process:
            self.demangler_process = subprocess.Popen([UserEnvironment.CPPFLIT], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

        self.demangler_process.stdin.write(f"{string}\n".encode())
        self.demangler_process.stdin.flush()

        demangled = self.demangler_process.stdout.readline().decode().rstrip()
        if self.project.VerboseOutput:
            print(f" 🧼 {INFO_COLOR}{string}{PURPLE} -> {GREEN}{demangled}")

        return demangled

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
            f"{INFO_COLOR}✨What's new:\n{INFO_COLOR}Injected Binary Size: {HEX}{ORANGE}{size:x}{GREEN} Bytes or"
            f" {ORANGE}~{size/1024:.2f}{GREEN} KiBs\n{INFO_COLOR}Injection Address @"
            f" {HEX}{self.project.InjectionAddress:x}\n{INFO_COLOR}New ROM End @ {HEX}{rom_end:x}\n{INFO_COLOR}Stack"
            f" Moved To: {HEX}{stack_addr:x}\n{INFO_COLOR}Stack End @ {HEX}{stack_end:x}\n{INFO_COLOR}New OSArenaLo @"
            f" {HEX}{osarena_lo:x}\n{INFO_COLOR}Debug Stack Moved To: {HEX}{db_stack_addr:x}\n{INFO_COLOR}Debug Stack"
            f" End @ {HEX}{db_stack_end:x}\n{INFO_COLOR}New Debug OSArenaLo @ {HEX}{db_osarena_lo:x}"
        )
