"""
A bitmask reference because I always forget

Bits Dec Hex
---- --- ---
1    1   0x1
2    3   0x3
3    7   0x7
4    17  0xf
5    31  0x1f
6    63  0x3f
7    127 0x7f
8    255 0x255

This is mostly a means to speed up CPU encoding by utilizing a cache look up table. 

Curious about ways to improve texture quality through dithering.

I also wonder if there is a clever way to remap colors to better reconstruct the 
original image when decoding

For example these do not remap within the full color range of 0-255:
3-bit range 0-252
5-bit range 0-248
7-bit range 0-254
"""
color_range = range(256)

# Raw encoded value
BITCOLOR_CACHE: list[list[int]] = [[], [], [], [], [], [], [], []]

# Multiplied by a factor to map back to 0-255 range
TRUNCATED_BITCOLOR_CACHE: list[list[int]] = [[], [], [], [], [], [], [], []]

# lmao
for i in color_range:
    BITCOLOR_CACHE[0].append(0)
    TRUNCATED_BITCOLOR_CACHE[0].append(0)
# 1 bit
for i in color_range:
    BITCOLOR_CACHE[1].append(i >> 7)
    TRUNCATED_BITCOLOR_CACHE[1].append((i >> 7) * 255)
# 2-bit
for i in color_range:
    BITCOLOR_CACHE[2].append(i >> 6)
    TRUNCATED_BITCOLOR_CACHE[2].append((i >> 6) * 85)
# 3-bit
for i in color_range:
    BITCOLOR_CACHE[3].append(i >> 5)
    TRUNCATED_BITCOLOR_CACHE[3].append((i >> 5) * 36)
# 4-bit
for i in color_range:
    BITCOLOR_CACHE[4].append(i >> 4)
    TRUNCATED_BITCOLOR_CACHE[4].append((i >> 4) * 17)
# 5-bit
for i in color_range:
    BITCOLOR_CACHE[5].append(i >> 3)
    TRUNCATED_BITCOLOR_CACHE[5].append((i >> 3) * 8)
# 6-bit
for i in color_range:
    BITCOLOR_CACHE[6].append(i >> 2)
    TRUNCATED_BITCOLOR_CACHE[6].append((i >> 2) * 4)
# 7-bit
for i in color_range:
    BITCOLOR_CACHE[7].append(i >> 1)
    TRUNCATED_BITCOLOR_CACHE[7].append((i >> 1) * 2)
