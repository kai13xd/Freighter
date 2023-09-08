from __future__ import annotations

import subprocess
from subprocess import Popen
from typing import IO, TypeVar, Generic, Protocol, NewType


from attrs import define, field
from freighter.config import *
from freighter.filemanager import ObjectFile, SourceFile, FileManager
from freighter.logging import Logger
from freighter.numerics import UInt, ULong, Int, Long
from freighter.path import DirectoryPath


class Demangler:
    process: Popen
    stdout: IO[bytes]
    stdin: IO[bytes]

    @property
    @classmethod
    def is_running(cls) -> bool:
        return cls.process.poll() is None

    @classmethod
    def __init__(cls, binutils: BinUtils) -> None:
        if cls.is_running is None:
            cls.process.kill()
        cls.process = Popen(binutils.CPPFLIT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        Logger.debug(f'Opened Demangler process using "{binutils.CPPFLIT}"')
        if cls.process.stdin:
            cls.stdin = cls.process.stdin
        if cls.process.stdout:
            cls.stdout = cls.process.stdout

    @classmethod
    def demangle(cls, string: str) -> str:
        cls.stdin.write(f"{string}\n".encode())
        cls.stdin.flush()
        demangled = cls.stdout.readline().decode().rstrip()
        Logger.info(f" 🧼 {CYAN}{string}{PURPLE} -> {GREEN}{demangled}")
        return demangled


class AddressOutOfBoundsException(Exception):
    pass


T = TypeVar("T", bound=Union[UInt, ULong])


class AddressSpace(Generic[T]):
    def __init__(self, min_physical_address: T, max_physical_address: T, min_address: T, max_address: T) -> None:
        self.min_physical_address: T = min_physical_address
        self.max_physical_address: T = max_physical_address
        self.min_address: T = min_address
        self.max_address: T = max_address

    @property
    def size(self) -> T:
        return self.max_address - self.min_address

    def create_valid_offset(self, offset: T) -> T:
        if offset > self.min_physical_address and offset < self.max_physical_address:
            return offset
        if offset > self.min_address and offset < self.max_address:
            return offset - self.min_address
        else:
            raise AddressOutOfBoundsException()

    def contains(self, offset: int) -> bool:
        return offset < 0 or offset > self.max_address


DEFAULT_GAMECUBE_ADDRESS_SPACE: AddressSpace[UInt] = AddressSpace[UInt](UInt(0x0), UInt(0x017FFFFF), UInt(0x80000000), UInt(0x817FFFFF))


@define
class Address(Generic[T]):
    address_space: AddressSpace[T]
    _offset: T

    def __init__(self, address_space: AddressSpace[T], offset: T) -> None:
        self.address_space = address_space
        self._offset = self.address_space.create_valid_offset(offset)
        pass

    @property
    def offset(self):
        return self._offset

    @property
    def physical_address(self) -> T:
        return self.address_space.min_physical_address + self.offset

    @property
    def virtual_address(self) -> T:
        return self.address_space.min_address + self.offset

    @property
    def hex_offset(self) -> str:
        return self.offset.hex

    @property
    def hex_virtual_address(self) -> str:
        return (self.address_space.min_address + self.offset).hex

    @property
    def hex_physical_address(self) -> str:
        return (self.address_space.min_physical_address + self.offset).hex

    def add_offset(self, value: int) -> None:
        self._offset += value

    def __hash__(self) -> int:
        return self.virtual_address

    def __repr__(self) -> str:
        return f"@{self.hex_virtual_address}"

    def __sub__(self, value: Address | int) -> Long:
        if isinstance(value, Address):
            return Long(self._offset) - Long(value._offset)
        else:
            return Long(self.virtual_address) - Long(value)


@define
class Symbol:
    # Private fields
    _name: str = field(alias="name")
    _address: Address | None = field(alias="address")

    nm_type: str

    # Public fields
    size: int
    """The physical memory size of this symbol"""

    section: str = ""
    """The memory section this symbol belongs to."""

    source: str = ""
    """The source file this symbol belongs to."""

    @property
    def is_undefined(self) -> bool:
        """Is this symbol referenced but not defined in it's source file?"""
        return self.nm_type in [None, "u", "U", "b"]

    @property
    def is_weak(self) -> bool:
        """Is this symbol a weak symbol?"""
        return self.nm_type == "v"

    @property
    def is_function(self) -> bool:
        """Is this symbol a function symbol?"""
        return self.nm_type == "T"

    @property
    def is_data(self) -> bool:
        """Is this symbol a data symbol?"""
        return self.nm_type == "d"

    @property
    def is_bss(self) -> bool:
        """Is this symbol a static data symbol?"""
        return self.nm_type == "B"

    @property
    def is_rodata(self) -> bool:
        """Is this symbol a readonly data symbol?"""
        return self.nm_type == "r"

    @property
    def is_c_linkage(self) -> bool:
        """
        Returns:

        True if this symbol's name is C linkage.

        False if this symbol's name is detected to formatted as a GCC Itanium ABI C++ symbol; i.e, the symbol name starts with '_Z'.
        """
        return not self._name.startswith("_Z")

    @property
    def is_absolute(self) -> bool:
        """Is this symbol an absolute symbol?"""
        return self.nm_type == "a"

    @property
    def is_complete_constructor(self) -> bool:
        """Returns True if this symbol a GCC complete constructor, otherwise False."""
        return "C1" in self._name

    @property
    def is_base_constructor(self) -> bool:
        """Returns True if this symbol is a GCC base constructor, otherwise False."""
        return "C2" in self._name

    @property
    def name(self) -> str:
        """Returns the symbol name. If this is a C++ symbol, returns the mangled symbol name."""
        return self._name

    @property
    def demangled_name(self) -> str:
        if self.is_c_linkage:
            return self._name
        else:
            return Demangler.demangle(self._name)

    @property
    def address(self) -> Address | None:
        """Returns the symbol's virtual address as an int"""
        return self._address

    @address.setter
    def address(self, value: int) -> None:
        self._address = Address[UInt](DEFAULT_GAMECUBE_ADDRESS_SPACE, UInt(value))

    @property
    def hex_address(self) -> str | None:
        """Returns the symbol's virtual address as a hex formatted string"""
        if self._address:
            return self._address.hex_virtual_address

    @hex_address.setter
    def hex_address(self, value: str) -> None:
        self._address = Address[UInt](DEFAULT_GAMECUBE_ADDRESS_SPACE, UInt(value))

    def __repr__(self) -> str:
        if self.is_c_linkage:
            return f"{self.name} @ {self.hex_address}"
        else:
            return f"{self.name} ({self.demangled_name}) @ {self.hex_address}"

    def __hash__(self):
        return hash((self.name, self.address))


class SymbolManager:
    def __init__(self, project_name: str, profile: ProjectProfile, binutils: BinUtils):
        self.project_name = project_name
        self.binutils = binutils
        self.symbols_folder = profile.SymbolsFolder
        self.dump_folder = profile.TemporaryFilesFolder / "dump"
        self.dump_folder.create()
        Demangler(binutils)
        self.symbols = dict[str, Symbol]()

    def add_symbol(self, symbol: Symbol):
        """Adds a Symbol object reference to the SymbolManager.

        Args:
            symbol (Symbol): The Symbol object to add
        """
        if symbol.is_c_linkage:
            self.symbols[symbol.name] = symbol
            return
        else:
            self.symbols |= {symbol.name: symbol, symbol.demangled_name: symbol}

    def get_symbol(self, symbol_name: str) -> Symbol:
        """Gets the Symbol object that matches the symbol name.

        Args:
            symbol_name (str): String that represents the symbol in C linkage format or for C++ symbols, the Itanium ABI specified mangled or demangled format.

        Returns:
            Symbol: Object that represents the symbol's attributes.
        """
        return self.symbols[symbol_name]

    def has_symbol(self, symbol_name: str) -> bool:
        return symbol_name in self.symbols.keys()

    def dump_nm(self, object_file: ObjectFile, io: IO, *args: str | PathLike) -> IO:
        """
        Dumps the output from binutils's nm.exe to a .txt file.

        Returns:
        TextIOWrapper: Result from the stdout
        """
        args = (self.binutils.NM, object_file) + args
        subprocess.call(args, stdout=io)
        io.seek(0)
        return io

    def dump_objdump(self, object_path: ObjectFile, io: IO, *args: str | PathLike) -> IO:
        """Dumps the output from DevKitPPC's powerpc-eabi-objdump.exe to a .txt file"""
        args = (self.binutils.OBJDUMP, object_path) + args
        subprocess.call(args, stdout=io)
        io.seek(0)
        return io

    def dump_readelf(self, object_path: ObjectFile, io: IO, *args: str | PathLike) -> IO:
        """Dumps the output from DevKitPPC's powerpc-eabi-readelf.exe to a .txt file"""
        args = (self.binutils.READELF, object_path) + args
        subprocess.call(args, stdout=io)
        io.seek(0)
        return io

    def find_missing_symbols(self) -> None:
        # Load symbols from a file. Supports recognizing demangled c++ symbols
        Logger.info(f"{ORANGE}Loading manually defined symbols...")
        for file in self.symbols_folder.find_files(".txt", recursive=True):
            with open(file, "r") as f:
                lines = f.readlines()

            section = "." + file.stem
            for line in lines:
                line = line.rstrip().partition("//")[0]
                if line:
                    name, address = line.split(" = ")
                    if name == "sys":
                        pass
                    if self.has_symbol(name):
                        symbol = self.get_symbol(name)
                        if symbol.source:  # skip this symbol because we are overriding it
                            continue
                        symbol.hex_address = address
                        # symbol.is_absolute = True
                        symbol.section = section

    def find_symbols_nm(self, object_file: ObjectFile):
        with self.dump_folder.make_filepath(object_file.path.stem + ".nm").open_as_text() as nm_dump:
            self.dump_nm(object_file, nm_dump)
            Logger.info(f'{ANALYZING} "{nm_dump.name}"')
            for line in nm_dump.readlines():
                type, symbol_name = line[8:].strip().split(" ")
                if type == "U":
                    continue
                if self.has_symbol(symbol_name):
                    continue
                else:
                    symbol = Symbol(symbol_name, None, type,0)
                
                if not symbol.source:
                    symbol.source = object_file.source_name
                self.add_symbol(symbol)

    def find_symbols_readelf(self, object_file: ObjectFile):
        with self.dump_folder.open_file_as_text(f"{object_file.path.stem}.readelf") as readelf_dump:
            self.dump_readelf(object_file, readelf_dump, "-a", "--wide", "--debug-dump")
            Logger.info(f'{ANALYZING} "{readelf_dump.name}"')
            section_map = {}

            while "  [ 0]" not in readelf_dump.readline():
                continue

            id = 1
            while not (line := readelf_dump.readline()).startswith("Key"):
                section_map[id] = line[7:].strip().split(" ")[0]
                id += 1
            while "Num" not in readelf_dump.readline():
                continue
            readelf_dump.readline()
            while (line := readelf_dump.readline()) != "\n":
                num, address, size, type, bind, vis, ndx, *name = line.split()
                symbol_name = name[0]
                if size == "0":
                    continue
                elif self.has_symbol(symbol_name):
                    symbol = self.get_symbol(symbol_name)
                    symbol.hex_address = "0x" + address
                    symbol.size = int(size)
                    if not symbol.source:
                        symbol.source = object_file
                    if ndx == "ABS":
                        continue
                    symbol.section = section_map[int(ndx)]

    def dump_extras(self, object_file: ObjectFile):
        with self.dump_folder.open_file_as_text(f"{object_file.path.stem}.objdump") as objdump:
            self.dump_objdump(object_file, objdump, "-tSr", "-C")
