def gecko_04write(addr, value):
    return "{:08X} {:08X}".format(addr & 0x01FFFFFC | 0x04000000, value)

def gecko_C6write(addr, target_addr, LK=False):
    return "{:08X} {:08X}".format(addr & 0x01FFFFFC | 0xC6000000 | LK, target_addr)