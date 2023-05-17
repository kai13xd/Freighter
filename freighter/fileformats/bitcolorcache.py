from dataclasses import dataclass


"""
bitmask reference because I forget

bits dec hex
---- --- ---
1    1   0x1
2    3   0x3
3    7   0x7
4    17  0xf
5    31  0x1f
6    63  0x3f
7    127 0x7f
8    255 0x255
"""

# Truncated color values
BITCOLOR_CACHE = []

color_range = range(256)
result = []
for i in color_range:
    result.append(0)  # 0 lmao
BITCOLOR_CACHE.append(result)
result = []
for i in color_range:
    # result.append((i >> 7) * 255)  # 1 bit
    result.append(i >> 7)  # 1 bit
BITCOLOR_CACHE.append(result)
result = []
for i in color_range:
    # result.append((i >> 6) * 85)  # 2-bit
    result.append(i >> 6)  # 2-bit
BITCOLOR_CACHE.append(result)
result = []
for i in color_range:
    # result.append((i >> 5) * 36)  # 3-bit
    result.append(i >> 5)  # 3-bit
BITCOLOR_CACHE.append(result)
result = []
for i in color_range:
    # result.append((i >> 4) * 17)  # 4-bit
    result.append(i >> 4)  # 4-bit
BITCOLOR_CACHE.append(result)
result = []
for i in color_range:
    # result.append((i >> 3) * 8)  # 5-bit
    result.append(i >> 3)  # 5-bit
BITCOLOR_CACHE.append(result)
result = []
for i in color_range:
    # result.append((i >> 2) * 4)  # 6-bit
    result.append(i >> 2)  # 6-bit
BITCOLOR_CACHE.append(result)
result = []
for i in color_range:
    # result.append((i >> 1) * 2)  # 7-bit
    result.append(i >> 1)  # 7-bit
BITCOLOR_CACHE.append(result)
