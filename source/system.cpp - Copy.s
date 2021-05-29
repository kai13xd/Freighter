.include "../source/defines.inc"

.macro lwz_bss rD, rBSS, target_addr
	lwz          \rD, \target_addr - ...bss.0 (\rBSS)
.endm
.macro lhz_bss rD, rBSS, target_addr
	lhz          \rD, \target_addr - ...bss.0 (\rBSS)
.endm
.macro lbz_bss rD, rBSS, target_addr
	lbz          \rD, \target_addr - ...bss.0 (\rBSS)
.endm

.macro stw_bss rS, rBSS, target_addr
	stw          \rS, \target_addr - ...bss.0 (\rBSS)
.endm
.macro sth_bss rS, rBSS, target_addr
	sth          \rS, \target_addr - ...bss.0 (\rBSS)
.endm
.macro stb_bss rS, rBSS, target_addr
	stb          \rS, \target_addr - ...bss.0 (\rBSS)
.endm

.macro li_bss rD, rBSS, SIMM
	addi         \rD, \rBSS, \SIMM - ...bss.0
.endm

#================================================================================
.section .init
#================================================================================

#================================================================================
.section extab
#================================================================================


#================================================================================
.section extabindex
#================================================================================


#================================================================================
.section .text
#================================================================================
.global openFile__6SystemFPcbb
openFile__6SystemFPcbb:
	# BufferedInputStream* System::OpenFile(char* path, bool is_datadir, bool do_print)
	# iArg0 (r3) = this
	# iArg1 (r4) = path
	# iArg2 (r5) = is_datadir
	# iArg3 (r6) = do_print

	# Stack Frame: 
	# 0x0000 - 0x0003   Old SP
	# 0x0004 - 0x0007   LR Reserved
	# 0x0008 - 0x001B   ???
	# 0x001C - 0x011B   char full_path[256]
	# 0x011C - 0x0123   ???
	# 0x0124 - 0x0127   r27
	# 0x0128 - 0x012B   r28
	# 0x012B - 0x012F   r29
	# 0x0130 - 0x0133   r30
	# 0x0134 - 0x0137   r31
	.set __sfsize,          0x0138
	.set __sf__old_sp,      0x0000
	.set __sf__lr_reserved, 0x0004
	.set __sf__full_path,   0x001C
	.set __sf__stmw_addr,   0x0124

	# [line 0000] sprintf( full_path, "%s", is_datadir ? this->m_0x004c : "" );
	# [line 0001] sprintf( full_path, "%s%s%s", full_path, is_datadir ? this->0x0050 : "", path );
	# [         ] 
	# [line 0002] if ( is_datadir && (this->0x0200.getChildCount() != 0) || (this->0x0214.getChildCount() != 0) {
	# [line 0003]   curr_corenode = this->0x0210;
	# [line 0004]   while ( curr_corenode != nullptr ) {
	# [line 0005]     if ( strcmp( curr_corenode->0x0004, path ) == 0 ) {
	# [line 0006]       aramStream->0x0000 = path;
    # [         ]       aramStream->0x0010 = curr_corenode->0x0014;
	# [         ]       aramStream->0x0008 = curr_corenode->0x0018;
	# [         ]       aramStream->0x000C = 0;
	# [line 0007]       return new BufferedInputStream( aramStream, DVDStream::readBuffer, dvdBufferedStream->0x001C );
	# [         ]     }
	# [line 0008]     curr_corenode = curr_corenode->0x000C;
	# [         ]   }
	# [line 0009]   curr_corenode = this->0x0224;
	# [line 0010]   while ( curr_corenode != nullptr ) {
	# [line 0011]     if ( strcmp( curr_corenode->0x0004, path ) == 0 ) {
	# [line 0012]       aramStream->0x0000 = path;
    # [         ]       aramStream->0x0010 = curr_corenode->0x0014;
	# [         ]       aramStream->0x0008 = curr_corenode->0x0018;
	# [         ]       aramStream->0x000C = 0;
	# [line 0013]       return new BufferedInputStream( aramStream, DVDStream::readBuffer, dvdStream->0x0050 );
	# [         ]     }
	# [line 0014]     curr_corenode = curr_corenode->0x000C;
	# [         ]   }
	# [         ] }
	# [line 0015] this->0x023C++;
	# [line 0016] dvdStream->0x0000 = full_path;
	# [         ] unk_var2 = dvdStream->0x0008;
	# [         ] dvdStream->0x004C = !DVDOpen( full_path, unk_var2 );
	# [line 0017] dvdStream->0x0044 = 0;
	# [line 0018] dvdStream->0x003C = dvdStream->0x003C;
	# [line 0019] sprintf( lastName, dvdStream->0x0000 );
	# [line 0020] DVDStream::numOpen++
	# [line 0021] is_dvd_open = dvdStream->0x004C;
	# [         ] if ( is_dvd_open != 0 ) {
	# [line 0022]   DVDStream::numOpen--
	# [line 0023]   if ( is_dvd_open == 0 ) {
	# [line 0024]     DVDClose( unk_var2 );
	# [line 0025]   return nullptr;
	# [         ] }
	# [line 0026] gpr6 = gsys->0x001C;
	# [line 0027] gsys->0x001C = 1;
	# [line 0028] gsys->0x001C = gpr6;
	# [line 0029] dvdStream->0x0000 = path
	# [line 0030] BufferedInputStream.init( dvdStream , DVDStream::readBuffer, this->0x025C);
	# [line 0031] return dvdBufferedStream;

#---Prologue---------------------------------------------------------------------
	mflr         r0
	stw          r0, 0x0004 (sp)
	stwu         sp, -__sfsize (sp)
	stmw         r27, __sf__stmw_addr (sp)
	
	.set block,      iVar0
	.set path,       iVar1
	.set this,       iVar2
	.set do_print,   iVar3   # Optimized away in original function
	.set is_datadir, iVar4
#	mr           do_print,      iArg3
	mr           is_datadir,    iArg2
	mr           path,      iArg1
	mr           this,          iArg0

	lis          block,        ...bss.0@h
	ori          block, block, ...bss.0@l
#---[line 0000]------------------------------------------------------------------
100$:
	cmpwi        is_datadir, 0
	beq-         101$
	lwz          iArg2, 0x004C (this)
	b            102$
101$:
	li_sda       iArg2, __noname__686
102$:          
	li_sda       iArg1, __noname__687
	addi         iArg0, sp, __sf__full_path
	crclr        6
	bl           sprintf
#---[line 0001]------------------------------------------------------------------
	mr           iArg4, path
	cmpwi        is_datadir, 0
	beq-         103$
	lwz          iArg3, 0x0050 (this)
	b            104$
103$:          
	li_sda       iArg3, __noname__686
104$:          
	addi         iArg2, sp, __sf__full_path
	li_sda       iArg1, __noname__688
	addi         iArg0, sp, __sf__full_path
	crclr        6
	bl           sprintf
#---[line 0002]------------------------------------------------------------------
	cmpwi        is_datadir, 0
	beq-         114$
	addi         iArg0, this, 0x0200
	bl           getChildCount__8CoreNodeFv
	cmpwi        r3, 0
	bne-         105$
	addi         iArg0, this, 0x0214
	bl           getChildCount__8CoreNodeFv
	cmpwi        r3, 0
	bne-         105$
	b            114$
#---[line 0003]------------------------------------------------------------------
105$:
	.set curr_corenode, iVar4
	lwz          curr_corenode, 0x0210 (this)
	b            109$  
#---[line 0005]------------------------------------------------------------------
106$:        
	lwz          iArg0, 0x0004 (curr_corenode)
	mr           iArg1, path
	bl           strcmp
	cmpwi        r3, 0
	bne-         108$
#---[line 0006]------------------------------------------------------------------
	lwz          r5, 0x0014 (curr_corenode)
	lwz          r4, 0x0018 (curr_corenode)
	li           r0, 0
	stw_bss      path, block, aramStream + 0x0000  #0x03A0
	stw_bss      r5,       block, aramStream + 0x0010  #0x03B0
	stw_bss      r4,       block, aramStream + 0x0008  #0x03A8
	stw_bss      r0,       block, aramStream + 0x000C  #0x03AC
#---[line 0007]------------------------------------------------------------------
	.set new_stream, iVar2
	li           iArg0, 32
	bl           alloc__6SystemFUl
	mr           new_stream, r3
	mr.          iArg0, new_stream
	beq-         107$
	li_bss       iArg1, block, aramStream
	lwz_sda      iArg2, readBuffer__9DVDStream
	lwz_bss      iArg3, block, dvdBufferedStream + 0x001C
	bl           __ct__19BufferedInputStreamFP6StreamPUci
107$:          
	mr           r3, new_stream
	b            117$
#---[line 0008]------------------------------------------------------------------
108$:          
	lwz          curr_corenode, 0x000C (curr_corenode)
#---[line 0004]------------------------------------------------------------------
109$:          
	cmplwi       curr_corenode, 0
	bne+         106$
#---[line 0009]------------------------------------------------------------------
	lwz          curr_corenode, 0x0224 (this)
	b            113$
110$:
#---[line 0011]------------------------------------------------------------------
	lwz          iArg0, 0x0004 (curr_corenode)
	mr           iArg1, path
	bl           strcmp
	cmpwi        r3, 0
	bne-         112$
	
#---[line 0012]------------------------------------------------------------------
	lwz          r5, 0x0014 (curr_corenode)
	lwz          r4, 0x0018 (curr_corenode)
	li           r0, 0
	stw_bss      path, block, aramStream + 0x0000  #0x03A0
	stw_bss      r5,       block, aramStream + 0x0010  #0x03B0
	stw_bss      r4,       block, aramStream + 0x0008  #0x03A8
	stw_bss      r0,       block, aramStream + 0x000C  #0x03AC
#---[line 0013]------------------------------------------------------------------
	.set new_stream, iVar2
	li           iArg0, 32
	bl           alloc__6SystemFUl
	mr           new_stream, r3
	mr.          iArg0, new_stream
	beq-         111$
	li_bss       iArg1, block, aramStream + 0x0000
	lwz_sda      iArg2, readBuffer__9DVDStream
	lwz_bss      iArg3, block, dvdStream + 0x0050
	bl           __ct__19BufferedInputStreamFP6StreamPUci
111$:
	mr           r3, new_stream
	b            117$
#---[line 0014]------------------------------------------------------------------
112$:         
	lwz          curr_corenode, 0x000C (curr_corenode)
#---[line 0010]------------------------------------------------------------------
113$:         
	cmplwi       curr_corenode, 0
	bne+         110$
#---[line 0015]------------------------------------------------------------------
114$:         
	lwz          r4, 0x023C (this)
	addi         r4, r4, 1
	stw          r4, 0x023C (this)
#---[line 0016]------------------------------------------------------------------
	.set unk_var2, iVar4
	addi         iArg0, sp, __sf__full_path
	stw_bss      iArg0, block, dvdStream + 0x0000
	li_bss       unk_var2, block, dvdStream + 0x0008
	mr           iArg1, unk_var2
	bl           DVDOpen
	neg          r3, r3
	crclr        6
	subic        r0, r3, 1
	subfe        r0, r0, r3
	stb_bss      r3, block, dvdStream + 0x004C
#---[line 0017]------------------------------------------------------------------
	li           r0, 0
	stw_bss      r0, block, dvdStream + 0x0044

#---[line 0018]------------------------------------------------------------------
	lwz_bss      r0, block, dvdStream + 0x003C
	stw_bss      r0, block, dvdStream + 0x0048

#---[line 0019]------------------------------------------------------------------
	li_bss       r3, block, lastName
	lwz_bss      r4, block, dvdStream + 0x0000
	bl           sprintf

#---[line 0020]------------------------------------------------------------------
	lwz_sda      r3, numOpen__9DVDStream
	addi         r3, r3, 1
	stw_sda      r3, numOpen__9DVDStream
#---[line 0021]------------------------------------------------------------------
	.set is_dvd_open, iVar3
	lbz_bss      is_dvd_open, block, dvdStream + 0x004C
	cmplwi       is_dvd_open, 0
	bne-         116$
#---[line 0022]------------------------------------------------------------------
	lwz_sda      r3, numOpen__9DVDStream
	subi         r3, r3, 1
	stw_sda      r3, numOpen__9DVDStream
#---[line 0023]------------------------------------------------------------------
	beq-         115$
#---[line 0024]------------------------------------------------------------------
	mr           iArg0, unk_var2
	bl           DVDClose
#---[line 0025]------------------------------------------------------------------
115$:         
	li           r3, 0
	b            117$
#---[line 0026]------------------------------------------------------------------
116$:         
	lwz_sda      r4, gsys
	lwz          r6, 0x001C (r4)
#---[line 0028]------------------------------------------------------------------
	li           r0, 1
	stw          r0, 0x001C (r4)
#---[line 0028]------------------------------------------------------------------
	stw          r6, 0x001C (r4)
#---[line 0029]------------------------------------------------------------------
	stw_bss      path, block, dvdStream + 0x0000
#---[line 0030]------------------------------------------------------------------
	li_bss       iArg0, block, dvdBufferedStream
	li_bss       iArg1, block, dvdStream
	lwz_sda      iArg2, readBuffer__9DVDStream
	lwz          iArg3, 0x025C (this)
	bl           init__19BufferedInputStreamFP6StreamPUci

#---[line 0031]------------------------------------------------------------------
	li_bss       r3, block, dvdBufferedStream
#---[Epilogue]-------------------------------------------------------------------
117$:
	lmw          r27, __sf__stmw_addr (sp)
	lwz          r0, 0x013C (sp)
	addi         sp, sp, __sfsize
	mtlr         r0
	blr          

#================================================================================
.section .ctors
#================================================================================


#================================================================================
.section .dtors
#================================================================================


#================================================================================
.section .rodata
#================================================================================


#================================================================================
.section .data
#================================================================================


#================================================================================
.section .bss
#================================================================================
.local ...bss.0
...bss.0 = 0x80398880

.local aramStream
aramStream = 0x80398c20

.local lastName
lastName = 0x80398c34

.local dvdStream
dvdStream = 0x80398d34

.local dvdBufferedStream
dvdBufferedStream = 0x80398d88

#================================================================================
.section .sdata
#================================================================================
.local __noname__687
__noname__687 = 0x803dd4e4

.local __noname__686
__noname__686 = 0x803dd4e0

.local __noname__688
__noname__688 = 0x803dd4e8

#================================================================================
.section .sbss
#================================================================================
.global gsys
gsys = 0x803e7b0c

.global readBuffer__9DVDStream
readBuffer__9DVDStream = 0x803e7b24

.global numOpen__9DVDStream
numOpen__9DVDStream = 0x803e7b28

#================================================================================
.section .sdata2
#================================================================================

#================================================================================
.section .sbss2
#================================================================================









