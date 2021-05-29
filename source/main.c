#include <defines.h>

const u32 textColor = DecToColor(100, 100, 100, 0xFF);

#define DPP_RETURN_SUCCESS 0x80000000
int DrawPlugPiki()
{
	// Set the colour of the text before printing
	DGXGraphics__setColour(ADDR_GFX, &textColor, 1);
	// Print "hello! 122" to showcase variadic argument printing at the (X, Y) position of 50, 50
	PrintText(50, 50, "hello! %d", 122);

	// This is required to show that 
    return DPP_RETURN_SUCCESS;
}