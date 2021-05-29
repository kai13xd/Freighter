#include <stdint.h>

#define PRESS_START	0x1000
#define PRESS_B		0x0200
#define PRESS_A		0x0100
#define PRESS_Z		0x0010
#define PRESS_X		0x0400
#define PRESS_Y		0x0800
#define PRESS_DU	0x0008
#define PRESS_DD	0x0004
#define PRESS_DL	0x0001
#define PRESS_DR	0x0002
#define ANALOG_UP       0x0800
#define ANALOG_DOWN     0x0400
#define ANALOG_LEFT     0x0100 
#define ANALOG_RIGHT    0x0200

typedef struct{
	uint16_t buttons;
	int8_t lanalogx;
	int8_t lanalogy;
	int8_t ranalogx;
	int8_t ranalogy;
	uint16_t u1;
	uint8_t status;
	uint8_t u2;
	uint8_t u3;
	uint8_t u4;
} __attribute__((packed)) Controller;
