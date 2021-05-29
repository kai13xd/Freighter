#---GPRs-------------------------------------------------------
r0  =  0
r1  =  1
r2  =  2
r3  =  3
r4  =  4
r5  =  5
r6  =  6
r7  =  7
r8  =  8
r9  =  9
r10 = 10
r11 = 11
r12 = 12
r13 = 13
r14 = 14
r15 = 15
r16 = 16
r17 = 17
r18 = 18
r19 = 19
r20 = 20
r21 = 21
r22 = 22
r23 = 23
r24 = 24
r25 = 25
r26 = 26
r27 = 27
r28 = 28
r29 = 29
r30 = 30
r31 = 31
#---FPRs-------------------------------------------------------
f0  =  0
f1  =  1
f2  =  2
f3  =  3
f4  =  4
f5  =  5
f6  =  6
f7  =  7
f8  =  8
f9  =  9
f10 = 10
f11 = 11
f12 = 12
f13 = 13
f14 = 14
f15 = 15
f16 = 16
f17 = 17
f18 = 18
f19 = 19
f20 = 20
f21 = 21
f22 = 22
f23 = 23
f24 = 24
f25 = 25
f26 = 26
f27 = 27
f28 = 28
f29 = 29
f30 = 30
f31 = 31
#---EABI-------------------------------------------------------
sp = r1
rtoc = r2
# r14 to r31 store local variables when a stack frame is constructed.
iVar0  = r31
iVar1  = r30
iVar2  = r29
iVar3  = r28
iVar4  = r27
iVar5  = r26
iVar6  = r25
iVar7  = r24
iVar8  = r23
iVar9  = r22
iVar10 = r21
iVar11 = r20
iVar12 = r19
iVar13 = r18
iVar14 = r17
iVar15 = r16
iVar16 = r15
iVar17 = r14
# On function call, r3 to r10 contain the integer arguments to the function, in code order. If a function needs more arguments, these are stored in the caller's stack frame.
iArg0  =  r3
iArg1  =  r4
iArg2  =  r5
iArg3  =  r6
iArg4  =  r7
iArg5  =  r8
iArg6  =  r9
iArg7  = r10
# If the function returns an integer value, it is stored in r3 to r4. r4 is only used for this purpose if the return value is a 64 bit number.
retval = r3
retval64h = r3
retval64l = r4

_SDA_BASE = 0x803e4d20
_SDA2_BASE = 0x803f0200
UNUSED = 0

#---Other Macros-----------------------------------------------
	.macro       call target_addr
		# Clobbers r12
		lis          r12,      \target_addr@h
		ori          r12, r12, \target_addr@l
		mtlr         r12
		blrl         
	.endm

#---Math Macros------------------------------------------------
	.macro       modw rD, rA, rB
		# Clobbers r0
		divw         r0, \rA, \rB
		mullw        r0, r0, \rB
		sub          \rD, \rA, r0
	.endm
	.macro       modwi rD, rA, SIMM
		# Clobbers r0
		li           r0, \SIMM
		divw         r0, \rA, r0
		mulli        r0, r0, \SIMM
		sub          \rD, \rA, r0
	.endm

#---SDATA Macros-----------------------------------------------
	.macro       li_sda rD, target_addr
		addi         \rD, r13, \target_addr - _SDA_BASE
	.endm
	.macro       lwz_sda rD, target_addr
		lwz          \rD, \target_addr - _SDA_BASE (r13)
	.endm
	.macro       stw_sda rS, target_addr
		stw          \rS, \target_addr - _SDA_BASE (r13)
	.endm

#---SDATA2 Macros----------------------------------------------
	.macro       li_sda2 rD, target_addr
		addi         \rD, rtoc, \target_addr - _SDA2_BASE
	.endm
	.macro       lwz_sda2 rD, target_addr
		lwz          \rD, \target_addr - _SDA2_BASE (rtoc)
	.endm
	.macro       stw_sda2 rS, target_addr
		stw          \rS, \target_addr - _SDA2_BASE (rtoc)
	.endm


