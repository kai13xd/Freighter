	.file	"ctest.c"
	.machine ppc
	.section	".text"
	.align 2
	.globl newfunc
	.type	newfunc, @function
newfunc:
.LFB0:
	.cfi_startproc
	li 3,5
	blr
	.cfi_endproc
.LFE0:
	.size	newfunc, .-newfunc
	.ident	"GCC: (devkitPPC release 37) 10.1.0"
