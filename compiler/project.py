from devkit_tools import Project

p = Project("pikmin.dol")
p.set_rom_end(0x803ec840)
p.set_stack_size(0x10000)
p.set_db_stack_size(0x2000)
#p.set_osarena_patcher(patch_osarena_low_plus)

#p.add_file("../source/ctest.c")
p.add_asm_file("../source/test.s")
p.add_asm_file("../source/system.cpp.s")

p.add_linker_file("../symbols.txt")

#p.branchlink(0x801b1328, "DrawP2DPane")
#p.branchlink(0x8005f0a8, "DrawPlugPiki")
p.branch(0x80116080, "newfunc")
p.branch(0x800447dc, "openFile__6SystemFPcbb")

p.build("../main.dol") 
