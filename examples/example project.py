from gc_c_kit import Project, write_lis, write_ori

def patch_osarena_low(p):
	new_stack_addr = p.rom_end + p.stack_size
	new_stack_addr = (new_stack_addr + 31) & 0xffffffe0
	new_db_stack_addr = new_stack_addr + p.db_stack_size
	new_db_stack_addr = (new_db_stack_addr + 31) & 0xffffffe0
	
	# In [__init_registers]...
	p.dol.seek(0x800031f0)
	write_lis( p.dol, 1,    new_stack_addr >> 16, signed=False ) 
	write_ori( p.dol, 1, 1, new_stack_addr & 0xFFFF )
	
	# In [OSInit]...
	# OSSetArenaLo( _db_stack_addr );
	p.dol.seek(0x801f5a4c)
	write_lis( p.dol, 3,    new_db_stack_addr >> 16, signed=False ) 
	write_ori( p.dol, 3, 3, new_db_stack_addr & 0xFFFF )
	
	# In [OSInit]...
	# If ( BootInfo->0x0030 == 0 ) && ( *BI2DebugFlag < 2 )
	# OSSetArenaLo( _stack_addr );
	p.dol.seek(0x801f5a84)
	write_lis( p.dol, 3,    new_stack_addr >> 16, signed=False )
	write_ori( p.dol, 3, 3, new_stack_addr & 0xFFFF )

p = Project("gcm/sys/main.dol", 0x803ec840)
p.set_osarena_patcher(patch_osarena_low)

p.src_dir = "src"
p.obj_dir = "obj"
p.stack_size = 0x10000
p.db_stack_size = 0x2000

p.add_asm_file("test.s")
p.add_asm_file("system.cpp.s")

p.add_linker_file("symbols.txt")

p.branch(0x80116080, "newfunc")
p.branch(0x800447dc, "openFile__6SystemFPcbb")

p.build("newmain.dol") 