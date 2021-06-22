from struct import pack 
from math import ceil 
from binascii import unhexlify

from dol_c_kit import write_uint32

def mask_field(val, bits, signed):
    if signed == True:
        # Lowest negative value
        if val < -1 * 2**(bits-1):
            raise RuntimeError("{0} too large for {1}-bit signed field".format(val, bits))
        # Highest positive value
        if val > 2**(bits-1) - 1:
            raise RuntimeError("{0} too large for {1}-bit signed field".format(val, bits))
    else:
        # Highest unsigned value
        if val > 2**bits - 1:
            raise RuntimeError("{0} too large for {1}-bit unsigned field".format(val, bits))
    return val & (2**bits - 1)


def assemble_branch(addr, target_addr, LK=False, AA=False):
    out = 0
    # Calculate delta
    delta = target_addr - addr
    assert delta % 4 == 0
    # Mask and range check
    LI = mask_field(delta // 4, 24, True)
    # Set fields
    out |= (LK << 0)
    out |= (AA << 1)
    out |= (LI << 2)
    out |= (18 << 26)
    return out

def assemble_integer_arithmetic_immediate(opcd, rD, rA, SIMM):
    out = 0
    # Mask and range check
    SIMM = mask_field(SIMM, 16, True)
    rD = mask_field(rD, 5, False)
    rA = mask_field(rA, 5, False)
    # Set fields
    out |= (SIMM << 0)
    out |= (rA << 16)
    out |= (rD << 21)
    out |= (opcd << 26)
    return out

def assemble_integer_logical_immediate(opcd, rS, rA, UIMM):
    out = 0
    # Mask and range check
    mask_field(UIMM, 16, False)
    mask_field(rS, 5, False)
    mask_field(rA, 5, False)
    # Set fields
    out |= (UIMM << 0)
    out |= (rA << 16)
    out |= (rS << 21)
    out |= (opcd << 26)
    return out

# Assemble an instruction
def assemble_addi(rD, rA, SIMM):
    return assemble_integer_arithmetic_immediate(14, rD, rA, SIMM)
def assemble_addis(rD, rA, SIMM):
    return assemble_integer_arithmetic_immediate(15, rD, rA, SIMM)
def assemble_ori(rS, rA, UIMM):
    return assemble_integer_logical_immediate(24, rS, rA, UIMM)
def assemble_oris(rS, rA, SIMM):
    return assemble_integer_logical_immediate(25, rS, rA, UIMM)
# Simplified mnenonics
def assemble_li(rD, SIMM):
    return assemble_addi(rD, 0, SIMM)
def assemble_lis(rD, SIMM):
    return assemble_addis(rD, 0, SIMM)
def assemble_nop():
    return assemble_ori(0, 0, 0)
    
# Write instructions to DOL
def write_branch(dol, target_addr, LK=False, AA=False):
    write_uint32(dol, assemble_branch(dol.tell(), target_addr, LK, AA))
def write_addi(dol, rD, rA, SIMM):
    write_uint32(dol, assemble_addi(rD, rA, SIMM))
def write_addis(dol, rD, rA, SIMM):
    write_uint32(dol, assemble_addis(rD, rA, SIMM))
def write_ori(dol, rS, rA, UIMM):
    write_uint32(dol, assemble_ori(rS, rA, UIMM))
def write_oris(dol, rS, rA, UIMM):
    write_uint32(dol, assemble_oris(rS, rA, UIMM))
# Simplified mnenonics
def write_li(dol, rD, SIMM):
    write_uint32(dol, assemble_li(rD, SIMM))
def write_lis(dol, rD, SIMM):
    write_uint32(dol, assemble_lis(rD, SIMM))
def write_nop(dol):
    write_uint32(dol, assemble_nop())


def _read_line(line):
    line = line.strip()
    vals = line.split(" ")
    for i in range(vals.count("")):
        vals.remove("")
    
    val1 = int(vals[0], 16)
    val2 = int(vals[1], 16)
    
    return val1, val2

def apply_gecko(dol, f):
    while True:
        line = f.readline()
        if line == "":
            break 
        if line.strip() == "" or line.startswith("$") or line.startswith("*"):
            continue 
        
        val1, val2 = _read_line(line)
        
        codetype = val1 >> 24
        addr = 0x80000000 + (val1 & 0xFFFFFF)
        
        hi = codetype & 0b1
        if hi:
            addr += 0x01000000
            
        
        if codetype == 0x00:
            amount = (val2 >> 16) + 1 
            value = val2 & 0xFF
            
            dol.seek(addr)
            for i in range(amount):
                dol.write(pack("B", value))
                
        elif codetype == 0x02:
            amount = (val2 >> 8) + 1 
            value = val2 & 0xFFFF
            
            dol.seek(addr)
            for i in range(amount):
                dol.write(pack(">H", value))
                
        elif codetype == 0x04: 
            dol.seek(addr)
            dol.write(pack(">I", val2))
        
        elif codetype == 0x06:
            bytecount = val2 
            dol.seek(addr)
            for i in range(int(ceil(bytecount/8.0))):
                datalen = bytecount % 8
                line = f.readline().strip()
                assert line != ""
                vals = line.split(" ")
                for j in range(vals.count("")):
                    vals.remove("")
                data = "".join(vals)
                
                dol.write(unhexlify(data)[:datalen])
                bytecount -= 8 
        
        elif codetype == 0xC6:
            dol.seek(addr)
            write_branch(dol, val2, LK=False)
