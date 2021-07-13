import subprocess
import os
import platform
from dol_c_kit import assemble_branch, write_branch

from dolreader.dol import DolFile, write_uint32
from dolreader.section import Section, TextSection, DataSection
from elftools.elf.elffile import ELFFile
from geckolibs.gct import GeckoCodeTable
from geckolibs.geckocode import GeckoCode, GeckoCommand, WriteBranch, Write32, WriteString


class Hook(object):
    def __init__(self, addr):
        self.good = False
        self.addr = addr
        self.data = None
    
    def resolve(self, symbols):
        return
    
    def apply_dol(self, dol):
        if dol.is_mapped(self.addr):
            self.good = True
    
    def write_geckocommand(self, f):
        self.good = True
        
    def dump_info(self):
        return "{:s} {:08X}".format(
               "{:13s}".format("[Hook]       "), self.addr)

class BranchHook(Hook):
    def __init__(self, addr, sym_name, lk_bit):
        Hook.__init__(self, addr)
        self.sym_name = sym_name
        self.lk_bit = lk_bit
    
    def resolve(self, symbols):
        if self.sym_name in symbols:
            self.data = symbols[self.sym_name]['st_value']
    
    def apply_dol(self, dol):
        if self.data and dol.is_mapped(self.addr):
            dol.seek(self.addr)
            dol.write(assemble_branch(self.addr, self.data, LK=self.lk_bit))
            self.good = True
    
    def write_geckocommand(self, f):
        if self.data:
            gecko_command = WriteBranch(self.data, self.addr, isLink = self.lk_bit)
            f.write(gecko_command.as_text() + "\n")
            self.good = True
    
    def dump_info(self):
        return "{:s} {:08X} {:s} {:s}".format(
               "[Branchlink] " if self.lk_bit else "[Branch]     ", self.addr, "-->" if self.good else "-X>", self.sym_name)

class PointerHook(Hook):
    def __init__(self, addr, sym_name):
        Hook.__init__(self, addr)
        self.sym_name = sym_name
    
    def resolve(self, symbols):
        if self.sym_name in symbols:
            self.data = symbols[self.sym_name]['st_value']
    
    def apply_dol(self, dol):
        if self.data and dol.is_mapped(self.addr):
            dol.write_uint32(self.addr, self.data)
            self.good = True
    
    def write_geckocommand(self, f):
        if self.data:
            gecko_command = Write32(self.data, self.addr)
            f.write(gecko_command.as_text() + "\n")
            self.good = True
        
    def dump_info(self):
        return "{:s} {:08X} {:s} {:s}".format(
               "[Pointer]    ", self.addr, "-->" if self.good else "-X>", self.sym_name)

class StringHook(Hook):
    def __init__(self, addr, string, encoding, max_size):
        Hook.__init__(self, addr)
        self.data = string.encode(encoding) + b'\x00'
        if max_size != -1 and len(self.data) > max_size:
            print("Warning: {:s} exceeds {} bytes!".format(string, max_size))
        self.string = string
    
    def resolve(self, symbols):
        return
    
    def apply_dol(self, dol):
        if dol.is_mapped(self.addr):
            dol.seek(self.addr)
            dol.write(self.data)
            self.good = True
    
    def write_geckocommand(self, f):
        gecko_command = WriteString(self.data, self.addr)
        f.write(gecko_command.as_text() + "\n")
        self.good = True
        
    def dump_info(self):
        return "{:s} {:08X} {:s} \"{:s}\"".format(
               "[String]     ", self.addr, "-->" if self.good else "-X>", self.string)

def find_rom_end(dol):
    rom_end = 0x80000000
    for offset, address, size in dol.sections:
        if address + size > rom_end:
            rom_end = address + size
    return rom_end

def try_remove(filepath):
    try:
        os.remove(filepath)
        return True
    except FileNotFoundError:
        return False

SupportedGeckoCodetypes = [
    GeckoCommand.Type.WRITE_8,
    GeckoCommand.Type.WRITE_16,
    GeckoCommand.Type.WRITE_32,
    GeckoCommand.Type.WRITE_STR,
    GeckoCommand.Type.WRITE_SERIAL,
    GeckoCommand.Type.WRITE_BRANCH,
    GeckoCommand.Type.ASM_INSERT,
    GeckoCommand.Type.ASM_INSERT_XOR,
]

class Project(object):
    def __init__(self, base_addr=None, verbose=False):
        self.base_addr = base_addr
        
        # System member variables
        if platform.system() == "Windows":
            self.devkitppc_path = "C:/devkitPro/devkitPPC/bin/"
        else:
            self.devkitppc_path = "/opt/devkitpro/devkitPPC/bin/"
        
        # Compiling member variables
        self.src_dir = ""
        self.obj_dir = ""
        self.project_name = "project"
        self.c_files = []
        self.asm_files = []
        self.obj_files = []
        self.linker_script_files = []
        self.symbols = {}
        self.optimization = "-O1"
        self.c_std = "c99"
        self.verbose = verbose
        
        # Patches member variables
        self.hooks = []
        self.gecko_codetable = GeckoCodeTable(gameName=self.project_name)
        self.gecko_code_metadata = []
        self.osarena_patcher = None
        
        
    def add_c_file(self, filepath):
        self.c_files.append(filepath)
        
    def add_asm_file(self, filepath):
        self.asm_files.append(filepath)
    
    def add_linker_script_file(self, filepath):
        self.linker_script_files.append(filepath)
    
    def add_gecko_txt_file(self, filepath):
        with open(filepath, "r") as f:
            gecko_codetable = GeckoCodeTable.from_text(f)
        for gecko_code in gecko_codetable:
            self.gecko_codetable.add_child(gecko_code)
    
    def add_gecko_gct_file(self, filepath):
        with open(filepath, "rb") as f:
            code_table = GeckoCodeTable.from_bytes(f)
        self.gecko_codetable.append(code_table)
    
    def add_branch(self, addr, funcname, LK=False):
        self.hooks.append(BranchHook(addr, funcname, LK))
    
    def add_branchlink(self, addr, funcname):
        self.add_branch(addr, funcname, LK=True)
    
    def add_pointer(self, addr, funcname):
        self.hooks.append(PointerHook(addr, funcname))
    
    def add_string(self, addr, string, encoding = "ascii", max_size = -1):
        self.hooks.append(StringHook(addr, string, encoding, max_size))
    
    def set_osarena_patcher(self, function):
        self.osarena_patcher = function
    
    def build_dol(self, in_dol_path, out_dol_path):
        with open(in_dol_path, "rb") as f:
            dol = DolFile(f)
        
        if self.base_addr == None:
            self.base_addr = (find_rom_end(dol) + 31) & 0xFFFFFFE0
            print("Base address auto-set from ROM end: {0:X}\n"
                  "Do not rely on this feature if your DOL uses .sbss2\n".format(self.base_addr))
        
        if self.base_addr % 32:
            print("WARNING!  DOL sections must be 32-byte aligned for OSResetSystem to work properly!\n")
        
        data = bytearray()

        if self.__build_project() == True:
            with open(self.obj_dir+self.project_name+".bin", "rb") as f:
                data += f.read()
                while (len(data) % 4) != 0:
                    data += b'\x00'
        
        for gecko_code in self.gecko_codetable:
            status = "ENABLED" if gecko_code.is_enabled() else "DISABLED"
            if gecko_code.is_enabled() == True:
                for gecko_command in gecko_code:
                    if gecko_command.codetype not in SupportedGeckoCodetypes:
                        status = "OMITTED"
            
            print("[GeckoCode]   {:12s} ${}".format(status, gecko_code.name))
            if status == "OMITTED":
                print("Includes unsupported codetypes:")
                for gecko_command in gecko_code:
                    if gecko_command.codetype not in SupportedGeckoCodetypes:
                        print(gecko_command)
            
            vaddress = self.base_addr + len(data)
            geckoblob = bytearray()
            gecko_command_metadata = []
            
            for gecko_command in gecko_code:
                if gecko_command.codetype == GeckoCommand.Type.ASM_INSERT \
                or gecko_command.codetype == GeckoCommand.Type.ASM_INSERT_XOR:
                    if status == "UNUSED" \
                    or status == "OMITTED":
                        gecko_command_metadata.append((0, len(gecko_command.value), status, gecko_command))
                    else:
                        dol.seek(gecko_command._address | 0x80000000)
                        write_branch(dol, vaddress + len(geckoblob))
                        gecko_command_metadata.append((vaddress + len(geckoblob), len(gecko_command.value), status, gecko_command))
                        geckoblob += gecko_command.value[:-4]
                        geckoblob += assemble_branch(vaddress + len(geckoblob), gecko_command._address + 4 | 0x80000000)
            data += geckoblob
            if gecko_command_metadata:
                self.gecko_code_metadata.append((vaddress, len(geckoblob), status, gecko_code, gecko_command_metadata))
        self.gecko_codetable.apply(dol)
        
        for hook in self.hooks:
            hook.resolve(self.symbols)
            hook.apply_dol(dol)
            if self.verbose:
                print(hook.dump_info())
        
        new_section: Section
        if len(dol.textSections) <= DolFile.MaxTextSections:
            new_section = TextSection(self.base_addr, data)
        elif len(dol.dataSections) <= DolFile.MaxDataSections:
            new_section = DataSection(self.base_addr, data)
        else:
            raise RuntimeError("DOL is full!  Cannot allocate any new sections.")
        dol.append_section(new_section)
        
        self.osarena_patcher(dol, self.base_addr + len(data))
        
        with open(out_dol_path, "wb") as f:
            dol.save(f)
    
    def build_gecko(self, gecko_path):
        with open(gecko_path, "w") as f:
            if self.__build_project() == True:
                with open(self.obj_dir+self.project_name+".bin", "rb") as bin:
                    data = bin.read()
            
            f.write("[Gecko]\n")
            # Copy existing Gecko Codes
            for gecko_code in self.gecko_codetable:
                f.write("${}\n".format(gecko_code.name))
                f.write("{}\n".format(gecko_code.as_text()))
                print("[GeckoCode]   {:12s} ${}".format("ENABLED" if gecko_code.is_enabled() else "DISABLED", gecko_code.name))
            # Create Program Data megacode
            if data:
                gecko_command = WriteString(data, self.base_addr)
                f.write("$Program Data\n")
                f.write(gecko_command.as_text() + "\n")
            # Create Hooks
            f.write("$Hooks\n")
            for hook in self.hooks:
                hook.resolve(self.symbols)
                hook.write_geckocommand(f)
                if self.verbose:
                    print(hook.dump_info())
            # Say they are all enabled
            f.write("[Gecko_Enabled]\n")
            for gecko_code in self.gecko_codetable:
                f.write("${}\n".format(gecko_code.name))
            f.write("$Program Data\n")
            f.write("$Hooks\n")
    
    def save_map(self, map_path):
        with open(map_path, "w") as map:
            with open(self.obj_dir+self.project_name+".o", 'rb') as f:
                elf = ELFFile(f)
                symtab = elf.get_section_by_name(".symtab")
                new_symbols = []
                
                for iter in symtab.iter_symbols():
                    # Filter out worthless symbols, as well as STT_SECTION and STT_FILE type symbols.
                    if iter.entry['st_info']['bind'] == "STB_LOCAL":
                        continue
                    # Symbols defined by the linker script have no section index, and are instead absolute.
                    # Symbols we already have aren't needed in the new symbol map, so they are filtered out.
                    if (iter.entry['st_shndx'] == 'SHN_ABS') or (iter.entry['st_shndx'] == 'SHN_UNDEF'):
                        continue
                    new_symbols.append(iter)
                new_symbols.sort(key = lambda i: i.entry['st_value'])
                
                curr_section_name = ""
                for iter in new_symbols:
                    parent_section = elf.get_section(iter.entry['st_shndx'])
                    if curr_section_name != parent_section.name:
                        curr_section_name = parent_section.name
                        map.write(
                            "\n"
                            "{} section layout\n"
                            "  Starting        Virtual\n"
                            "  address  Size   address\n"
                            "  -----------------------\n".format(curr_section_name))
                    map.write("  {:08X} {:06X} {:08X}  0 {}\n".format(
                        iter.entry['st_value'] - self.base_addr, iter.entry['st_size'], iter.entry['st_value'], iter.name))
                # Record Geckoblobs from patched-in C2/F2 codetypes.  I really wanted to name this section .gecko in the
                # symbol map, but only .init and .text section headers tell Dolphin to color the symbols by index.
                if self.gecko_code_metadata:
                    map.write(
                        "\n"
                        ".text section layout\n"
                        "  Starting        Virtual\n"
                        "  address  Size   address\n"
                        "  -----------------------\n")
                    for code_vaddr, code_size, code_status, gecko_code, gecko_command_metadata in self.gecko_code_metadata:
                        i = 0
                        for cmd_vaddr, cmd_size, cmd_status, gecko_command in gecko_command_metadata:
                            if gecko_command.codetype == GeckoCommand.Type.ASM_INSERT \
                            or gecko_command.codetype == GeckoCommand.Type.ASM_INSERT_XOR:
                                if cmd_status == "OMITTED":
                                    map.write("  UNUSED   {:06X} ........ {}${}\n".format(
                                        cmd_size, gecko_code.name, i))
                                else:
                                    map.write("  {:08X} {:06X} {:08X}  0 {}${}\n".format(
                                        cmd_vaddr - self.base_addr, cmd_size, cmd_vaddr, gecko_code.name, i))
                            i += 1
                # For whatever reason, the final valid symbol loaded by Dolphin ( <= 5.0-13603 ) gets messed up
                # and loses its size.  To compensate, an dummy symbol is thrown into the map at a dubious address.
                map.write(
                    "\n"
                    ".dummy section layout\n"
                    "  Starting        Virtual\n"
                    "  address  Size   address\n"
                    "  -----------------------\n"
                    "  00000000 000000 81200000  0 Workaround for Dolphin's bad symbol map loader\n")
    
    def cleanup(self):
        for filename in self.obj_files:
            try_remove(self.obj_dir+filename)
        try_remove(self.obj_dir+self.project_name+".o")
        try_remove(self.obj_dir+self.project_name+".bin")
        try_remove(self.obj_dir+self.project_name+".map")
        self.obj_files.clear()
        self.symbols.clear()
        self.gecko_code_metadata.clear()
    
    def __compile(self, infile):
        args = [self.devkitppc_path+"powerpc-eabi-gcc"]
        args.append(self.src_dir+infile)
        args.append("-c")
        args.extend(("-o", self.obj_dir+infile+".o"))
        args.append(self.optimization)
        args.append("-std="+self.c_std)
        args.append("-w")
        args.extend(("-I", self.src_dir))
        args.append("-fno-asynchronous-unwind-tables")
        if self.verbose:
            print(args)
        subprocess.call(args)
        self.obj_files.append(infile+".o")
        return True
    
    def __assemble(self, infile):
        args = [self.devkitppc_path+"powerpc-eabi-as"]
        args.append(self.src_dir+infile)
        args.extend(("-o", self.obj_dir+infile+".o"))
        args.append("-w")
        args.extend(("-I", self.src_dir))
        if self.verbose:
            print(args)
        subprocess.call(args)
        self.obj_files.append(infile+".o")
        return True
    
    def __link_project(self):
        if self.base_addr == None:
            raise RuntimeError("Base address not set!  New code cannot be linked.")
        
        args = [self.devkitppc_path+"powerpc-eabi-ld"]
        # The symbol "." represents the location counter.  By setting it this way,
        # we don't need a linker script to set the base address of our new code.
        args.extend(("--defsym", ".="+hex(self.base_addr)))
        
        for file in self.linker_script_files:
            args.extend(("-T", file))
        
        args.extend(("-o", self.obj_dir+self.project_name+".o"))
        
        for filename in self.obj_files:
            args.append(self.obj_dir+filename)
        
        args.extend(("-Map", self.obj_dir+self.project_name+".map"))
        if self.verbose:
            print(args)
        subprocess.call(args)
        return True
    
    def __process_project(self):
        with open(self.obj_dir+self.project_name+".o", 'rb') as f:
            elf = ELFFile(f)
            with open(self.obj_dir+self.project_name+".bin", "wb") as bin:
                for iter in elf.iter_sections():
                    # Filter out sections without SHF_ALLOC attribute
                    if iter.header["sh_flags"] & 0x2:
                        bin.seek(iter.header["sh_addr"] - self.base_addr)
                        bin.write(iter.data())
            
            symtab = elf.get_section_by_name(".symtab")
            for iter in symtab.iter_symbols():
                # Filter out worthless symbols, as well as STT_SECTION and STT_FILE type symbols.
                if iter.entry['st_info']['bind'] == "STB_LOCAL":
                    continue
                self.symbols[iter.name] = iter.entry
        return True
    
    def __build_project(self):
        os.makedirs(self.src_dir, exist_ok=True)
        os.makedirs(self.obj_dir, exist_ok=True)
        is_built = False
        is_linked = False
        is_processed = False
        
        for filepath in self.c_files:
            is_built |= self.__compile(filepath)
        
        for filepath in self.asm_files:
            is_built |= self.__assemble(filepath)
        
        if is_built == True:
            is_linked |= self.__link_project()
        if is_linked == True:
            is_processed |= self.__process_project()
        
        return is_processed
