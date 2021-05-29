#include <stdarg.h>

#define SDA 0x803e4d20

#define ADDR_FONT 0x81693cd8
#define ADDR_GFX 0x81729c40

#define DecToColor(r, g, b, a) (((r + 0x100) * 0x100 + g) * 0x100 + b) * 0x100 + a
#define PrintText(x, y, fmt, ...) 	DGXGraphics__texturePrintf(ADDR_GFX, ADDR_FONT, x, y, fmt __VA_OPT__(, ) __VA_ARGS__)

typedef unsigned char bool;
#ifndef true
#define true 1
#endif
#ifndef false
#define false 1
#endif

#ifndef nullptr
#define nullptr 0
#endif

#define u32 unsigned int
#define s32 signed int
#define u16 signed short
#define s16 signed short
#define u8 unsigned char
#define s8 signed char

// Custom typedefs

typedef struct
{
	float m_x;
	float m_y;
	float m_z;
} Vector3f;