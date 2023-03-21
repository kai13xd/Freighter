import re
import subprocess
from collections import defaultdict
from glob import glob
from concurrent.futures import ProcessPoolExecutor, as_completed
from os import listdir, makedirs, remove, removedirs
from pathlib import Path
from symtable import SymbolTable
from dolreader.dol import DolFile
from dolreader.section import DataSection, Section, TextSection
from elftools.elf.elffile import ELFFile, SymbolTableSection
from geckolibs.gct import GeckoCodeTable, GeckoCommand
from os.path import abspath
from .constants import *
from .hooks import *
import sys


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


def dump_objdump(objectfile_path: str, *args: str, outpath: str = ""):
    """Dumps the output from DevKitPPC's powerpc-eabi-objdump.exe to a .txt file"""
    args = (OBJDUMP, objectfile_path) + args
    if not outpath:
        outpath = TEMPDIR + objectfile_path.split("/")[-1] + ".s"
    with open(outpath, "w") as f:
        subprocess.call(args, stdout=f)
    return outpath


def dump_nm(object_path: str, *args: str, outpath: str = ""):
    """Dumps the output from DevKitPPC's powerpc-eabi-nm.exe to a .txt file"""
    args = (NM, object_path) + args
    if not outpath:
        outpath = TEMPDIR + object_path.split("/")[-1].rstrip(".o") + ".nm"
    with open(outpath, "w") as f:
        subprocess.call(args, stdout=f)
    return outpath


def dump_readelf(object_path: str, *args: str, outpath: str = ""):
    """Dumps the output from DevKitPPC's powerpc-eabi-readelf.exe to a .txt file"""
    args = (READELF, object_path) + args
    if not outpath:
        outpath = TEMPDIR + object_path.split("/")[-1] + ".readelf"
    with open(outpath, "w") as f:
        subprocess.call(args, stdout=f)
    return outpath


class Symbol:
    def __init__(self):
        self.name = ""
        self.demangled_name = ""
        self.section = ""
        self.address = 0
        self.hex_address = ""
        self.size = 0
        self.is_undefined = True
        self.is_weak = False
        self.is_function = False
        self.is_data = False
        self.is_bss = False
        self.is_rodata = False
        self.is_c_linkage = False
        self.is_manually_defined = False
        self.is_written_to_ld = False
        self.source_file = ""
        self.library_file = ""


class Project(object):
    def __init__(self, name: str, gameid: str, auto_import=True):
        self.gameid = gameid
        self.project_name = name
        self.inject_address = 0
        self.auto_import = auto_import
        self.verbose = False
        self.entry_function: str = ""
        self.build_dir = BUILDDIR
        self.temp_dir = TEMPDIR
        self.dol_inpath: str = ""
        self.dol_outpath: str = ""
        self.dol: DolFile
        self.bin_data: bytearray
        self.symbols_paths = list[str]()
        self.linkerscripts = list[str]()
        self.map_inpath: str = ""
        if DOLPHIN_MAP_DIR:
            self.symbol_map_outpaths = [DOLPHIN_MAP_DIR + gameid + ".map"]
        else:
            self.symbol_map_outpaths = [""]

        self.common_args = list[str]()
        self.gcc_args = list[str]()
        self.gpp_args = list[str]()
        self.project_objfile = self.temp_dir + self.project_name + ".o"
        self.ld_args = list[str]()

        self.include_folders = list[str]()
        self.source_folders = list[str]()
        self.library_folders = "/lib/"
        self.ignored_files = list[str]()
        self.__get_default_folders()

        self.c_files = list[str]()
        self.cpp_files = list[str]()
        self.asm_files = list[str]()
        self.object_files = list[str]()
        self.static_libs = list[str]()
        self.hooks = list[Hook]()

        self.gecko_table = GeckoCodeTable(gameid, name)
        self.gecko_meta = []
        self.symbols = defaultdict(Symbol)
        self.osarena_patcher = None

    def __get_default_folders(self) -> None:
        if self.auto_import == False:
            return
        source_paths = ["source", "src", "code"]
        include_paths = ["include", "includes", "headers"]

        for folder in glob("*", recursive=True):
            if folder in include_paths:
                print(f'{FLGREEN}Automatically added include folder: {FLCYAN}"{folder}"')
                self.include_folders.append(folder + "/")
            if folder in source_paths:
                print(f'{FLGREEN}Automatically added source folder: {FLCYAN}"{folder}"')
                self.source_folders.append(folder + "/")

    def build(
        self,
        dol_inpath: str,
        inject_address: int,
        dol_outpath: str,
        symbol_map_in_path: str = "",
        verbose: bool = False,
        clean_up: bool = False,
    ):
        self.dol_inpath = dol_inpath
        self.dol_outpath = dol_outpath
        self.inject_address = inject_address
        self.verbose = verbose

        if symbol_map_in_path:
            self.map_inpath = assert_file_exists(symbol_map_in_path)
        if not self.symbol_map_outpaths:
            print(f"{FYELLOW}[Warning] Output path to Dolphin's Maps folder was not found.\n{FWHITE}Use {FGREEN}add_map_output{FWHITE} method.")

        makedirs(self.temp_dir, exist_ok=True)
        self.__get_source_files()
        self.__compile()
        for object_file in self.object_files:
            self.__find_undefined_cpp_symbols(object_file)
        self.__load_symbol_definitions()
        self.__generate_linkerscript()
        self.__link()
        self.__process_project()
        self.__analyze_final()
        self.__save_symbol_map()

        self.dol = DolFile(open(dol_inpath, "rb"))
        if self.inject_address == None:
            self.inject_address = self.dol.lastSection.address + self.dol.lastSection.size
            print(
                f"{FWHITE}Base address auto-set from ROM end: {FLBLUE}{self.inject_address:x}\n"
                f"{FWHITE}Do not rely on this feature if your DOL uses .sbss2\n"
            )
        if self.inject_address % 32:
            print("Warning!  DOL sections must be 32-byte aligned for OSResetSystem to work properly!\n")
        self.bin_data = bytearray(open(self.temp_dir + self.project_name + ".bin", "rb").read())
        print(f"{FYELLOW}Begin Patching...")
        self.__apply_gecko()
        self.__apply_hooks()

        if clean_up:
            print(f"{FCYAN} Cleaning up temporary files\n")
            delete_dir(self.temp_dir)
        print(f'\n{FLGREEN}🎊 BUILD COMPLETE 🎊\nSaved .dol to {FLCYAN}"{dol_outpath}"{FLGREEN}!')

    def __get_source_files(self):
        """Adds all source files found the specified folder to the Project for complilation.
        Files within ignore list will be removed."""
        if self.auto_import == False:
            return
        for folder in self.source_folders:
            for file in Path(folder).glob("*.*"):
                ext = file.suffix
                file = file.as_posix()
                if file in self.ignored_files:
                    continue
                match (ext):
                    case ".c":
                        self.add_c_file(file)
                    case ".cpp":
                        self.add_cpp_file(file)
                    case ".s":
                        self.add_asm_file(file)

    def __compile(self):
        with ProcessPoolExecutor() as executor:
            tasks = []
            for source in self.c_files + self.cpp_files:
                outpath = self.temp_dir + source.split("/")[-1] + ".o"
                self.object_files.append(outpath)
                self.__process_pragmas(source)
                task = executor.submit(self.compile, source, outpath, source.endswith("cpp"))
                print(f"{COMPILING} {source}")
                # task = Process(target=self.compile, args=(source, outpath, source.endswith("cpp")))
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
            args = [GPP, "-c"] + self.gpp_args
        else:
            args = [GCC, "-c"] + self.gcc_args
        args += self.common_args
        for path in self.include_folders:
            args.append("-I" + path)
        args.extend([input, "-o", output, "-fdiagnostics-color=always"])

        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        return process.returncode, input, out.decode(), err.decode()

    def __find_undefined_cpp_symbols(self, object_file: str):
        nm_file = dump_nm(object_file)
        print(f"{FYELLOW}Analyzing NM Output -> {FLCYAN + nm_file}...")
        source_file = object_file.replace(self.temp_dir, "").rsplit(".", 2)[0]
        with open(nm_file, "r") as f:
            for line in f.readlines():
                if line.startswith(("0", "8")):
                    line = line[8:]
                line = line.strip()
                if line == "d":  # not sure why a single 'd' gets written on a line to the nm on occasion.
                    continue
                (type, symbol_name) = line.split(" ")
                type = type.lower()
                symbol = self.symbols[symbol_name]
                symbol.name = symbol_name
                if symbol_name.startswith("_Z"):
                    symbol.demangled_name = self.demangle(symbol_name)
                    self.symbols[symbol.demangled_name] = symbol
                else:
                    symbol.is_c_linkage = True
                    symbol.demangled_name = symbol_name
                if type == "u":
                    continue
                if type == "t":
                    symbol.is_function = True
                elif type == "v":
                    symbol.is_weak = True
                elif type == "b":
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
        for file in self.symbols_paths:
            lines = open(file, "r").readlines()
            section = "." + file.split("/")[1].split(".")[0]
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
        dump_objdump(self.project_objfile, "-tSr", "-C")
        self.__find_undefined_cpp_symbols(self.project_objfile)
        self.__analyze_readelf(dump_readelf(self.project_objfile, "-a", "--wide", "--debug-dump"))

    def __generate_linkerscript(self):
        with open(self.temp_dir + self.project_name + "_linkerscript.ld", "w") as f:

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

            if self.entry_function:
                f.write("ENTRY(" + self.entry_function + ");\n")
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
            f.write(f"\t. = 0x{self.inject_address:4x};")
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
        self.add_linkerscript(self.temp_dir + self.project_name + "_linkerscript.ld")

    def __link(self):
        print(f"{FLCYAN}Linking...{FYELLOW}")
        args = [GPP]
        for arg in self.ld_args:
            args.append("-Wl," + arg)
        for file in self.object_files:
            args.append(file)
        args.extend(self.linkerscripts)
        args.extend(["-Wl,-Map", f"{self.temp_dir + self.project_name}.map"])
        args.extend(["-o", self.project_objfile])
        if self.verbose:
            print(f"{FLMAGENTA}{args}")
        exit_code = subprocess.call(args)
        if exit_code:
            raise RuntimeError(f'{ERROR} failed to link object files"\n')
        else:
            print(f"{LINKED}{FLMAGENTA} -> {FLCYAN}{self.temp_dir + self.project_name}.o")

    def __process_project(self):
        with open(self.project_objfile, "rb") as f:
            elf = ELFFile(f)
            with open(self.temp_dir + self.project_name + ".bin", "wb") as data:
                for symbol in elf.iter_sections():
                    if symbol.header["sh_addr"] < self.inject_address:
                        continue
                    # Filter out sections without SHF_ALLOC attribute
                    if symbol.header["sh_flags"] & 0x2:
                        data.seek(symbol.header["sh_addr"] - self.inject_address)
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
                    symbol.library_file = self.project_name + ".o"
                    if ndx == "ABS":
                        continue
                    symbol.section = section_map[int(ndx)]

    def __apply_hooks(self):
        for hook in self.hooks:
            hook.resolve(self.symbols)
            hook.apply_dol(self.dol)
            if self.verbose:
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
                new_section = TextSection(self.inject_address, self.bin_data)
            elif len(self.dol.dataSections) <= DolFile.MaxDataSections:
                new_section = DataSection(self.inject_address, self.bin_data)
            else:
                raise RuntimeError("DOL is full! Cannot allocate any new sections.")
            self.dol.append_section(new_section)
            self.__patch_osarena_low(self.dol, self.inject_address + len(self.bin_data))

        with open(self.dol_outpath, "wb") as f:
            self.dol.save(f)

    def __apply_gecko(self):
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
            vaddress = self.inject_address + len(self.bin_data)
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
        if not self.symbol_map_outpaths:
            print(f"{FLCYAN}No paths found for symbol map output. Skipping.")
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
                if symbol.entry["st_value"] < self.inject_address:
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
                print(
                    f'{FLGREEN + symbol_data["name"]} {FLMAGENTA}@ {hex(symbol_data["address"])} {FLCYAN}({index_to_name[symbol_data["section_index"]]}) {FLGREEN}Size: {str(symbol_data["size"])} bytes {FLYELLOW +symbol_data["bind"]}, {symbol_data["type"]}',
                    end=" ",
                )
                print(f"{FLGREEN}Added")
                section_symbols[symbol_data["section"]].append(symbol_data)
            with open(self.map_inpath, "r+") as f:
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
                            insert_str = f'  {symbol["address"] - self.inject_address:08X} {symbol["size"]:06X} {symbol["address"]:08X}  4 '
                            if symbol["name"] in self.symbols:
                                symbol = self.symbols[symbol["name"]]
                                insert_str += f"{symbol.demangled_name}\t {symbol.section} {symbol.source_file} {symbol.library_file}\n"
                            contents.insert(insert_index[section] + insert_offset, insert_str)
                            insert_offset += 1
                for path in self.symbol_map_outpaths:
                    open(path, "w").writelines(contents)

    def demangle(self, string: str):
        process = subprocess.Popen([CPPFLIT, string], stdout=subprocess.PIPE)
        demangled = re.sub("\r\n", "", process.stdout.readline().decode("ascii"))
        if self.verbose:
            print(f" 🧼 {FBLUE+ string + FLMAGENTA} -> {FLGREEN + demangled}")
        return demangled

    def set_entry_function(self, func_symbol: str):
        """Sets the entry function to use. Must have C linkage (extern "C").

        This is necessary for the "-gc-section" compiler flag to work"""
        self.entry_function = func_symbol
        self.ld_args += ["-gc-sections"]

    def set_sda_bases(self, sda: int, sda2: int):
        self.common_args += ["-msdata=sysv"]
        self.ld_args += [f"--defsym=_SDA_BASE_={hex(sda)}"]
        self.ld_args += [f"--defsym=_SDA2_BASE_={hex(sda2)}"]

    def add_symbol_map_output(self, path: str):
        """Adds the specified path to the list of maps to be."""
        self.symbol_map_outpaths.append(path)

    def add_linkerscript(self, path: str):
        self.linkerscripts.extend(["-T", assert_file_exists(path)])

    def add_symbols_folder(self, path: str):
        """Adds all .txt files found in this folder for Freighter to pull manually defined symbols from."""
        for file in Path(assert_dir_exists(path)).glob("*.txt"):
            self.symbols_paths.append(file.as_posix())

    def add_include_folder(self, path: str):
        """Adds the specified folder as an -I compiler flag

        Note: Folders within the root folder with the following names are automatically added:

        include/

        includes/

        headers/
        """
        self.include_folders.append(assert_dir_exists(path))

    def add_gecko_folder(self, path: str):
        """Adds all Gecko files found in this folder to the Project for complilation."""
        for file in Path(path).glob("*.txt*"):
            self.add_gecko_file(file.as_posix())

    def add_c_file(self, path: str) -> None:
        """Adds the C (.c) file to the Project for compilation."""
        self.c_files.append(assert_file_exists(path))

    def add_cpp_file(self, path: str):
        """Adds the C++ (.cpp) file to the Project for compilation."""
        self.cpp_files.append(assert_file_exists(path))

    def add_asm_file(self, path: str):
        """Adds the ASM (.s) file to the Project for compilation."""
        self.asm_files.append(assert_file_exists(path))

    def add_gecko_file(self, path: str):
        """Adds the Gecko (.txt) file to the Project for compilation."""
        for child in GeckoCodeTable.from_text(open(path, "r").read()):
            self.gecko_table.add_child(child)

    def add_static_library(self, path: str):
        """Adds the static library (.a) file to the Project for compilation."""
        self.static_libs.append(assert_dir_exists(self.library_folders + path))

    def ignore_file(self, *paths: str):
        """Tells Freighter to not compile these files"""
        for file in paths:
            self.ignored_files.append(assert_file_exists(file))

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

        if self.verbose == True:
            size = rom_end - self.inject_address
            print(f"{FLCYAN}✨What's new:")
            print(f"{FLBLUE}Mod Size: {FYELLOW}0x{FLYELLOW}{size:x}{FLGREEN} Bytes or {FLYELLOW}~{size/1024:.2f}{FLGREEN} KiBs")
            print(f"{FLBLUE}Injected @: {HEX}{self.inject_address:x}")
            print(f"{FLBLUE}Mod End @: {HEX}{rom_end:x}\n")

            print(f"{FLBLUE}Stack Moved To: {HEX}{stack_addr:x}")
            print(f"{FLBLUE}Stack End @: {HEX}{stack_end:x}")
            print(f"{FLBLUE}New OSArenaLo: {HEX}{osarena_lo:x}\n")

            print(f"{FLBLUE}Debug Stack Moved to: {HEX}{db_stack_addr:x}")
            print(f"{FLBLUE}Debug Stack End @: {HEX}{db_stack_end:x}")
            print(f"{FLBLUE}New Debug OSArenaLo: {HEX}{db_osarena_lo:x}")
