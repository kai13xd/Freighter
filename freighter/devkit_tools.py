import re
import subprocess
from collections import defaultdict
from glob import glob
from concurrent.futures import ProcessPoolExecutor, as_completed
from os import makedirs, remove, removedirs
from pathlib import Path
from dolreader.dol import DolFile
from dolreader.section import DataSection, Section, TextSection
from elftools.elf.elffile import ELFFile, SymbolTableSection
from geckolibs.gct import GeckoCodeTable, GeckoCommand
import sys
from dataclasses import dataclass

from .config import *
from .constants import *
from .hooks import *


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


@dataclass
class Symbol:
    name = ""
    demangled_name = ""
    section = ""
    address = 0
    hex_address = ""
    size = 0
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


class Project:
    def __init__(self, project_toml_filepath: str, userenv_toml_filepath: str = ""):
        self.config = FreighterConfig(project_toml_filepath, userenv_toml_filepath)
        self.dol: DolFile
        self.bin_data: bytearray
        if self.config.project_profile.InputSymbolMap:
            assert_file_exists(self.config.project_profile.InputSymbolMap)
            self.config.project_profile.SymbolMapOutputPaths.append(
                self.config.user_env.DolphinDocumentsFolder + "Maps/" + self.config.project_profile.GameID + ".map"
            )

        self.library_folders = "/lib/"
        self.__get_source_folders()
        self.project_objfile = self.config.project_profile.BuildPath + self.config.project_profile.Name + ".o"
        self.c_files = list[str]()
        self.cpp_files = list[str]()
        self.asm_files = list[str]()
        self.object_files = list[str]()
        self.static_libs = list[str]()
        self.hooks = list[Hook]()

        self.gecko_table = GeckoCodeTable(self.config.project_profile.GameID, self.config.project_profile.Name)
        self.gecko_meta = []
        self.symbols = defaultdict(Symbol)
        self.osarena_patcher = None

    def __get_source_folders(self) -> None:
        if self.config.project_profile.AutoImport == False:
            return
        source_paths = ["source\\", "src\\", "code\\"]
        include_paths = ["include\\", "includes\\", "headers\\"]

        for folder in glob("*/", recursive=True):
            if folder in include_paths:
                print(f'{FLGREEN}Automatically added include folder: {FLCYAN}"{folder}"')
                self.config.project_profile.IncludeFolders.append(folder + "/")
            if folder in source_paths and folder not in self.config.project_profile.SourceFolders:
                print(f'{FLGREEN}Automatically added source folder: {FLCYAN}"{folder}"')
                self.config.project_profile.SourceFolders.append(folder.rstrip("//") + "/")

    def dump_objdump(self, objectfile_path: str, *args: str, outpath: str = ""):
        """Dumps the output from DevKitPPC's powerpc-eabi-objdump.exe to a .txt file"""
        args = (self.config.user_env.DevKitPPCBinFolder + OBJDUMP, objectfile_path) + args
        if not outpath:
            outpath = self.config.project_profile.TemporaryFilesFolder + objectfile_path.split("/")[-1] + ".s"
        with open(outpath, "w") as f:
            subprocess.call(args, stdout=f)
        return outpath

    def dump_nm(self, object_path: str, *args: str, outpath: str = ""):
        """Dumps the output from DevKitPPC's powerpc-eabi-nm.exe to a .txt file"""
        args = (self.config.user_env.DevKitPPCBinFolder + NM, object_path) + args
        if not outpath:
            outpath = self.config.project_profile.TemporaryFilesFolder + object_path.split("/")[-1].rstrip(".o") + ".nm"
        with open(outpath, "w") as f:
            subprocess.call(args, stdout=f)
        return outpath

    def dump_readelf(self, object_path: str, *args: str, outpath: str = ""):
        """Dumps the output from DevKitPPC's powerpc-eabi-readelf.exe to a .txt file"""
        args = (self.config.user_env.DevKitPPCBinFolder + READELF, object_path) + args
        if not outpath:
            outpath = self.config.project_profile.TemporaryFilesFolder + object_path.split("/")[-1] + ".readelf"
        with open(outpath, "w") as f:
            subprocess.call(args, stdout=f)
        return outpath

    def build(
        self,
    ):
        makedirs(self.config.project_profile.TemporaryFilesFolder, exist_ok=True)
        self.__get_source_files()
        if self.config.project_profile.SDA and self.config.project_profile.SDA2:
            self.config.project_profile.CommonArgs += ["-msdata=sysv"]
            self.config.project_profile.LDArgs += [f"--defsym=_SDA_BASE_={hex(self.config.project_profile.SDA)}"]
            self.config.project_profile.LDArgs += [f"--defsym=_SDA2_BASE_={hex(self.config.project_profile.SDA2)}"]
        self.__compile()
        for object_file in self.object_files:
            self.__find_undefined_cpp_symbols(object_file)
        self.__load_symbol_definitions()
        self.__generate_linkerscript()
        self.__link()
        self.__process_project()
        self.__analyze_final()
        self.__save_symbol_map()

        self.dol = DolFile(open(self.config.project_profile.InputDolFile, "rb"))
        if not self.config.project_profile.InjectionAddress:
            self.config.project_profile.InjectionAddress = self.dol.lastSection.address + self.dol.lastSection.size
            print(
                f"{FWHITE}Base address auto-set from ROM end: {FLBLUE}{self.config.project_profile.InjectionAddress:x}\n"
                f"{FWHITE}Do not rely on this feature if your DOL uses .sbss2\n"
            )
        if self.config.project_profile.InjectionAddress % 32:
            print("Warning!  DOL sections must be 32-byte aligned for OSResetSystem to work properly!\n")
        self.bin_data = bytearray(open(self.config.project_profile.TemporaryFilesFolder + self.config.project_profile.Name + ".bin", "rb").read())
        print(f"{FYELLOW}Begin Patching...")
        self.__apply_gecko()
        self.__apply_hooks()

        if self.config.project_profile.CleanUpTemporaryFiles:
            print(f"{FCYAN} Cleaning up temporary files\n")
            delete_dir(self.config.project_profile.TemporaryFilesFolder)
        print(f'\n{FLGREEN}🎊 BUILD COMPLETE 🎊\nSaved .dol to {FLCYAN}"{self.config.project_profile.InputDolFile}"{FLGREEN}!')

    def __get_source_files(self):
        """Adds all source files found the specified folder to the Project for complilation.
        Files within ignore list will be removed."""
        if self.config.project_profile.AutoImport == False:
            return
        for folder in self.config.project_profile.SourceFolders:
            for file in Path(folder).glob("*.*"):
                ext = file.suffix
                file = file.as_posix()

                if file in self.config.project_profile.IgnoredSourceFiles:
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
                outpath = self.config.project_profile.TemporaryFilesFolder + source.split("/")[-1] + ".o"
                self.object_files.append(outpath)
                self.__process_pragmas(source)
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
            if halt_compilation:
                sourceliststr = ""
                for source in uncompiled_sources:
                    sourceliststr += source + "\n"
                print(f"{FLRED}Build process halted. Please fix code errors for the following files:\n{FLCYAN}" + sourceliststr)
                sys.exit(0)

    def compile(self, input: str, output: str, is_cpp_file: bool = False) -> tuple[int, str, str, str]:
        args = []
        if is_cpp_file:
            args = [self.config.user_env.DevKitPPCBinFolder + GPP, "-c"] + self.config.project_profile.GPPArgs
        else:
            args = [self.config.user_env.DevKitPPCBinFolder + GCC, "-c"] + self.config.project_profile.GCCArgs
        args += self.config.project_profile.CommonArgs
        for path in self.config.project_profile.IncludeFolders:
            args.append("-I" + path)
        args.extend([input, "-o", output, "-fdiagnostics-color=always"])

        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        return process.returncode, input, out.decode(), err.decode()

    def __find_undefined_cpp_symbols(self, object_file: str):
        nm_file = self.dump_nm(object_file)
        print(f"{FYELLOW}Analyzing NM Output -> {FLCYAN + nm_file}...")
        source_file = object_file.replace(self.config.project_profile.TemporaryFilesFolder, "").rsplit(".", 2)[0]
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
                    self.symbols[symbol.demangled_name] = symbol
                else:
                    symbol.is_c_linkage = True
                    symbol.demangled_name = symbol_name
                if type in ["u","U","b"]:
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
        for file in Path(self.config.project_profile.SymbolsFolder).glob("*.txt"):
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

    def __get_function_symbol(self, line: str):
        """This func looks like booty should clean up later when i feel like it
        TODO: This function doesnt account for transforming typedefs/usings back to their primitive or original typename"""
        if 'extern "C"' in line:
            is_c_linkage = True
        else:
            is_c_linkage = False
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

    def __process_pragmas(self, file_path):
        c_linkage = False
        with open(file_path, "r", encoding="utf8") as f:
            while line := f.readline():
                if line.startswith("#pragma hook"):
                    branch_type, *addresses = line[13:].split(" ")
                    while True:  # skip comments and find the next function declaration
                        line = f.readline()
                        if not line:
                            continue
                        if line[2:] == "/":
                            continue
                        elif "(" in line:
                            break
                    func = self.__get_function_symbol(line)
                    match (branch_type):
                        case "bl":
                            for address in addresses:
                                self.hook_branchlink(func, int(address, 16))
                        case "b":
                            for address in addresses:
                                self.hook_branch(func, int(address, 16))
                        case _:
                            raise BaseException(f"\n{ERROR} Wrong branch type given in #pragma hook declaration! {FLBLUE}'{type}'{FLRED} is not supported!")
                elif line.startswith("#pragma write"):
                    address = line[14:].strip()
                    while True:  # skip comments and find the next function declaration
                        line = f.readline()
                        if not line:
                            continue
                        if line[2:] == "/":
                            continue
                        elif "(" in line:
                            break
                    func = self.__get_function_symbol(line)
                    self.hook_pointer(func, int(address, 16))

    def __analyze_final(self):
        print(f"{FYELLOW}Dumping objdump...{FCYAN}")
        self.dump_objdump(self.project_objfile, "-tSr", "-C")
        self.__find_undefined_cpp_symbols(self.project_objfile)
        self.__analyze_readelf(self.dump_readelf(self.project_objfile, "-a", "--wide", "--debug-dump"))

    def __generate_linkerscript(self):
        linkerscript_file = self.config.project_profile.TemporaryFilesFolder + self.config.project_profile.Name + "_linkerscript.ld"
        with open(linkerscript_file, "w") as f:

            def write_section(section: str):
                symbols = [x for x in self.symbols.values() if x.section == section]
                if symbols == []:
                    return
                f.write(f"\t{section} ALIGN(0x20):\n\t{{\n")
                for symbol in symbols:
                    if symbol.is_manually_defined and not symbol.is_written_to_ld:
                        f.write(f"\t\t{symbol.name} = {symbol.hex_address};\n")
                        symbol.is_written_to_ld = True
                f.write("\t}\n\n")

            if self.config.project_profile.EntryFunction:
                f.write("ENTRY(" + self.config.project_profile.EntryFunction + ");\n")
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
            f.write(f"\t. = 0x{self.config.project_profile.InjectionAddress:4x};")
            f.write(
                """    
    /DISCARD/ : 
    {
    *crtbegin.o(*);
    *crtend.o(*);
    *(.eh_frame*);
    *lib_a*(*);
    *iosupport.o(*);
    *handle_manager.o(*);
    *read.o(*);
    *write.o(*);
    *lseek.o(*);
    *close.o(*);
    *fstat.o(*);
    *del_op.o(*);
    *del_opv.o(*)
    *getpid.o(*);
    *kill.o(*);
    *sbrk.o(*);
    *isatty.o(*);
    *_exit.o(*);
    *flock.o(*);
    *syscall_support.o(*);
    *(.ctors* );
    *(.dtors* );
    *(.init* );
    *(.fini* );
    }
    .sdata  ALIGN(0x20):    { *(.sdata*) }
	.sbss   ALIGN(0x20):    { *(.sbss*) }
	.sdata2 ALIGN(0x20):    { *(.sdata2*) }
	.sbss2  ALIGN(0x20):    { *(.sbss2*) }
	.rodata ALIGN(0x20):    { *(.rodata*) }
    .data   ALIGN(0x20):    { *(.data*) }
	.bss    ALIGN(0x20):    { *(.bss*) }
    .text   ALIGN(0x20):    { *(.text*) }
     
}"""
            )
        self.config.project_profile.LinkerScripts.append(linkerscript_file)

    def __link(self):
        print(f"{FLCYAN}Linking...{FYELLOW}")
        args = [self.config.user_env.DevKitPPCBinFolder + GPP]
        for arg in self.config.project_profile.LDArgs:
            args.append("-Wl," + arg)
        for file in self.object_files:
            args.append(file)
        for linkerscript in self.config.project_profile.LinkerScripts:
            args.append("-T" + linkerscript)
        args.extend(["-Wl,-Map", f"{self.config.project_profile.TemporaryFilesFolder + self.config.project_profile.Name}.map"])
        args.extend(["-o", self.project_objfile])
        if self.config.project_profile.VerboseOutput:
            print(f"{FLMAGENTA}{args}")
        exit_code = subprocess.call(args)
        if exit_code:
            raise RuntimeError(f'{ERROR} failed to link object files"\n')
        else:
            print(f"{LINKED}{FLMAGENTA} -> {FLCYAN}{self.config.project_profile.TemporaryFilesFolder + self.config.project_profile.Name}.o")

    def __process_project(self):
        with open(self.project_objfile, "rb") as f:
            elf = ELFFile(f)
            with open(self.config.project_profile.TemporaryFilesFolder + self.config.project_profile.Name + ".bin", "wb") as data:
                for symbol in elf.iter_sections():
                    if symbol.header["sh_addr"] < self.config.project_profile.InjectionAddress:
                        continue
                    # Filter out sections without SHF_ALLOC attribute
                    if symbol.header["sh_flags"] & 0x2:
                        data.seek(symbol.header["sh_addr"] - self.config.project_profile.InjectionAddress)
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
                    symbol.library_file = self.config.project_profile.Name + ".o"
                    if ndx == "ABS":
                        continue
                    symbol.section = section_map[int(ndx)]

    def __apply_hooks(self):
        for hook in self.hooks:
            hook.resolve(self.symbols)
            hook.apply_dol(self.dol)
            if self.config.project_profile.VerboseOutput:
                print(hook.dump_info())
        print("\n")
        bad_symbols = list[str]()
        for hook in self.hooks:
            if hook.good == False and hook.symbol_name not in bad_symbols:
                bad_symbols.append(hook.symbol_name)
        if bad_symbols:
            badlist = "\n"
            for name in bad_symbols:
                badlist += f'{FLYELLOW}{name}{FLWHITE} found in {FLCYAN}"{self.symbols[name].source_file}"\n'
            raise RuntimeError(
                f"{ERROR} C++Kit could not resolve hook addresses for the given symbols:\n{badlist}\n"
                f"{FLWHITE}Reasons:{FLRED}\n"
                f"• The function was optimized out by the compiler for being out of the entry function's scope.\n"
                f'• Symbol definitions are missing from C++Kit in the {FLCYAN}"symbols"{FLRED} folder.\n\n\n'
            )
        if len(self.bin_data) > 0:
            new_section: Section
            if len(self.dol.textSections) <= DolFile.MaxTextSections:
                new_section = TextSection(self.config.project_profile.InjectionAddress, self.bin_data)
            elif len(self.dol.dataSections) <= DolFile.MaxDataSections:
                new_section = DataSection(self.config.project_profile.InjectionAddress, self.bin_data)
            else:
                raise RuntimeError("DOL is full! Cannot allocate any new sections.")
            self.dol.append_section(new_section)
            self.__patch_osarena_low(self.dol, self.config.project_profile.InjectionAddress + len(self.bin_data))

        with open(self.config.project_profile.OutputDolFile, "wb") as f:
            self.dol.save(f)

    def __apply_gecko(self):
        for gecko_txt in Path(self.config.project_profile.GeckoFolder).glob("*.txt*"):
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
            vaddress = self.config.project_profile.InjectionAddress + len(self.bin_data)
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
        if not self.config.project_profile.InputSymbolMap:
            print(f"{FLYELLOW}No input symbol map. Skipping.")
            return
        if not self.config.project_profile.SymbolMapOutputPaths:
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
                if symbol.entry["st_value"] < self.config.project_profile.InjectionAddress:
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
                if self.config.project_profile.VerboseOutput:
                    print(
                        f'{FLGREEN + symbol_data["name"]} {FLMAGENTA}@ {hex(symbol_data["address"])} {FLCYAN}({index_to_name[symbol_data["section_index"]]}) {FLGREEN}Size: {str(symbol_data["size"])} bytes {FLYELLOW +symbol_data["bind"]}, {symbol_data["type"]}',
                        end=" ",
                    )
                    print(f"{FLGREEN}Added")
                section_symbols[symbol_data["section"]].append(symbol_data)
            with open(self.config.project_profile.InputSymbolMap, "r+") as f:
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
                            insert_str = (
                                f'  {symbol["address"] - self.config.project_profile.InjectionAddress:08X} {symbol["size"]:06X} {symbol["address"]:08X}  4 '
                            )
                            if symbol["name"] in self.symbols:
                                symbol = self.symbols[symbol["name"]]
                                insert_str += f"{symbol.demangled_name}\t {symbol.section} {symbol.source_file} {symbol.library_file}\n"
                            contents.insert(insert_index[section] + insert_offset, insert_str)
                            insert_offset += 1
                for path in self.config.project_profile.SymbolMapOutputPaths:
                    open(path, "w").writelines(contents)

    def demangle(self, string: str):
        process = subprocess.Popen([self.config.user_env.DevKitPPCBinFolder + CPPFLIT, string], stdout=subprocess.PIPE)
        demangled = re.sub("\r\n", "", process.stdout.readline().decode("ascii"))
        if self.config.project_profile.VerboseOutput:
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

        if self.config.project_profile.VerboseOutput == True:
            size = rom_end - self.config.project_profile.InjectionAddress
            print(f"{FLCYAN}✨What's new:")
            print(f"{FLBLUE}Mod Size: {FYELLOW}0x{FLYELLOW}{size:x}{FLGREEN} Bytes or {FLYELLOW}~{size/1024:.2f}{FLGREEN} KiBs")
            print(f"{FLBLUE}Injected @: {HEX}{self.config.project_profile.InjectionAddress:x}")
            print(f"{FLBLUE}Mod End @: {HEX}{rom_end:x}\n")

            print(f"{FLBLUE}Stack Moved To: {HEX}{stack_addr:x}")
            print(f"{FLBLUE}Stack End @: {HEX}{stack_end:x}")
            print(f"{FLBLUE}New OSArenaLo: {HEX}{osarena_lo:x}\n")

            print(f"{FLBLUE}Debug Stack Moved to: {HEX}{db_stack_addr:x}")
            print(f"{FLBLUE}Debug Stack End @: {HEX}{db_stack_end:x}")
            print(f"{FLBLUE}New Debug OSArenaLo: {HEX}{db_osarena_lo:x}")
