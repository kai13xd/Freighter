import subprocess 
import os 
from itertools import chain
from gc_c_kit import DolFile
from gc_c_kit import branchlink, branch, apply_gecko

DEVKITPPC = "C:/devkitPro/devkitPPC/bin/"
GCC = "powerpc-eabi-gcc.exe"
AS = "powerpc-eabi-as.exe"
LD = "powerpc-eabi-ld.exe"
OBJDUMP = "powerpc-eabi-objdump.exe"
OBJCOPY = "powerpc-eabi-objcopy.exe"

class Project(object):
    def __init__(self, dolpath, rom_end_addr=None):
        # DOL member variables
        with open(dolpath, "rb") as f:
            self.dol = DolFile(f)
            # Check to see if the DOL has any spare sections
            if self.dol.is_text_section_available() == False and self.dol.is_data_section_available() == False:
                raise RuntimeError("Dol is full! Cannot allocate any new sections")
        self.stack_size = 0x10000
        self.db_stack_size = 0x2000
        self.rom_end = rom_end_addr
        
        # Compiling member variables
        self.src_dir = "."
        self.obj_dir = "."
        self.project_name = "project"
        self.c_files = []
        self.asm_files = []
        self.obj_files = []
        self.linker_script_files = []
        self.symbols = {}
        self.optimization = "-O1"
        self.c_std = "c99"
        self.verbose = False
        
        # Patches member variables
        self.branchlinks = []
        self.branches = []
        self.osarena_patcher = None
        
        
    def add_file(self, filepath):
        self.c_files.append(filepath)
        
    def add_asm_file(self, filepath):
        self.asm_files.append(filepath)
    
    def add_linker_file(self, filepath):
        self.linker_script_files.append(filepath)
    
    def branchlink(self, addr, funcname):
        self.branchlinks.append((addr, funcname))
    
    def branch(self, addr, funcname):
        self.branches.append((addr, funcname))
    
    def set_osarena_patcher(self, function):
        self.osarena_patcher = function
        
    def apply_gecko(self, geckopath):
        with open(geckopath, "r") as f:
            apply_gecko(self.dol, f)
    
    def compile(self, infile):
        args = [DEVKITPPC+GCC]
        args.append(self.src_dir+"/"+infile)
        args.append("-c")
        args.extend(("-o", self.obj_dir+"/"+infile+".o"))
        args.append(self.optimization)
        args.append("-std="+self.c_std)
        if self.verbose == True:
            args.append("-w")
        args.extend(("-I", self.src_dir))
        print(args)
        subprocess.call(args)
        self.obj_files.append(infile+".o")
    
    def assemble(self, infile):
        args = [DEVKITPPC+AS]
        args.append(self.src_dir+"/"+infile)
        args.extend(("-o", self.obj_dir+"/"+infile+".o"))
        if self.verbose == True:
            args.append("-w")
        args.extend(("-I", self.src_dir))
        print(args)
        subprocess.call(args)
        self.obj_files.append(infile+".o")
    
    def link(self):
        args = [DEVKITPPC+LD]
        args.append("-Os")
        # The symbol "." represents the processor counter.  By setting it this way,
        # we don't need a Linker Script to set the base address of our new code.
        args.extend(("--defsym", ".="+hex(self.rom_end)))
        
        for file in self.linker_script_files:
            args.extend(("-T", file))
        
        args.extend(("-o", self.obj_dir+"/"+self.project_name+".o"))
        
        for filename in self.obj_files:
            args.append(self.obj_dir+"/"+filename)
        
        args.extend(("-Map", self.obj_dir+"/"+self.project_name+".map"))
        print(args)
        subprocess.call(args)
    
    def objdump(self):
        args = [DEVKITPPC+OBJDUMP, self.obj_dir+"/"+self.project_name+".o", "--full-content"]
        print(args)
        subprocess.call(args)
    
    def objcopy(self):
        arg = [DEVKITPPC+OBJCOPY]
        arg.append(self.obj_dir+"/"+self.project_name+".o")
        arg.append(self.obj_dir+"/"+self.project_name+".bin")
        arg.extend(("-O", "binary"))
        arg.append("-g")
        arg.append("-S")
        arg.extend(("-R", ".eh_frame"))
        arg.extend(("-R", ".comment"))
        arg.extend(("-R", ".gnu.attributes"))
        print(arg)
        subprocess.call(arg)
    
    def read_map(self):
        with open(self.obj_dir+"/"+self.project_name+".map", "r") as f:
            for next in f:
                if len(next) < 50:
                    continue
                if next[34:50] != "                ":
                    continue
                
                vals = next.strip().split(" ")
                for i in range(vals.count("")):
                    vals.remove("")
                
                addr = vals[0]
                func = vals[1]
                
                self.symbols[func] = int(addr, 16)
    
    def build(self, newdolpath):
        os.makedirs(self.src_dir, exist_ok=True)
        os.makedirs(self.obj_dir, exist_ok=True)
        
        for filepath in self.c_files:
            self.compile(filepath)
        
        for filepath in self.asm_files:
            self.assemble(filepath)

        self.link()
        self.read_map()
        self.objdump()
        self.objcopy()
        
        with open(self.obj_dir+"/"+self.project_name+".bin", "rb") as f:
            data = f.read()
        
        offset, sectionaddr, size = self.dol.allocate_text_section(len(data), addr=self.rom_end)
        
        self.dol.seek(sectionaddr)
        self.dol.write(data)
        
        print(self.symbols)
        for addr, func in self.branches:
            if func not in self.symbols:
                print("Function not found in symbol map: {0}. Skipping...".format(func))
                continue
                #raise RuntimeError("Function not found in symbol map: {0}".format(func))
            
            branch(self.dol, addr, self.symbols[func])
        
        for addr, func in self.branchlinks:
            if func not in self.symbols:
                print("Function not found in symbol map: {0}. Skipping...".format(func))
                continue
                #raise RuntimeError("Function not found in symbol map: {0}".format(func))
            
            branchlink(self.dol, addr, self.symbols[func])
        
        self.osarena_patcher(self)
        
        with open(newdolpath, "wb") as f:
            self.dol.save(f)
