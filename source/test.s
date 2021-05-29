.include "../source/defines.inc"
.section .text

.global newfunc
newfunc:
	lwz  r0, r0 (r3)
	li   r3, 5
	nop
	nop
	nop
	nop
	nop
	blr  

