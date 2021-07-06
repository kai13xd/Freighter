import subprocess
import os
import platform
import struct
from dol_c_kit import DolFile, write_uint32
from dol_c_kit import assemble_branch, write_branch, apply_gecko
from dol_c_kit import gecko_04write, gecko_C6write

from elftools.elf.elffile import ELFFile

class Hook(object):
    def __init__(self, addr, sym_name):
        self.good = False
        self.kind = "Hook"
        self.addr = addr
        self.sym_name = sym_name

class BranchHook(Hook):
    def __init__(self, addr, sym_name, lk_bit):
        Hook.__init__(self, addr, sym_name)
        self.kind = "Branchlink" if lk_bit else "Branch"
        self.lk_bit = lk_bit

class PointerHook(Hook):
    def __init__(self, addr, sym_name):
        Hook.__init__(self, addr, sym_name)
        self.kind = "Pointer"

class Project(object):
    def __init__(self, base_addr=None, verbose=False):
        self.is_built = False
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
        self.gecko_txt_files = []
        self.gecko_gct_files = []
        self.osarena_patcher = None
        
        
    def add_c_file(self, filepath):
        self.c_files.append(filepath)
        
    def add_asm_file(self, filepath):
        self.asm_files.append(filepath)
    
    def add_linker_script_file(self, filepath):
        self.linker_script_files.append(filepath)
    
    def add_gecko_txt_file(self, filepath):
        self.gecko_txt_files.append(filepath)
    
#    def add_gecko_gct_file(self, filepath):
#        self.gecko_gct_files.append(filepath)
    
    def add_branch(self, addr, funcname, LK=False):
        self.hooks.append(BranchHook(addr, funcname, LK))
    
    def add_branchlink(self, addr, funcname):
        self.add_branch(addr, funcname, LK=True)
    
    def add_pointer(self, addr, funcname):
        self.hooks.append(PointerHook(addr, funcname))
    
    def set_osarena_patcher(self, function):
        self.osarena_patcher = function
    
    def build_dol(self, in_dol_path, out_dol_path):
        with open(in_dol_path, "rb") as f:
            dol = DolFile(f)
        
        if self.base_addr == None:
            self.base_addr = (dol.find_rom_end() + 31) & 0xFFFFFFE0
            print("Base address auto-set from ROM end: {0:X}\n"
                  "Do not rely on this feature if your DOL uses .sbss2\n".format(self.base_addr))
        
        if self.base_addr % 32:
            print("WARNING!  DOL sections must be 32-byte aligned for OSResetSystem to work properly!\n")
        
        self.__build_project()
        
        if self.is_built == True:
            with open(self.obj_dir+self.project_name+".bin", "rb") as f:
                data = f.read()
            
            if dol.is_text_section_available():
                offset, sectionaddr, size = dol.allocate_text_section(len(data), addr=self.base_addr)
            elif dol.is_data_section_available():
                offset, sectionaddr, size = dol.allocate_data_section(len(data), addr=self.base_addr)
            else:
                raise RuntimeError("DOL is full!  Cannot allocate any new sections.")
            
            dol.seek(sectionaddr)
            dol.write(data)
            
            for hook in self.hooks:
                if hook.sym_name in self.symbols:
                    hook.good = True
                    dol.seek(hook.addr)
                    if type(hook) == BranchHook:
                        write_branch(dol, self.symbols[hook.sym_name]['st_value'], LK=hook.lk_bit)
                    elif type(hook) == PointerHook:
                        write_uint32(dol, self.symbols[hook.sym_name]['st_value'])
                if self.verbose:
                    print("{:s} {:08X} {:s} {:s}".format(
                        "{:13s}".format("["+hook.kind+"]"), hook.addr, "-->" if hook.good else "-X>", hook.sym_name))
            
            self.osarena_patcher(dol, self.base_addr + len(data))
        
        self.__apply_gecko(dol)
        
        with open(out_dol_path, "wb") as f:
            dol.save(f)
    
    def build_gecko(self, gecko_path):
        self.__build_project()
        
        with open(gecko_path, "w") as f:
            if self.is_built == True:
                with open(self.obj_dir+self.project_name+".bin", "rb") as bin:
                    data = bin.read()
                # Pad new data to next multiple of 8 for the Gecko Codehandler
                len_real = len(data)
                while (len(data) % 8) != 0:
                    data += b'\x00'
            
                f.write("$Program Code\n")
                f.write("{:08X} {:08X}\n".format((self.base_addr & 0x01FFFFFC) | 0x06000000, len_real))
                for i in range(0, len(data), 8):
                    word1 = struct.unpack_from(">I", data, i  )[0]
                    word2 = struct.unpack_from(">I", data, i+4)[0]
                    f.write("{:08X} {:08X}\n".format(word1, word2))
            
            f.write("$Hooks\n")
            for hook in self.hooks:
                if hook.sym_name in self.symbols:
                    hook.good = True
                    if type(hook) == BranchHook:
                        f.write(gecko_C6write(hook.addr, self.symbols[hook.sym_name]['st_value'], hook.lk_bit) + "\n")
                    elif type(hook) == PointerHook:
                        f.write(gecko_04write(hook.addr, self.symbols[hook.sym_name]['st_value']) + "\n")
                if self.verbose:
                    print("{:s} {:08X} {:s} {:s}".format(
                        "{:13s}".format("["+hook.kind+"]"), hook.addr, "-->" if hook.good else "-X>", hook.sym_name))
    
    def save_map(self, map_path, write_hooks=False):
        with open(map_path, "w") as map:
            if write_hooks == True:
                for hook in self.hooks:
                    map.write("{:s} {:08X} {:s} {:s}\n".format(
                        "{:13s}".format("["+hook.kind+"]"), hook.addr, "-->" if hook.good else "-X>", hook.sym_name))
            
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
    
    def cleanup(self):
        if self.is_built == True:
            for filename in self.obj_files:
                os.remove(self.obj_dir+filename)
            os.remove(self.obj_dir+self.project_name+".o")
            os.remove(self.obj_dir+self.project_name+".bin")
            os.remove(self.obj_dir+self.project_name+".map")
        self.obj_files.clear()
        self.symbols.clear()
        self.is_built = False
    
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
    
    def __build_project(self):
        os.makedirs(self.src_dir, exist_ok=True)
        os.makedirs(self.obj_dir, exist_ok=True)
        
        for filepath in self.c_files:
            self.is_built = True
            self.__compile(filepath)
        
        for filepath in self.asm_files:
            self.is_built = True
            self.__assemble(filepath)
        
        if self.is_built == True:
            self.__link_project()
            self.__process_project()
    
    def __apply_gecko(self, dol):
        for file in self.gecko_txt_files:
            with open(file, "r") as f:
                apply_gecko(dol, f)
#        for file in self.gecko_gct_files:
#            with open(file, "r") as f:
#                something to process GCT files here
