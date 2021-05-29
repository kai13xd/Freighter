import subprocess 
import os 
from itertools import chain
from dolreader import DolFile, SectionCountFull
from doltools import branchlink, branch, apply_gecko, write_lis, write_ori

GCCPATH = "C:\\devkitPro\\devkitPPC\\bin\\powerpc-eabi-gcc.exe"
LDPATH = "C:\\devkitPro\\devkitPPC\\bin\\powerpc-eabi-ld.exe"
OBJDUMPPATH = "C:\\devkitPro\\devkitPPC\\bin\\powerpc-eabi-objdump.exe"
OBJCOPYPATH = "C:\\devkitPro\\devkitPPC\\bin\\powerpc-eabi-objcopy.exe"


def compile(inpath, outpath, mode, optimize="-O1", std="c99", warning="-w"):
    assert mode in ("-S", "-c") # turn into asm or compile 
    args = [GCCPATH, inpath, mode, "-o", outpath, optimize, "-std="+std, warning, "-I", "../headers/"]
    print(args)
    subprocess.call(args)
    
    
def link(infiles, outfile, outmap, linker_files):
    arg = [LDPATH]
    arg.append("-Os")
    for file in linker_files:
        arg.append("-T")
        arg.append(file)
    
    arg.extend(("-o", outfile))
    
    for file in infiles:
        arg.append(file)
    
    arg.extend(("-Map", outmap))
    print(arg)
    subprocess.call(arg)
    
    
def objdump(*args):
    arg = [OBJDUMPPATH]
    arg.extend(args)
    print(arg)
    subprocess.call(arg)


def objcopy(*args, attrs = []):
    arg = [OBJCOPYPATH]
    arg.extend(args)
    for attr in attrs:
        arg.extend(("-R", attr))
    print(arg)
    subprocess.call(arg)
    
    
def read_map(mappath):
    result = {}
    with open(mappath, "r") as f:
		#read until section header is found
        for line in f:
            if line.startswith(".text"):
                break 
        #assert that section header part 2 is found
        next = f.readline()
        assert next.startswith(" *(.text)")
        
        
        while 1:
            next = f.readline()
            #stop when end of section is encountered
            if next.strip() == "":
                break
            #skip symbol closures
            if next.startswith(" .text"):
                continue
            
            vals = next.strip().split(" ")
            
            for i in range(vals.count("")):
                vals.remove("")
            
            addr = vals[0]
            func = vals[1]
            
            result[func] = int(addr, 16) 
    
    return result 


class Project(object):
    def __init__(self, dolpath, address=None, offset=None):
        # Check to see if the DOL has any spare sections
        with open(dolpath,"rb") as f:
            tmp = DolFile(f)
        
        try:
            _offset, addr, size = tmp.allocate_text_section(4, address)
        except SectionCountFull as e:
            print(e)
            try:
                _offset, addr, size = tmp.allocate_data_section(4, address)
            except SectionCountFull as e:
                print(e)
                raise RuntimeError("Dol is full! Cannot allocate any new sections")
        
        self.set_stack_size(0x10000)
        self.set_db_stack_size(0x2000)
        
        del tmp
        
        # Open the DOL for realsies
        with open(dolpath,"rb") as f:
            self.dol = DolFile(f)
        
        self.c_files = []
        self.asm_files = []
        
        self.linker_files = []
        
        self.branchlinks = []
        self.branches = []
        
        self.osarena_patcher = None 
        
        
    def add_file(self, filepath):
        self.c_files.append(filepath)
        
    def add_asm_file(self, filepath):
        self.asm_files.append(filepath)
    
    def add_linker_file(self, filepath):
        self.linker_files.append(filepath)
    
    def branchlink(self, addr, funcname):
        self.branchlinks.append((addr, funcname))
    
    def branch(self, addr, funcname):
        self.branches.append((addr, funcname))
    
    def set_rom_end(self, addr):
        self._rom_end = addr
    
    def set_stack_size(self, size):
        self._stack_size = size
    
    def set_db_stack_size(self, size):
        self._db_stack_size = size
    
    def patch_osarena_low(self, new_rom_end):
        new_stack_addr = new_rom_end + self._stack_size
        new_stack_addr = (new_stack_addr + 31) & 0xffffffe0
        new_db_stack_addr = new_stack_addr + self._db_stack_size
        new_db_stack_addr = (new_db_stack_addr + 31) & 0xffffffe0
        
        # In [__init_registers]...
        self.dol.seek(0x800031f0)
        write_lis( self.dol, 1,    new_stack_addr >> 16, signed=False ) 
        write_ori( self.dol, 1, 1, new_stack_addr & 0xFFFF )
        
        # In [OSInit]...
        # OSSetArenaLo( _db_stack_addr );
        self.dol.seek(0x801f5a4c)
        write_lis( self.dol, 3,    new_db_stack_addr >> 16, signed=False ) 
        write_ori( self.dol, 3, 3, new_db_stack_addr & 0xFFFF )
    	
        # In [OSInit]...
        # If ( BootInfo->0x0030 == 0 ) && ( *BI2DebugFlag < 2 )
        # OSSetArenaLo( _stack_addr );
        self.dol.seek(0x801f5a84)
        write_lis( self.dol, 3,    new_stack_addr >> 16, signed=False )
        write_ori( self.dol, 3, 3, new_stack_addr & 0xFFFF )
        
        print("New ROM end:", hex(new_rom_end))
        
    def apply_gecko(self, geckopath):
        with open(geckopath, "r") as f:
            apply_gecko(self.dol, f)
    
    def build(self, newdolpath, address=None, offset=None):
        os.makedirs("tmp", exist_ok=True)
        
        for fpath in self.c_files:
            compile(fpath, fpath+".s", mode="-S")
            compile(fpath, fpath+".o", mode="-c")
        
        for fpath in self.asm_files:
            compile(fpath, fpath+".o", mode="-c")
        
        inputobjects = [fpath+".o" for fpath in chain(self.c_files, self.asm_files)]
        with open("tmplink", "w") as f:
            f.write("SECTIONS\n"
                    "{{\n"
                    "    . = 0x{0:x};\n"
                    "    .text : \n"
                    "    {{\n"
                    "        *(.text)\n"
                    "    }}\n"
                    "	.rodata :\n"
                    "	{{\n"
                    "		*(.rodata*)\n"
                    "	}}\n"
                    "	.data :\n"
                    "	{{\n"
                    "		*(.data)\n"
                    "	}}\n"
                    "	. += 0x08;\n"
                    "	.sdata :\n"
                    "	{{\n"
                    "		*(.sdata)\n"
                    "	}}\n"
                    "}}\n".format(self._rom_end))
        linker_files = ["tmplink"]
        for fpath in self.linker_files:
            linker_files.append(fpath)
        link(   [fpath+".o" for fpath in chain(self.c_files, self.asm_files)], 
                "project.o", "project.map", linker_files)
        
        objdump("project.o", "--full-content")
        
        objcopy("project.o", "project.bin", "-O", "binary", "-g", "-S", attrs=[".eh_frame", ".comment", ".gnu.attributes"])
        
        with open("project.bin", "rb") as f:
            data = f.read()
        
        functions = read_map("project.map")
        
        offset, sectionaddr, size = self.dol.allocate_text_section(len(data), addr=self._rom_end)
        
        self.dol.seek(sectionaddr)
        self.dol.write(data)
        
        print(functions)
        for addr, func in self.branches:
            if func not in functions:
                print("Function not found in symbol map: {0}. Skipping...".format(func))
                continue
                #raise RuntimeError("Function not found in symbol map: {0}".format(func))
            
            branch(self.dol, addr, functions[func])
        
        for addr, func in self.branchlinks:
            if func not in functions:
                print("Function not found in symbol map: {0}. Skipping...".format(func))
                continue
                #raise RuntimeError("Function not found in symbol map: {0}".format(func))
            
            branchlink(self.dol, addr, functions[func])
        
        self.patch_osarena_low(sectionaddr+size)
        
        with open(newdolpath, "wb") as f:
            self.dol.save(f)
        
if __name__ == "__main__":
    compile("main.c", "main.s", mode="-S")
    compile("main.c", "main.o", mode="-c")
