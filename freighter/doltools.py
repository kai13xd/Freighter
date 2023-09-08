import struct

from freighter.symbols import Address, DEFAULT_GAMECUBE_ADDRESS_SPACE
from dolreader.dol import DolFile


def mask_field(val: int, bits, is_signed: bool):
    if is_signed == True:
        # Lowest negative value
        if val < -1 * 2 ** (bits - 1):
            raise RuntimeError("{0} too large for {1}-bit signed field".format(val, bits))
        # Highest positive value
        if val > 2 ** (bits - 1) - 1:
            raise RuntimeError("{0} too large for {1}-bit signed field".format(val, bits))
    else:
        # Highest unsigned value
        if val > 2**bits - 1:
            raise RuntimeError("{0} too large for {1}-bit unsigned field".format(val, bits))
    return val & (2**bits - 1)


def sign_extend(val: int, bits):
    sign_bit = 1 << (bits - 1)
    return (val & (sign_bit - 1)) - (val & sign_bit)


def hi(val: int, is_signed: bool):  # @h Modifier
    if is_signed:
        return sign_extend(val >> 16, 16)
    else:
        return val >> 16 & 0xFFFF


def lo(val: int, is_signed: bool):  # @l Modifier
    if is_signed:
        return sign_extend(val, 16)
    else:
        return val & 0xFFFF


def hia(val: int, is_signed: bool):  # @ha Modifier
    if val & 0x8000:
        return hi(val + 0x10000, is_signed)
    else:
        return hi(val, is_signed)


def assemble_branch(addr: Address, target_addr: Address, LK: bool = False, AA: bool = False):
    out = 0
    # Calculate delta
    delta = target_addr - addr
    assert delta % 4 == 0
    # Mask and range check
    LI = mask_field(delta // 4, 24, True)
    # Set fields
    out |= LK << 0
    out |= AA << 1
    out |= LI << 2
    out |= 18 << 26
    return struct.pack(">I", out)


def assemble_integer_arithmetic_immediate(opcd: int, rD: int, rA: int, SIMM: int):
    out = 0
    # Mask and range check
    SIMM = mask_field(SIMM, 16, True)
    rD = mask_field(rD, 5, False)
    rA = mask_field(rA, 5, False)
    # Set fields
    out |= SIMM << 0
    out |= rA << 16
    out |= rD << 21
    out |= opcd << 26
    return struct.pack(">I", out)


def assemble_integer_logical_immediate(opcd: int, rA: int, rS: int, UIMM: int):
    out = 0
    # Mask and range check
    mask_field(UIMM, 16, False)
    mask_field(rS, 5, False)
    mask_field(rA, 5, False)
    # Set fields
    out |= UIMM << 0
    out |= rA << 16
    out |= rS << 21
    out |= opcd << 26
    return struct.pack(">I", out)


# Assemble an instruction
def assemble_addi(rD: int, rA: int, SIMM: int):
    return assemble_integer_arithmetic_immediate(14, rD, rA, SIMM)


def assemble_addis(rD: int, rA: int, SIMM: int):
    return assemble_integer_arithmetic_immediate(15, rD, rA, SIMM)


def assemble_ori(rA: int, rS: int, UIMM: int):
    return assemble_integer_logical_immediate(24, rA, rS, UIMM)


def assemble_oris(rA: int, rS: int, UIMM: int):
    return assemble_integer_logical_immediate(25, rA, rS, UIMM)


# Simplified mnenonics
def assemble_li(rD: int, SIMM: int):
    return assemble_addi(rD, 0, SIMM)


def assemble_lis(rD: int, SIMM: int):
    return assemble_addis(rD, 0, SIMM)


def assemble_nop():
    return assemble_ori(0, 0, 0)


# Write instructions to DOL
def write_branch(dol: DolFile, target_addr: Address, LK=False, AA=False):
    dol.write(assemble_branch(Address(DEFAULT_GAMECUBE_ADDRESS_SPACE, dol.tell()), target_addr, LK, AA))


def write_addi(dol: DolFile, rD: int, rA: int, SIMM: int):
    dol.write(assemble_addi(rD, rA, SIMM))


def write_addis(dol: DolFile, rD: int, rA: int, SIMM: int):
    dol.write(assemble_addis(rD, rA, SIMM))


def write_ori(dol: DolFile, rA: int, rS: int, UIMM: int):
    dol.write(assemble_ori(rA, rS, UIMM))


def write_oris(dol: DolFile, rA: int, rS: int, UIMM: int):
    dol.write(assemble_oris(rA, rS, UIMM))


# Simplified mnenonics
def write_li(dol: DolFile, rD: int, SIMM: int):
    dol.write(assemble_li(rD, SIMM))


def write_lis(dol: DolFile, rD: int, SIMM: int):
    dol.write(assemble_lis(rD, SIMM))


def write_nop(dol: DolFile):
    dol.write(assemble_nop())
