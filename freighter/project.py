import hashlib
from re import Pattern
import re
import subprocess
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import cache
from os import makedirs
from time import time
from typing import Iterator,DefaultDict

from dolreader.dol import DolFile
from dolreader.section import DataSection, Section, TextSection
from elftools.elf.elffile import ELFFile, SymbolTableSection
from geckolibs.gct import GeckoCodeTable
from geckolibs.geckocode import AsmInsert, AsmInsertXOR

from freighter.config import *
from freighter.colors import *
from freighter.console import *
from freighter.exceptions import *
from freighter.fileformats import *
from freighter.filelist import *
from freighter.hooks import *
from freighter.filelist import *


def strip_comments(line: str):
    return line.split("//")[0].strip()


class FreighterProject:

    def __init__(self, user_environment: UserEnvironment, project_config: ProjectConfig):
        
        self.project_name = project_config.ProjectName
        self.user_environment = user_environment
        self.file_manager = FileManager(project_config)
        self.profile: Profile = project_config.selected_profile  # Allows multiprocessing processes to have context
        self.banner_config = project_config.BannerConfig
        self.compiler_args = project_config.selected_profile.CompilerArgs
        self.ld_args = project_config.selected_profile.LDArgs
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

        self.dol = DolFile(open(self.profile.InputDolFile, "rb"))
        # if not self.profile.InjectionAddress:
        # self.profile.InjectionAddress = self.dol.lastSection.address + self.dol.lastSection.size
        # Console.print(f"{WHITE}Base address auto-set from end of Read-Only Memory: {Cyan}{self.profile.InjectionAddress:x}\n{WHITE}Do not rely on this if your DOL uses .sbss2\n")

        if self.profile.InjectionAddress % 32:
            Console.print("Warning! DOL sections must be 32-byte aligned for OSResetSystem to work properly!\n")

        if self.profile.SDA and self.profile.SDA2:
            self.compiler_args += ["-msdata=eabi"]
            self.ld_args += [
                f"--defsym=_SDA_BASE_={hex(self.profile.SDA)}",
                f"--defsym=_SDA2_BASE_={hex(self.profile.SDA2)}",
            ]

        if self.profile.InputSymbolMap:
            self.profile.OutputSymbolMapPaths.append(self.user_environment.DolphinMaps.create_filepath(self.profile.GameID + ".map"))
        if self.profile.StringHooks:
            for address, string in self.profile.StringHooks.items():
                self.hooks.append(StringHook(address, string))
        filepath = self.profile.TemporaryFilesFolder.create_filepath(self.project_name + ".o")
        self.final_object_file = ObjectFile(self.file_manager,filepath)
        self.gecko_table = GeckoCodeTable(self.profile.GameID, self.project_name)

    def build(self) -> None:
        build_start_time = time()
        if not self.profile.TemporaryFilesFolder.exists():
            self.profile.TemporaryFilesFolder.create()
        self.get_source_files()
        start = time()
        self.process_pragmas()
        print(f"Processed pragmas in {time()-start} seconds")
        self.compile()
        self.load_symbol_definitions()
        self.generate_linkerscript()
        self.link()
        self.bin_path = self.profile.TemporaryFilesFolder.create_filepath(self.project_name + ".bin")
        self.process_project()
        self.bin_data = bytearray(open(self.bin_path, "rb").read())
        self.analyze_final()
        self.save_symbol_map()

        Console.print(f"{ORANGE}Begin Patching...")
        self.apply_gecko()
        self.apply_hooks()
        self.patch_osarena_low(self.dol, self.profile.InjectionAddress + len(self.bin_data))
        with open(self.profile.OutputDolFile, "wb") as f:
            self.dol.save(f)

        self.create_banner()

        self.build_time = time() - build_start_time
        Console.print(f'\n{GREEN}🎊 Build Complete! 🎊\nSaved final binary to "{self.profile.OutputDolFile}"!')
        self.print_extras()
        self.final_object_file.calculate_hash()
        self.file_manager.save_state()

    def cleanup(self):
        Console.print(f'{CYAN}Cleaning up temporary files at "{self.profile.TemporaryFilesFolder}"')
        self.profile.TemporaryFilesFolder.delete()
        Console.print("Removed temporary files.")

    def create_banner(self) -> None:
        if self.banner_config:
            Console.print("Generating game banner...")

            texture = GameCubeTexture(self.banner_config.BannerImage)
            banner = BNR()
            banner.banner_image.data = texture.encode(ImageFormat.RGB5A3)
            banner.description.data = self.banner_config.Description
            banner.title.data = self.banner_config.Title
            banner.gamename.data = self.banner_config.GameName
            banner.maker.data = self.banner_config.Maker
            banner.short_maker.data = self.banner_config.ShortMaker
            banner.save(self.banner_config.OutputPath)
            Console.print(f'Banner saved to "{self.banner_config.OutputPath}"')

    def print_extras(self) -> None:
        with open(self.profile.OutputDolFile, "rb") as f:
            md5 = hashlib.file_digest(f, "md5").hexdigest()
            sha_256 = hashlib.file_digest(f, "sha256").hexdigest()
            sha_512 = hashlib.file_digest(f, "sha512").hexdigest()
            Console.print(f"{GREEN}MD5: {CYAN}{md5}\n{GREEN}SHA-256: {CYAN}{sha_256}\n{GREEN}SHA-512: {CYAN}{sha_512}")

        symbols = list[Symbol]()
        for symbol in self.symbols.values():
            symbols.append(symbol)
        symbols = list(set(symbols))
        symbols.sort(key=lambda x: x.size, reverse=True)
        symbols = symbols[:10]
        Console.print(f"\nTop biggest symbols:")
        for symbol in symbols:
            Console.print(f'{GREEN}{symbol}{CYAN} in "{ORANGE}{symbol.source_file}{CYAN}" {PURPLE}{symbol.size}{GREEN} bytes')

        Console.print(f"\n{CYAN}Compilation Time: {PURPLE}{self.compile_time:.2f} {CYAN}seconds")
        Console.print(f"{CYAN}Build Time {PURPLE}{self.build_time:.2f} {CYAN}seconds")

    def dump_objdump(self, object_path: ObjectFile, *args: str | Path) -> FilePath:
        """Dumps the output from DevKitPPC's powerpc-eabi-objdump.exe to a .txt file"""
        args = (self.user_environment.OBJDUMP, object_path) + args
        outpath = self.profile.TemporaryFilesFolder.create_filepath(object_path.filepath.stem + ".s")

        with open(outpath, "w") as f:
            subprocess.call(args, stdout=f)
        return outpath

    def dump_nm(self, object_path: FilePath, *args: str | Path) -> FilePath:
        """Dumps the output from DevKitPPC's powerpc-eabi-nm.exe to a .txt file"""
        args = (self.user_environment.NM, object_path) + args
        outpath = self.profile.TemporaryFilesFolder.create_filepath(object_path.filepath.stem + ".o.nm")
        with open(outpath, "w") as f:
            subprocess.call(args, stdout=f)
        return outpath

    def dump_readelf(self, object_path: ObjectFile, *args: str | Path) -> FilePath:
        """Dumps the output from DevKitPPC's powerpc-eabi-readelf.exe to a .txt file"""
        args = (self.user_environment.READELF, object_path) + args

        outpath = self.profile.TemporaryFilesFolder.create_filepath(object_path.filepath.stem + ".o.readelf")
        with open(outpath, "w") as f:
            subprocess.call(args, stdout=f)
        return outpath

    def get_source_files(self) -> None:
        for folder in self.profile.SourceFolders:
            for file in folder.find_files(".c", ".cpp", recursive=True):
                if file in self.profile.IgnoredSourceFiles:
                    continue
                source_file = SourceFile(self.file_manager,file)
                self.source_files.append(source_file)
                self.object_files.append(source_file.object_file)

    def compile(self) -> None:
        compile_start_time = time()
        compile_list = []
        for source_file in self.source_files:
            if source_file.needs_recompile():
                source_file.object_file.is_dirty = True
                compile_list.append(source_file)
        
        if compile_list:  
            failed_compilations = list[tuple[SourceFile, str]]()
            successful_compilations = list[SourceFile]()
            with ProcessPoolExecutor() as executor:
                tasks = []
                for source_file in compile_list:
                    Console.print(f'{COMPILING} "{source_file}"')
                    task = executor.submit(self.compile_task, source_file, source_file.object_file)
                    tasks.append(task)
                for result in as_completed(tasks):
                    exitcode, source_file, out, err = result.result()
                    if exitcode:
                        failed_compilations.append((source_file, err))
                        Console.print(f'{ERROR} "{source_file}"{CYAN}')
                        continue
                    else:
                        Console.print(f'{SUCCESS} "{source_file}"{CYAN}')
                        successful_compilations.append(source_file)
            if failed_compilations:
                bad_source_files = ""
                for source_file, error in failed_compilations:
                    import re
                    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", re.VERBOSE)
                    errorstr = ansi_escape.sub("", error)
                    errorlines = errorstr.split("\n")
                    length = max(len(line) for line in errorlines)
                    header = f"{CYAN}{'=' * length}{AnsiAttribute.RESET}\n"
                    Console.print(f'{header}{ORANGE}{AnsiAttribute.BOLD}Compile Errors{AnsiAttribute.RESET}: "{source_file}"\n{header}{error}')
                    bad_source_files += str(source_file) + "\n"
                raise FreighterException(f"{ORANGE}Build process halted. Please fix code errors for the following files:\n{CYAN}" + bad_source_files)
            
            for source_file in successful_compilations:
                if source_file.object_file.is_hash_same():
                    Console.print(f'"{source_file}" resulted in the same binary.')
                    self.symbols.update(source_file.object_file.restore_previous_state().symbols)
                    self.find_undefined_symbols(source_file.object_file)
                else:
                    # Update the symbol dict for any new symbols
                    self.find_undefined_symbols(source_file.object_file)
        else:
            Console.print("No source files have been modified.")
            self.symbols.update(self.final_object_file.restore_previous_state().symbols)
        
        self.compile_time = time() - compile_start_time
            
        

    def compile_task(self, source_file: SourceFile, output: ObjectFile) -> tuple[int, SourceFile, str, str]:
        args = []
        if source_file.filepath.suffix == ".cpp":
            args = [self.user_environment.GPP, "-c"] + self.profile.GPPArgs
        else:
            args = [self.user_environment.GCC, "-c"] + self.profile.GCCArgs
        args += self.compiler_args
        for path in self.profile.IncludeFolders:
            args.append("-I" + str(path))
        args.extend([source_file, "-o", output, "-fdiagnostics-color=always"])

        process = subprocess.Popen(args, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        return process.returncode, source_file, out.decode(), err.decode()

    def find_undefined_symbols(self, object_file: ObjectFile):
        nm_file = self.dump_nm(object_file)
        Console.print(f'{ANALYZING} "{nm_file}"')
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
                    if object_file.source_name == self.project_name:
                        symbol.source_file = ""  # Temporary workaround for symbols sourced from external libs
                    else:
                        symbol.source_file = object_file.source_name

    def load_symbol_definitions(self):
        # Load symbols from a file. Supports recognizing demangled c++ symbols
        Console.print(f"{ORANGE}Loading manually defined symbols...")
        for file in self.profile.SymbolsFolder.find_files(".txt",recursive=True):
            with open(file.as_posix(), "r") as f:
                lines = f.readlines()

            section = "." + file.stem
            for line in lines:
                line = line.rstrip().partition("//")[0]
                if line:
                    name, address = line.split(" = ")
                    if name == "sys":
                        pass
                    if name in self.symbols:
                        symbol = self.symbols[name]
                        if symbol.source_file:  # skip this symbol because we are overriding it
                            continue
                        symbol.hex_address = address
                        symbol.is_absolute = True
                        symbol.section = section

    def process_pragmas(self):
        for source_file in self.source_files:
            if source_file in self.profile.IgnoreHooks:
                continue
            is_c_linkage = False
            if source_file.filepath.suffix == ".c":
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
                    line_number, lines, function_symbol = self.get_function_symbol(source_file,lines, is_c_linkage)
                    if branch_type == "bl":
                        for address in addresses:
                            self.hooks.append(BranchHook(address, function_symbol,source_file.filepath,line_number, True))
                    elif branch_type == "b":
                        for address in addresses:
                            self.hooks.append(BranchHook(address, function_symbol,source_file.filepath,line_number))
                    else:
                        raise FreighterException(f"{branch_type} is not a valid supported branch type for #pragma hook!\n" + f"{line} Found in {CYAN}{source_file}{ORANGE} on line number {line_number + 1}")
                elif line.startswith("inject"):
                    inject_type, *addresses = line.removeprefix("inject ").split(" ")
                    if inject_type == "pointer":
                        line_number, lines, function_symbol = self.get_function_symbol(source_file,lines, is_c_linkage)
                        for address in addresses:
                            self.hooks.append(PointerHook(address, function_symbol))
                    elif inject_type == "string":
                        for address in addresses:
                            inject_string = ""
                            self.hooks.append(StringHook(address, inject_string))
                    else:
                        raise FreighterException(f"Arguments for {PURPLE}{line}{CYAN} are incorrect!\n" + f"{line} Found in {CYAN}{source_file}{ORANGE} on line number {line_number + 1}")
        
        # May help fix stupid mistakes  
        unique_addresses = {}
        duplicates = defaultdict[int,list[BranchHook]](list[BranchHook])
        for hook in [x for x in self.hooks if isinstance(x,BranchHook)]:
            if hook.address not in unique_addresses.keys():
                unique_addresses[hook.address] = hook
            else:
                duplicates[hook.address].append(hook)
                if unique_addresses[hook.address] not in duplicates[hook.address]:
                    duplicates[hook.address].append(unique_addresses[hook.address])
        
        if duplicates:
            bad_hooks_string= ""
            for address, hooks in duplicates.items():
                bad_hooks_string += f"{hex(address)}\n"
                for hook in hooks:
                    bad_hooks_string += f'\t{hook.symbol_name} in "{hook.source_file}:{hook.line_number}"\n'
            raise FreighterException(f"BranchHooks referencing different functions were found hooking into the same address!\n{bad_hooks_string}")
            

    re_function_name:Pattern[str] = re.compile(r".* (\w*(?=\()).*")
    re_parameter_names:Pattern[str] = re.compile(r'([^\]&*]\w+)(,|(\)\[)|(\)\()|\))')
    re_flip_const:Pattern[str] = re.compile(r"(const) ([:\[\]<>\w]*[^ *&])")
    re_flip_volatile:Pattern[str] = re.compile(r"(volatile) ([:\[\]<>\w]*[^ *&])")
    re_flip_const_volatile:Pattern[str] = re.compile(r"(const volatile) ([:\[\]<>\w]*[^ *&])")
    
    def get_function_symbol(self,source_file:SourceFile, lines: Iterator[tuple[ int, str]], is_c_linkage: bool = False) -> tuple[int, Iterator[tuple[int, str]], str]:
        """TODO: This function doesnt account for transforming typedefs/usings back to their primitive or original typename"""
        """Also doesn't account for namespaces that arent in the function signature"""
      
        while True:
            line_number, line = next(lines)
            if 'extern "C"' in line:
                is_c_linkage = True
            if not line:
                continue
            if "(" in line:
                line = strip_comments(line)
                line = line.rsplit('{')[0]
                if is_c_linkage:
                    return line_number, lines, self.re_function_name.sub(r"\1",line,1)
                try:
                    result :list[str]= re.findall(r"(.*)(\(.*\))",line)[0]
                    function_name, signature = result
                    namespace_parts = function_name.split("::")
                    if len(namespace_parts) > 1 and namespace_parts[-1] == namespace_parts[-2]:
                        Console.print(f"'{line}' is a constructor")
                    else:
                        function_name = function_name.rsplit(" ",-1)[-1]
                except:
                    raise BadFunctionSignatureExecption(source_file,line_number, line)
                if signature == '()':
                    return line_number, lines, function_name + signature
                signature = self.re_parameter_names.sub(r'\2',signature)
                
                if "const " in signature or "volatile " in signature:
                    parameters = signature.split(",")
                    parameters[0] = parameters[0][1:]
                    parameters[-1] = parameters[-1][:-1]
                    result = []
                    for parameter in parameters:
                        parameter = parameter.lstrip()
                        if "volatile const" in parameter:
                            parameter = parameter.replace("volatile const", "const volatile")
                        if "const volatile" in parameter:
                            parameter = self.re_flip_const_volatile.sub(r"\2 \1",parameter)
                        elif "volatile" in parameter:
                            parameter = self.re_flip_volatile.sub(r"\2 \1",parameter)
                        else:
                            # c++filt returns demangled symbols with 'type const*' or 'type const&' rather than 'const type*' or 'const type&'
                            parameter = self.re_flip_const.sub(r"\2 \1",parameter)  
                        # Passing types by value is implicitly const. c++filt returns a demangled symbol with const removed
                        if parameter[-1] not in ["*","&"]:
                            parameter = parameter.replace('const',"").replace("volatile","").rstrip()                        
                        result.append(parameter)
                    signature = f"({', '.join(result)})"
                
                return line_number, lines, function_name + signature

    def analyze_final(self):
        Console.print(f"{ORANGE}Dumping objdump...{CYAN}")
        self.dump_objdump(self.final_object_file, "-tSr", "-C")
        self.find_undefined_symbols(self.final_object_file)
        self.analyze_readelf(self.dump_readelf(self.final_object_file, "-a", "--wide", "--debug-dump"))

    def generate_linkerscript(self):
        written_symbols = set[Symbol]()  # Keep track of duplicates
        linkerscript_file = self.profile.TemporaryFilesFolder.create_filepath(self.project_name + ".ld")
        with open(linkerscript_file, "w") as f:

            def write_section(section: str):
                symbols = [symbol for symbol in self.symbols.values() if symbol.section == section]
                if not symbols:
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
            for section in self.profile.DiscardSections:
                f.write(f"\t\t*({section}*);\n")
            f.write("\n")
            for lib in self.profile.DiscardLibraryObjects:
                f.write(f"\t\t*{lib}(*);\n")
            f.write("\t}\n\n")

            f.write(f"\t. = 0x{self.profile.InjectionAddress:4x};\n")
            f.write(
                "\t__end__ = .;\n"
                "\t.sdata ALIGN(0x20):\n\t{\n\t\t*(.sdata*)\n\t}\n\n"
                "\t.sbss ALIGN(0x20):\n\t{\n\t\t*(.sbss*)\n\t}\n\n"
                "\t.sdata2 ALIGN(0x20):\n\t{\n\t\t*(.sdata2*)\n\t}\n\n"
                "\t.sbss2 ALIGN(0x20):\n\t{\n\t\t*(.sbss2*)\n\t}\n\n"
                "\t.rodata ALIGN(0x20):\n\t{\n\t\t*(.rodata*)\n\t}\n\n"
                "\t.data ALIGN(0x20):\n\t{\n\t\t*(.data*)\n\t}\n\n"
                "\t.bss ALIGN(0x20):\n\t{\n\t\t*(.bss*)\n\t}\n\n"
                "\t.ctors ALIGN(0x20):\n\t{\n\t\t*(.ctors*)\n\t}\n"
                "\t.dtors ALIGN(0x20):\n\t{\n\t\t*(.dtors*)\n\t}\n"
                "\t.init ALIGN(0x20):\n\t{\n\t\t*(.init*)\n\t}\n"
                "\t.fini ALIGN(0x20):\n\t{\n\t\t*(.fini*)\n\t}\n"
                "\t.eh_frame ALIGN(0x20):\n\t{\n\t\t*(.eh_frame*)\n\t}\n"
                "\t.text ALIGN(0x20):\n\t{\n\t\t*(.text*)\n\t}\n"
                "}"
            )
           
      
        self.profile.LinkerScripts.append(linkerscript_file)

    def link(self):
        Console.print(f"{CYAN}Linking...{ORANGE}")
        args: list[str | Path] = [self.user_environment.GPP]
        for arg in self.ld_args:
            args.append("-Wl," + str(arg))
        for file in self.object_files:
            args.append(file.filepath)
        for linkerscript in self.profile.LinkerScripts:
            args.append("-T" + str(linkerscript))
        args.extend(["-Wl,-Map", self.profile.TemporaryFilesFolder.create_filepath(self.project_name + ".map")])
        args.extend(["-o", self.final_object_file.filepath])

        Console.print(f"{PURPLE}{args}", PrintType.VERBOSE)
        process = subprocess.Popen(args, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        
        
        if process.returncode:
            re_quote = re.compile(r"(`)")
            re_parens = re.compile(r"(\(.*\))")
            error = re_quote.sub("'",err.decode())
            error = re_parens.sub(rf'{MAGENTA}\n\t({PURPLE}\1{MAGENTA}){AnsiAttribute.RESET}\n',error)
            Console.print(error)
            raise FreighterException(f'{ERROR} failed to link object files"\n')
        else:
            Console.print(f"{LINKED}{PURPLE} -> {CYAN}{self.final_object_file}")

    def process_project(self):
        with open(self.final_object_file, "rb") as f:
            elf = ELFFile(f)
            with open(self.bin_path, "wb") as data:
                for symbol in elf.iter_sections():
                    if symbol.header["sh_addr"] < self.profile.InjectionAddress:
                        continue
                    # Filter out sections without SHF_ALLOC attribute
                    if symbol.header["sh_flags"] & 0x2:
                        data.seek(symbol.header["sh_addr"] - self.profile.InjectionAddress)
                        data.write(symbol.data())

    def analyze_readelf(self, path: FilePath):
        section_map = {}
        Console.print(f'{ANALYZING} "{path}"')
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
                    symbol.size = int(size)
                    symbol.library_file = self.project_name + ".o"
                    if ndx == "ABS":
                        continue
                    symbol.section = section_map[int(ndx)]

    def apply_hooks(self):
        for hook in self.hooks:
            hook.resolve(self.symbols)
            hook.apply_dol(self.dol)
            Console.print(hook)
        bad_symbols = list[str]()
        for hook in self.hooks:
            if not hook.good and hook.symbol_name not in bad_symbols:
                bad_symbols.append(hook.symbol_name)
        if bad_symbols:
            badlist = "\n"
            for name in bad_symbols:
                badlist += f'{ORANGE}{name}{AnsiAttribute.RESET} found in {CYAN}"{self.symbols[name].source_file}"\n'
            raise FreighterException(
                f'{ERROR} Freighter could not resolve hook addresses for the given symbols:\n{badlist}\n{AnsiAttribute.RESET}Possible Reasons:{ORANGE}\n• The cache Freighter uses for incremental builds is faulty and needs to be reset. Use -cleanup option to remove the cache.\n• If this is a C++ Symbol there may be a symbol definition missing from the {{Cyan}}"symbols"{{Orange}} folder'
            )
        if len(self.bin_data) > 0:
            new_section: Section
            if len(self.dol.textSections) <= DolFile.MaxTextSections:
                new_section = TextSection(self.profile.InjectionAddress, self.bin_data)
            elif len(self.dol.dataSections) <= DolFile.MaxDataSections:
                new_section = DataSection(self.profile.InjectionAddress, self.bin_data)
            else:
                raise FreighterException("DOL is full! Cannot allocate any new sections.")
            self.dol.append_section(new_section)

        with open(self.profile.OutputDolFile, "wb") as f:
            self.dol.save(f)

    def apply_gecko(self):
        for gecko_txt in self.profile.GeckoFolder.find_files(".txt", recursive=True):
            if gecko_txt in self.profile.IgnoredGeckoFiles:
                continue
            for child in GeckoCodeTable.from_text(open(gecko_txt, "r").read()):
                self.gecko_table.add_child(child)
        while (len(self.bin_data) % 4) != 0:
            self.bin_data += b"\x00"
        Console.print(f"\n[{GREEN}Gecko Codes{AnsiAttribute.RESET}]")
        for gecko_code in self.gecko_table:
            status = f"{GREEN}ENABLED {CYAN}" if gecko_code.is_enabled() else f"{RED}DISABLED{CYAN}"
            if gecko_code.is_enabled() == True:
                for gecko_command in gecko_code:
                    if gecko_command.codetype not in SupportedGeckoCodetypes:
                        status = "OMITTED"
            Console.print(f"{status:12s} ${gecko_code.name}")
            if status == "OMITTED":
                Console.print(f"{ORANGE}Includes unsupported codetypes:")
                for gecko_command in gecko_code:
                    if gecko_command.codetype not in SupportedGeckoCodetypes:
                        Console.print(gecko_command)
            vaddress = self.profile.InjectionAddress + len(self.bin_data)
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
        Console.print("\n")
        self.gecko_table.apply(self.dol)

    def save_symbol_map(self):
        if not self.profile.InputSymbolMap:
            Console.print(f"{ORANGE}No input symbol map. Skipping.")
            return

        if not self.profile.OutputSymbolMapPaths:
            Console.print(f"{ORANGE}No paths found for symbol map output. Skipping.")
            return

        Console.print(f"{CYAN}Copying symbols to map...")
        with open(self.final_object_file, "rb") as f:
            elf = ELFFile(f)

            index_to_name = {}
            for index, section in enumerate(elf.iter_sections()):
                index_to_name[index] = section.name

            section_symbols = defaultdict(list)
            symtab = elf.get_section_by_name(".symtab")
            if isinstance(symtab, SymbolTableSection):
                # Filter through the symbol table so that we only append symbols that use physical memory
                for symbol in symtab.iter_symbols():
                    symbol_data = {}
                    symbol_data["bind"], symbol_data["type"] = symbol.entry["st_info"].values()
                    if symbol_data["type"] in ["STT_NOTYPE", "STT_FILE"]:
                        continue
                    if symbol.entry["st_value"] < self.profile.InjectionAddress:
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
                    #     Console.print(
                    #         f'{GREEN + symbol_data["name"]} {PURPLE}@ {hex(symbol_data["address"])} {Cyan}({index_to_name[symbol_data["section_index"]]}) {GREEN}Size: {str(symbol_data["size"])} bytes {Orange +symbol_data["bind"]}, {symbol_data["type"]}',
                    #         end=" ",
                    #     )
                    #     Console.print(f"{GREEN}Added")
                    section_symbols[symbol_data["section"]].append(symbol_data)
            with open(self.profile.InputSymbolMap, "r+") as f:
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
                            insert_str = f'  {symbol["address"] - self.profile.InjectionAddress:08X} {symbol["size"]:06X} {symbol["address"]:08X}  4 '
                            if symbol["name"] in self.symbols:
                                symbol = self.symbols[symbol["name"]]
                                insert_str += f"{symbol.demangled_name}\t {symbol.source_file} {symbol.library_file}\n"
                            contents.insert(insert_index[section] + insert_offset, insert_str)
                            insert_offset += 1
                for path in self.profile.OutputSymbolMapPaths:
                    open(path, "w").writelines(contents)

    @cache
    def demangle(self, string: str) -> str:
        if not self.demangler_process:
            self.demangler_process = subprocess.Popen([self.user_environment.CPPFLIT], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

        demangled = ""
        if self.demangler_process.stdin and self.demangler_process.stdout:
            self.demangler_process.stdin.write(f"{string}\n".encode())
            self.demangler_process.stdin.flush()
            demangled = self.demangler_process.stdout.readline().decode().rstrip()
            Console.print(f" 🧼 {CYAN}{string}{PURPLE} -> {GREEN}{demangled}", PrintType.VERBOSE)
        return demangled

    def patch_osarena_low(self, dol: DolFile, rom_end: int):
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

        size = rom_end - self.profile.InjectionAddress
        Console.print(
            f"{CYAN}✨What's new:\n{CYAN}Injected Binary Size: 0x{ORANGE}{size:x}{GREEN} Bytes or"
            f" {ORANGE}~{size/1024:.2f}{GREEN} KiBs\n{CYAN}Injection Address @"
            f" 0x{self.profile.InjectionAddress:x}\n{CYAN}New ROM End @ 0x{rom_end:x}\n{CYAN}Stack"
            f" Moved To: 0x{stack_addr:x}\n{CYAN}Stack End @ 0x{stack_end:x}\n{CYAN}New OSArenaLo @"
            f" 0x{osarena_lo:x}\n{CYAN}Debug Stack Moved To: 0x{db_stack_addr:x}\n{CYAN}Debug Stack"
            f" End @ 0x{db_stack_end:x}\n{CYAN}New Debug OSArenaLo @ 0x{db_osarena_lo:x}"
        )
