from dolreader.dol import DolFile
from freighter.colors import *
from freighter.console import *
from freighter.doltools import *
from freighter.path import *
from geckolibs.geckocode import GeckoCommand, Write16, Write32, WriteBranch, WriteString
from dataclasses import dataclass

SupportedGeckoCodetypes = [
    GeckoCommand.Type.WRITE_8,
    GeckoCommand.Type.WRITE_16,
    GeckoCommand.Type.WRITE_32,
    GeckoCommand.Type.WRITE_STR,
    GeckoCommand.Type.WRITE_SERIAL,
    GeckoCommand.Type.WRITE_BRANCH,
    GeckoCommand.Type.ASM_INSERT,
    GeckoCommand.Type.ASM_INSERT_XOR,
]


@dataclass
class Hook:
    address: int
    source_file: str|PathLike
    line_number: int
    symbol_name: str
    good: bool = False
    data: Any = 0
    

    def __init__(self, address: int | str, source_file: str|PathLike= "", line_number: int = 0):
        if isinstance(address, str):
            address = int(address, 16)
        self.address = address
        self.source_file = source_file
        self.line_number = line_number

    def resolve(self, symbols):
        return

    def apply_dol(self, dol: DolFile):
        if dol.is_mapped(self.address):
            self.good = True

    def write_geckocommand(self, f):
        self.good = True

    def __repr__(self):
        return repr("{:s} {:08X}".format("{:13s}".format("[Hook]       "), self.address))[+1:-1]


class BranchHook(Hook):
    def __init__(self, address, symbol_name, source_file, line_number, lk_bit=False):
        Hook.__init__(self, address, source_file, line_number)
        self.symbol_name = symbol_name
        self.lk_bit = lk_bit

    def resolve(self, symbols):
        if self.symbol_name in symbols:
            symbol = symbols[self.symbol_name]
            if symbol.address:
                self.data = symbol.address
            else:
                return

    def apply_dol(self, dol: DolFile):
        if self.data and dol.is_mapped(self.address):
            dol.seek(self.address)
            dol.write(assemble_branch(self.address, self.data, LK=self.lk_bit))
            self.good = True

    def write_geckocommand(self, f):
        if self.data:
            gecko_command = WriteBranch(self.data, self.address, isLink=self.lk_bit)
            f.write(gecko_command.as_text() + "\n")
            self.good = True

    def __repr__(self):
        return f"💉 {f'{ORANGE}BranchLink' if self.lk_bit else f'{PURPLE}[Branch]'} 0x{self.address:x}{f'{GREEN} ✔️ {self.symbol_name}' if self.good else f'{RED} ❌ {self.symbol_name}{RED}    Address was not found!'}"


class PointerHook(Hook):
    def __init__(self, address, symbol_name):
        Hook.__init__(self, address)
        self.symbol_name = symbol_name

    def resolve(self, symbols):
        if self.symbol_name in symbols:
            self.data = symbols[self.symbol_name].address

    def apply_dol(self, dol: DolFile):
        if self.data and dol.is_mapped(self.address):
            dol.write_uint32(self.address, self.data)
            self.good = True

    def write_geckocommand(self, f):
        if self.data:
            gecko_command = Write32(self.data, self.address)
            f.write(gecko_command.as_text() + "\n")
            self.good = True

    def __repr__(self):
        return f"💉 {CYAN}Pointer 0x{self.address:x}{f'{GREEN} ✔️' if self.good else f'{RED} ❌'} {self.symbol_name}"


class StringHook(Hook):
    def __init__(self, address: int | str, string: str, encoding: str = "ascii", max_strlen: int | None = None):
        Hook.__init__(self, address)
        self.data = bytearray()
        self.string = string
        self.encoding = encoding
        self.max_strlen = max_strlen

    def resolve(self, symbols):
        self.data = self.string.encode(self.encoding) + b"\x00"
        if self.max_strlen != None:
            if len(self.data) > self.max_strlen:
                Console.print('Warning: "{:s}" exceeds {} bytes!'.format(repr(self.string)[+1:-1], self.max_strlen))
            else:
                while len(self.data) < self.max_strlen:
                    self.data += b"\x00"

    def apply_dol(self, dol: DolFile):
        if dol.is_mapped(self.address):
            dol.seek(self.address)
            dol.write(self.data)
            self.good = True

    def write_geckocommand(self, f):
        gecko_command = WriteString(self.data, self.address)
        f.write(gecko_command.as_text() + "\n")
        self.good = True

    def __repr__(self):
        return f'✍️ {PURPLE}StringHook 0x{self.address:x} -> "{self.string}"'


class FileHook(Hook):
    def __init__(self, address, filepath, start, end, max_size):
        Hook.__init__(self, address)
        self.data = bytearray()
        self.filepath = filepath
        self.start = start
        self.end = end
        self.max_size = max_size

    def resolve(self, symbols):
        try:
            with open(self.filepath, "rb") as f:
                if self.end == None:
                    self.data = f.read()[self.start :]
                else:
                    self.data = f.read()[self.start : self.end]
                if self.max_size != None:
                    if len(self.data) > self.max_size:
                        Console.print('Warning: "{:s}" exceeds {} bytes!'.format(repr(self.filepath)[+1:-1], self.max_size))
                    else:
                        while len(self.data) < self.max_size:
                            self.data += b"\x00"
        except OSError:
            Console.print('Warning: "{:s}" could not be opened!'.format(repr(self.filepath)[+1:-1]))

    def apply_dol(self, dol: DolFile):
        if dol.is_mapped(self.address):
            dol.seek(self.address)
            dol.write(self.data)
            self.good = True

    def write_geckocommand(self, f):
        gecko_command = WriteString(self.data, self.address)
        f.write(gecko_command.as_text() + "\n")
        self.good = True

    def __repr__(self):
        return f'[File] 0x{self.address:x} -> "{self.filepath}"'


class NOPHook(Hook):

    def apply_dol(self, dol: DolFile):
        if dol.is_mapped(self.address):
            dol.write_uint32(self.address, 0x60000000)
            self.good = True

    def __repr__(self):
        return f"✋ {PURPLE}NOPHook 0x{self.address:x} -> nop"


class Immediate16Hook(Hook):
    def __init__(self, address, symbol_name, modifier):
        Hook.__init__(self, address)
        self.symbol_name = symbol_name
        self.modifier = modifier

    def resolve(self, symbols):
        # I wrote these fancy @h, @l, @ha functions to barely use them, lol.  When writing
        # 16-bit immediates, you don't really need to worry about whether or not it is
        # signed, since you're masking off any sign extension that happens regardless.
        if self.symbol_name in symbols:
            if self.modifier == "@h":
                self.data = hi(symbols[self.symbol_name]["st_value"], True)
            elif self.modifier == "@l":
                self.data = lo(symbols[self.symbol_name]["st_value"], True)
            elif self.modifier == "@ha":
                self.data = hia(symbols[self.symbol_name]["st_value"], True)
            elif self.modifier == "@sda":
                if symbols["_SDA_BASE_"]["st_value"] == None:
                    raise RuntimeError("You must set this project's sda_base member before using the @sda modifier!  Check out the set_sda_bases method.")
                self.data = mask_field(
                    symbols[self.symbol_name]["st_value"] - symbols["_SDA_BASE_"]["st_value"],
                    16,
                    True,
                )
            elif self.modifier == "@sda2":
                if symbols["_SDA2_BASE_"]["st_value"] == None:
                    raise RuntimeError("You must set this project's sda2_base member before using the @sda2 modifier!  Check out the set_sda_bases method.")
                self.data = mask_field(
                    symbols[self.symbol_name]["st_value"] - symbols["_SDA2_BASE_"]["st_value"],
                    16,
                    True,
                )
            else:
                Console.print('Unknown modifier: "{}"'.format(self.modifier))
            self.data = mask_field(self.data, 16, True)

    def apply_dol(self, dol: DolFile):
        if self.data and dol.is_mapped(self.address):
            dol.write_uint16(self.address, self.data)
            self.good = True

    def write_geckocommand(self, f):
        if self.data:
            gecko_command = Write16(self.data, self.address)
            f.write(gecko_command.as_text() + "\n")
            self.good = True

    def __repr__(self):
        return repr(
            "{:s} {:08X} {:s} {:s} {:s}".format(
                "[Immediate16]",
                self.address,
                "-->" if self.good else "-X>",
                self.symbol_name,
                self.modifier,
            )
        )[+1:-1]


# Paired-Singles Load and Store have a 12-bit immediate field, unlike normal load/store instructions
class Immediate12Hook(Hook):
    def __init__(self, address, w, i, symbol_name, modifier):
        Hook.__init__(self, address)
        self.w = w
        self.i = i
        self.symbol_name = symbol_name
        self.modifier = modifier

    def resolve(self, symbols):
        # I wrote these fancy @h, @l, @ha functions to barely use them, lol.  When writing
        # 16-bit immediates, you don't really need to worry about whether or not it is
        # signed, since you're masking off any sign extension that happens regardless.
        if self.symbol_name in symbols:
            if self.modifier == "@h":
                self.data = hi(symbols[self.symbol_name]["st_value"], True)
            elif self.modifier == "@l":
                self.data = lo(symbols[self.symbol_name]["st_value"], True)
            elif self.modifier == "@ha":
                self.data = hia(symbols[self.symbol_name]["st_value"], True)
            elif self.modifier == "@sda":
                if symbols["_SDA_BASE_"]["st_value"] == None:
                    raise RuntimeError("You must set this project's sda_base member before using the @sda modifier!  Check out the set_sda_bases method.")
                self.data = mask_field(
                    symbols[self.symbol_name]["st_value"] - symbols["_SDA_BASE_"]["st_value"],
                    16,
                    True,
                )
            elif self.modifier == "@sda2":
                if symbols["_SDA2_BASE_"]["st_value"] == None:
                    raise RuntimeError("You must set this project's sda2_base member before using the @sda2 modifier!  Check out the set_sda_bases method.")
                self.data = mask_field(
                    symbols[self.symbol_name]["st_value"] - symbols["_SDA2_BASE_"]["st_value"],
                    16,
                    True,
                )
            else:
                Console.print('Unknown modifier: "{}"'.format(self.modifier))
            self.data = mask_field(self.data, 12, True)
            self.data |= mask_field(self.i, 1, False) << 12
            self.data |= mask_field(self.w, 3, False) << 13

    def apply_dol(self, dol: DolFile):
        if self.data and dol.is_mapped(self.address):
            dol.write_uint16(self.address, self.data)
            self.good = True

    def write_geckocommand(self, f):
        if self.data:
            gecko_command = Write16(self.data, self.address)
            f.write(gecko_command.as_text() + "\n")
            self.good = True

    def __repr__(self):
        return f"[Immediate12] 0x{self.address:x} {self.symbol_name} {self.modifier}"
