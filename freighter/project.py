from __future__ import annotations

import hashlib
import re
import subprocess
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import cache
from os import makedirs
from re import Pattern
from time import time
from typing import Iterator

from dolreader.dol import DolFile

from elftools.elf.elffile import ELFFile, SymbolTableSection
from freighter.config import *
from freighter.exceptions import *
from freighter.fileformats import *
from freighter.filemanager import *
from freighter.hooks import *
from freighter.logging import *
from freighter.path import *
from freighter.symbols import *
from io import BytesIO

# class ProjectProtocol(Protocol):
#     def build(self) -> bool:
#         ...

#     def compile(self) -> bool:
#         ...

#     def link(self) -> bool:
#         ...

#     def clean(self) -> bool:
#         ...


class FreighterProject:
    def __init__(self, user_environment: UserEnvironmentConfig, project_config: ProjectConfig, clean: bool):
        self.library_folders: str
        self.source_files = list[SourceFile]()
        self.asm_files = list[SourceFile]()
        self.object_files = list[ObjectFile]()
        self.static_libs = list[str]()

        self.user_environment: UserEnvironmentConfig = user_environment
        self.project_name = project_config.ProjectName
        self.binutils = user_environment.BinUtilsPaths[project_config.TargetArchitecture]
        self.compiler_args = project_config.SelectedProfile.CompilerArgs
        self.ld_args = project_config.SelectedProfile.LDArgs
        self.profile: GameCubeProfile | SwitchProfile = project_config.SelectedProfile
        self.temp_folder = self.profile.TemporaryFilesFolder
        if clean:
            self.clean()
        self.temp_folder.create()
        self.symbol_manager = SymbolManager(self.project_name, self.profile, self.binutils)
        self.file_manager = FileManager(project_config)
        self.find_source_files()

    def clean(self):
        Logger.info(f'{CYAN}Cleaning up temporary files at "{self.temp_folder}"')
        self.temp_folder.delete()
        Logger.info("Removed temporary files.")

    def build(self):
        ...

    def find_source_files(self) -> None:
        for folder in self.profile.SourceFolders:
            for file in folder.find_files(".c", ".cpp", recursive=True):
                if file in self.profile.IgnoredSourceFiles:
                    continue
                source_file = SourceFile(self.file_manager, file)
                self.source_files.append(source_file)
                self.object_files.append(source_file.object_file)

    @performance_profile
    def compile(self, final_object_file: ObjectFile) -> bool:
        compile_list = []
        for source_file in self.source_files:
            if source_file.needs_recompile():
                source_file.object_file.is_dirty = True
                compile_list.append(source_file)

        if not compile_list:
            Logger.info("No source files have been modified.")
            self.symbol_manager.symbols.update(final_object_file.restore_previous_state().symbols)
            return False

        failed_compilations = list[tuple[SourceFile, str]]()
        successful_compilations = list[SourceFile]()
        with ProcessPoolExecutor() as executor:
            tasks = []
            # Compile all source files in the compile list
            for source_file in compile_list:
                Logger.info(f'{COMPILING} "{source_file}"')
                task = executor.submit(self.compile_task, source_file, source_file.object_file)
                tasks.append(task)

            # Await for all compilation tasks to finish
            for result in as_completed(tasks):
                exitcode, source_file, out, err = result.result()
                if exitcode:
                    failed_compilations.append((source_file, err))
                    Logger.info(f'{ERROR} "{source_file}"{CYAN}')
                    continue
                else:
                    Logger.info(f'{SUCCESS} "{source_file}"{CYAN}')
                    successful_compilations.append(source_file)

        # Update the build cache with any successful compilations
        for source_file in successful_compilations:
            if source_file.object_file.is_hash_same():
                Logger.info(f'Modified "{source_file}" compiled into the same binary.')
                self.symbol_manager.symbols.update(source_file.object_file.restore_previous_state().symbols)
                self.symbol_manager.find_symbols_nm(source_file.object_file)
            else:
                # Update the symbol dict for any new symbols
                self.symbol_manager.find_symbols_nm(source_file.object_file)

        # Print to console any compliation errors that occured
        if failed_compilations:
            bad_source_files = ""
            ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", re.VERBOSE)
            for source_file, error in failed_compilations:
                errorstr = ansi_escape.sub("", error)
                errorlines = errorstr.split("\n")
                length = max(len(line) for line in errorlines)
                header = f"{CYAN}{'=' * length}{AnsiAttribute.RESET}\n"
                Logger.info(f'{header}{ORANGE}{AnsiAttribute.BOLD}Compile Errors{AnsiAttribute.RESET}: "{source_file}"\n{header}{error}')
                bad_source_files += str(source_file) + "\n"
            raise FreighterException(f"{ORANGE}Build process halted. Please fix code errors for the following files:\n{CYAN}" + bad_source_files)

        return True

    def compile_task(self, source_file: SourceFile, output: ObjectFile) -> tuple[int, SourceFile, str, str]:
        args = []
        if source_file.path.suffix == ".cpp":
            args = [self.binutils.GPP, "-c"] + self.profile.GPPArgs
        else:
            args = [self.binutils.GCC, "-c"] + self.profile.GCCArgs
        args += self.compiler_args
        for path in self.profile.IncludeFolders:
            args.append("-I" + str(path))
        args.extend([source_file, "-o", output, "-fdiagnostics-color=always"])

        process = subprocess.Popen(args, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        return process.returncode, source_file, out.decode(), err.decode()

    @performance_profile
    def link(self, output_object: ObjectFile):
        Logger.info(f"{CYAN}Linking...{ORANGE}")
        args: list[str | Path] = [self.binutils.GPP]
        for arg in self.ld_args:
            args.append("-Wl," + str(arg))
        for file in self.object_files:
            args.append(file.path)
        for linkerscript in self.profile.LinkerScripts:
            args.append("-T" + str(linkerscript))
        for library in self.profile.Libraries:
            args.append(library)
        args.extend(["-Wl,-Map", self.temp_folder.make_filepath(self.project_name + ".map")])
        args.extend(["-o", output_object.path])

        Logger.debug(f"{PURPLE}{args}")
        process = subprocess.Popen(args, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()

        if process.returncode:
            re_quote = re.compile(r"(`)")
            re_parens = re.compile(r"(\(.*\))")
            error = re_quote.sub("'", err.decode())
            error = re_parens.sub(rf"{MAGENTA}\n\t({PURPLE}\1{MAGENTA}){AnsiAttribute.RESET}\n", error)
            Logger.info(error)
            raise FreighterException(f'{ERROR} failed to link object files"\n')
        else:
            Logger.info(f"{LINKED}{PURPLE} -> {CYAN}{output_object}")


class SwitchProject(FreighterProject):
    def __init__(self, user_environment: UserEnvironmentConfig, project_config: SwitchProjectConfig, clean: bool):
        super().__init__(user_environment, project_config, clean)

    def build(self):
        final_object_file = ObjectFile(self.file_manager, self.temp_folder.make_filepath(self.project_name + ".o"))
        self.compile(final_object_file)
        self.link(final_object_file)
        with open(final_object_file) as f:
            elf = ELFFile(f)


class GameCubeProject(FreighterProject):
    def __init__(self, user_environment: UserEnvironmentConfig, project_config: GameCubeProjectConfig, clean: bool):
        super().__init__(user_environment, project_config, clean)
        if isinstance(project_config.SelectedProfile, GameCubeProfile):
            self.profile: GameCubeProfile = project_config.SelectedProfile
        self.banner_config = project_config.BannerConfig
        self.hook_patcher = GameCubeHookPatcher(self.profile, self.symbol_manager)
        self.gecko_patcher = GeckoPatcher(self.profile, project_config.ProjectName)

        if self.profile.InjectionAddress % 32:
            Logger.warn("Warning! DOL sections must be 32-byte aligned for OSResetSystem to work properly!\n")

        if self.profile.SDA and self.profile.SDA2:
            self.compiler_args += ["-msdata=eabi"]
            self.ld_args += [f"--defsym=_SDA_BASE_={self.profile.SDA.hex}", f"--defsym=_SDA2_BASE_={self.profile.SDA2.hex}"]

    def build(self) -> None:
        final_object_file = ObjectFile(self.file_manager, self.temp_folder.make_filepath(self.project_name + ".o"))
        self.hook_patcher.find_pragma_hooks(self.source_files)

        if self.compile(final_object_file):
            self.symbol_manager.find_missing_symbols()
            self.generate_linkerscript()
            self.link(final_object_file)

        with BytesIO() as final_binary:
            self.write_sections(final_object_file, final_binary)
            self.symbol_manager.find_symbols_nm(final_object_file)
            self.symbol_manager.find_symbols_readelf(final_object_file)
            self.export_symbol_map(final_object_file)
            dol_file = DolFile(open(self.profile.InputBinary, "rb"))
            self.hook_patcher.apply(dol_file, final_binary)
            self.gecko_patcher.apply(dol_file, final_binary)
            self.finalize(final_binary, dol_file)

        self.create_banner()

        Logger.info(f'{GREEN}🎊 Build Complete! 🎊\nSaved final binary to "{self.profile.OutputBinary}"!')
        self.print_extras(final_object_file)

        final_object_file.hash()

        # if FilePath("ProjectFiles.toml").exists:
        #     projectfile_builder = ProjectFileBuilder.load(FilePath("ProjectFiles.toml"))
        #     if projectfile_builder:
        #         projectfile_builder.build(self.file_manager)

        self.file_manager.save_state()

    def finalize(self, final_binary: BytesIO, dol_file: DolFile):
        self.patch_osarena_low(self.profile.InjectionAddress + final_binary.getbuffer().nbytes, dol_file)
        with open(self.profile.OutputBinary, "wb") as f:
            dol_file.save(f)

    def create_banner(self) -> None:
        if self.banner_config:
            Logger.info("Generating game banner...")

            texture = GameCubeTexture(self.banner_config.BannerImage)
            banner = BNR()
            banner.banner_image.data = texture.encode(ImageFormat.RGB5A3)
            banner.description.data = self.banner_config.Description
            banner.title.data = self.banner_config.Title
            banner.gamename.data = self.banner_config.GameTitle
            banner.maker.data = self.banner_config.Maker
            banner.short_maker.data = self.banner_config.ShortMaker
            banner.save(self.banner_config.OutputPath)
            Logger.info(f'Banner saved to "{self.banner_config.OutputPath}"')

    def print_extras(self, final_object_file: ObjectFile) -> None:
        with open(final_object_file, "rb") as f:
            md5 = hashlib.file_digest(f, "md5").hexdigest()
            sha_256 = hashlib.file_digest(f, "sha256").hexdigest()
            sha_512 = hashlib.file_digest(f, "sha512").hexdigest()
            Logger.info(f"Hashes:\n{GREEN}MD5: {CYAN}{md5}\n{GREEN}SHA-256: {CYAN}{sha_256}\n{GREEN}SHA-512: {CYAN}{sha_512}")

        # Sort symbols by size
        symbols = list(self.symbol_manager.symbols.values())
        symbols.sort(key=lambda x: x.size, reverse=True)
        symbols = symbols[:10]

        top_symbols_str = []
        top_symbols_str.append("Top biggest symbols:")
        for symbol in symbols:
            top_symbols_str.append(f'{GREEN}{symbol}{CYAN} in "{ORANGE}{symbol.source}{CYAN}" {PURPLE}{symbol.size}{GREEN} bytes')
        Logger.info("\n".join(top_symbols_str))

    def generate_linkerscript(self):
        written_symbols = set[Symbol]()  # Keep track of duplicates
        linkerscript_file = self.temp_folder.make_filepath(self.project_name + ".ld")
        with open(linkerscript_file, "w") as f:

            def write_section(section: str):
                symbols = [symbol for symbol in self.symbol_manager.symbols.values() if symbol.section == section]
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

    def write_sections(self, object_file: ObjectFile, final_binary: BytesIO):
        with ELFFile.load_from_path(object_file) as elf:
            for symbol in elf.iter_sections():
                if symbol.header["sh_addr"] < self.profile.InjectionAddress:
                    continue
                # Filter out sections without SHF_ALLOC attribute
                if symbol.header["sh_flags"] & 0x2:
                    final_binary.seek(symbol.header["sh_addr"] - self.profile.InjectionAddress)
                    final_binary.write(symbol.data())

    def export_symbol_map(self, final_object_file: ObjectFile):
        if not self.user_environment.DolphinMaps:
            Logger.warn("Dolphin Maps folder is not set in the UserEnvironment.toml. Skipping map export...")
            return

        if not self.profile.InputSymbolMap:
            Logger.warn(f"{ORANGE}No input symbol map. Skipping map export...")
            return

        if not self.profile.OutputSymbolMapPaths:
            Logger.warn(f"{ORANGE}No paths found for symbol map output. Skipping map export...")
            return

        self.profile.OutputSymbolMapPaths.append(self.user_environment.DolphinMaps.make_filepath(self.profile.GameID + ".map"))

        Logger.info(f"{CYAN}Copying new symbols to map file...")

        with open(final_object_file, "rb") as f:
            elf = ELFFile(BytesIO(f.read()))

        index_to_name = {}
        for index, section in enumerate(elf.iter_sections()):
            index_to_name[index] = section.name

        section_symbols = defaultdict(list)
        section = elf.get_section_by_name(".symtab")
        if isinstance(section, SymbolTableSection):
            symbol_table = section
        else:
            raise FreighterException(f'.symtab not found in "{final_object_file}"')

        # Filter through the symbol table so that we only append symbols that use physical memory
        for symbol in symbol_table.iter_symbols():
            symbol_data = {}
            bind, type = symbol.entry["st_info"].values()
            if type in ["STT_NOTYPE", "STT_FILE"]:
                continue
            symbol_data["bind"] = bind
            symbol_data["type"] = type

            address = symbol.entry["st_value"]
            if address < self.profile.InjectionAddress:
                continue
            symbol_data["address"] = address

            size = symbol.entry["st_size"]

            if size == 0:
                continue
            symbol_data["size"] = size

            symbol_data["name"] = symbol.name

            section_index = symbol.entry["st_shndx"]

            if section_index in ["SHN_ABS", "SHN_UNDEF"]:
                continue
            symbol_data["section_index"] = section_index
            symbol_data["section"] = index_to_name[section_index]
            section_symbols[symbol_data["section"]].append(symbol_data)

        # Read original map file to insert new symbols into
        with open(self.profile.InputSymbolMap, "r") as map_file:
            contents = map_file.readlines()

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
                    symbol = self.symbol_manager.get_symbol(symbol["name"])
                    insert_str += f"{symbol.demangled_name}\t {symbol.source} {self.project_name+".o"}\n"
                    contents.insert(insert_index[section] + insert_offset, insert_str)
                    insert_offset += 1

        # Write map file to all output paths
        for path in self.profile.OutputSymbolMapPaths:
            with open(path, "w") as map_file:
                map_file.writelines(contents)
            Logger.info(f'Wrote map file to "{path}"')

    def patch_osarena_low(self, rom_end: int, dol_file: DolFile):
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
        dol_file.seek(0x80005410)
        write_lis(dol_file, 1, sign_extend(stack_addr >> 16, 16))
        write_ori(dol_file, 1, 1, stack_addr & 0xFFFF)

        # It can be assumed that the db_stack_addr value is also set somewhere.
        # However, it does not seem to matter, as the DBStack is not allocated.

        # In [OSInit]...
        # OSSetArenaLo( db_osarena_lo );
        dol_file.seek(0x800EB36C)
        write_lis(dol_file, 3, sign_extend(db_osarena_lo >> 16, 16))
        write_ori(dol_file, 3, 3, db_osarena_lo & 0xFFFF)

        # In [OSInit]...
        # If ( BootInfo->0x0030 == 0 ) && ( *BI2DebugFlag < 2 )
        # OSSetArenaLo( _osarena_lo );
        dol_file.seek(0x800EB3A4)
        write_lis(dol_file, 3, sign_extend(osarena_lo >> 16, 16))
        write_ori(dol_file, 3, 3, osarena_lo & 0xFFFF)

        # In [__OSThreadInit]...
        # DefaultThread->0x304 = db_stack_end
        dol_file.seek(0x800F18BC)
        write_lis(dol_file, 3, sign_extend(db_stack_end >> 16, 16))
        write_ori(dol_file, 0, 3, db_stack_end & 0xFFFF)

        # In [__OSThreadInit]...
        # DefaultThread->0x308 = _stack_end
        dol_file.seek(0x800F18C4)
        write_lis(dol_file, 3, sign_extend(stack_end >> 16, 16))
        dol_file.seek(0x800F18CC)
        write_ori(dol_file, 0, 3, stack_end & 0xFFFF)

        size = rom_end - self.profile.InjectionAddress
        log_str = f"""{CYAN}✨What's new:
{CYAN}Injected Binary Size: 0x{ORANGE}{size:x}{GREEN} Bytes or {ORANGE}~{size/1024:.2f}{GREEN} KiBs
{CYAN}Injection Address @0x{self.profile.InjectionAddress:x}
{CYAN}New ROM End @ 0x{rom_end:x}
{CYAN}Stack moved to: 0x{stack_addr:x}
{CYAN}Stack End @ 0x{stack_end:x}
{CYAN}New OSArenaLo @ 0x{osarena_lo:x}
{CYAN}Debug Stack Moved To: 0x{db_stack_addr:x}
{CYAN}Debug Stack End @ 0x{db_stack_end:x}
{CYAN}New Debug OSArenaLo @ 0x{db_osarena_lo:x}
"""
        Logger.info(log_str)
