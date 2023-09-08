from __future__ import annotations

from collections import defaultdict
from re import Pattern
from typing import TYPE_CHECKING, Protocol, Iterator, BinaryIO, runtime_checkable

from attr import define
from freighter.doltools import *
from freighter.exceptions import FreighterException
from freighter.logging import *
from freighter.path import *
from geckolibs.gct import GeckoCodeTable
from geckolibs.geckocode import AsmInsert, AsmInsertXOR, GeckoCommand, Write16, Write32, WriteBranch, WriteString
from freighter.symbols import DEFAULT_GAMECUBE_ADDRESS_SPACE, Address, Symbol, SymbolManager
from freighter.numerics import UInt
from dolreader.dol import DolFile, TextSection, DataSection

if TYPE_CHECKING:
    from io import TextIOWrapper, BytesIO
    from os import PathLike

    from dolreader.section import DataSection, Section, TextSection
    from freighter.config import GameCubeProfile, ProjectProfile, SwitchProfile
    from freighter.filemanager import SourceFile


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


class Hook(Protocol):
    address: Address[UInt]
    symbol_name: str | None = None
    data: Any

    @property
    def length(self):
        return len(self.data)

    def _resolve(self, symbol_manager: SymbolManager) -> bool:
        ...

    def _apply(self, dol: DolFile) -> bool:
        ...


class SupportsGeckoCommand(Protocol):
    def write_geckocommand(self, f: TextIOWrapper) -> bool:
        ...


@runtime_checkable
class SupportsPragmaHook(Hook, Protocol):
    address: Address

    def __repr__(self) -> str:
        if not self.data:
            return f"[{self.__class__.__name__}] '{self.symbol_name}' -> {self.address.hex_virtual_address}"
        elif isinstance(self, StringHook):
            return f'[{self.__class__.__name__}] "{self.data.decode("ascii")}" -> {self.address.hex_virtual_address}'
        else:
            return f"[{self.__class__.__name__}] ({self.symbol_name}) -> {self.address.hex_virtual_address}"


class BranchHook(SupportsPragmaHook, SupportsGeckoCommand):
    def __init__(self, address: Address[UInt], symbol_name: str, lk_bit: bool = False) -> None:
        self.address = address
        self.symbol_name: str = symbol_name
        self.lk_bit = lk_bit
        self.data = None

    def _resolve(self, symbol_manager: SymbolManager) -> bool:
        if not symbol_manager.has_symbol(self.symbol_name):
            return False
        else:
            symbol = symbol_manager.get_symbol(self.symbol_name)
            if symbol.address:
                self.data = symbol.address
                return True
            return False

    def _apply(self, dol: DolFile) -> bool:
        if self.data and dol.is_mapped(self.address.virtual_address):
            dol.seek(self.address.virtual_address)
            dol.write(assemble_branch(self.address, self.data, LK=self.lk_bit))
            return True
        return False

    def write_geckocommand(self, f) -> bool:
        if self.data:
            gecko_command = WriteBranch(self.data, self.address.virtual_address, isLink=self.lk_bit)
            f.write(gecko_command.as_text() + "\n")
            return True
        return False


class PointerHook(SupportsPragmaHook, SupportsGeckoCommand):
    def __init__(self, address: Address[UInt], symbol_name: str):
        self.address = address
        self.symbol_name: str = symbol_name
        self.data: int | None = None

    def _resolve(self, symbol_manager: SymbolManager) -> bool:
        if not symbol_manager.has_symbol(self.symbol_name):
            return False
        else:
            symbol = symbol_manager.get_symbol(self.symbol_name)
            if symbol.address:
                self.data = symbol.address.virtual_address
                return True
            return False

    def _apply(self, dol: DolFile) -> bool:
        if self.data and dol.is_mapped(self.address.virtual_address):
            dol.write_uint32(self.address.virtual_address, self.data)
            return True
        return False

    def write_geckocommand(self, f: TextIOWrapper) -> bool:
        if self.data:
            gecko_command = Write32(self.data, self.address.virtual_address)
            f.write(gecko_command.as_text() + "\n")
            return True
        return False


class StringHook(SupportsPragmaHook, SupportsGeckoCommand):
    def __init__(self, address: Address[UInt], string: str, encoding: str = "ascii"):
        self.address = address
        self.data = string.encode(encoding) + b"\0"
        self.symbol_name = None
        self.encoding = encoding
        self.string_length = len(self.data)

    def _resolve(self, symbol_manager: SymbolManager) -> bool:
        if not self.data:
            return False
        return True

    def _apply(self, dol: DolFile) -> bool:
        if not dol.is_mapped(self.address.virtual_address):
            return False

        original_string = dol.read_c_string(self.address.virtual_address).encode(encoding=self.encoding) + b"\0"
        original_string_length = len(original_string)
        if self.length > original_string_length:
            Logger.warn(
                f'[StringHook] "{self.data.decode("ascii")}" overwrites "{original_string.decode("ascii")}" by {hex(self.length - original_string_length)} bytes!'
                "This will overwrite past the bounds of the original string!"
            )

            return False

        while self.length < original_string_length:
            self.data += b"\x00"

        dol.seek(self.address.virtual_address)
        dol.write(self.data)
        return True

    def write_geckocommand(self, f) -> bool:
        gecko_command = WriteString(self.data, self.address.virtual_address)
        f.write(gecko_command.as_text() + "\n")
        return True


class FileHook(Hook, SupportsGeckoCommand):
    def __init__(self, address, filepath, start, end, max_size):
        self.address = address
        self.data = bytearray()
        self.filepath = filepath
        self.start = start
        self.end = end
        self.max_size = max_size

    def _resolve(self, symbol_manager: SymbolManager) -> bool:
        try:
            with open(self.filepath, "rb") as f:
                if self.end == None:
                    self.data = f.read()[self.start :]
                else:
                    self.data = f.read()[self.start : self.end]
                if self.max_size != None:
                    if len(self.data) > self.max_size:
                        Logger.error(f'"{self.filepath}" exceeds {self.max_size} bytes!')
                    else:
                        while len(self.data) < self.max_size:
                            self.data += b"\x00"
        except OSError:
            Logger.error(f'"{self.filepath}" could not be opened!')
            return False
        return True

    def _apply(self, dol: DolFile) -> bool:
        if dol.is_mapped(self.address.virtual_address):
            dol.seek(self.address.virtual_address)
            dol.write(self.data)
            return True
        return False

    def write_geckocommand(self, f) -> bool:
        gecko_command = WriteString(self.data, self.address.virtual_address)
        f.write(gecko_command.as_text() + "\n")
        return True


class NOPHook(SupportsPragmaHook):
    def __init__(self, address):
        self.address = address
        self.data = 0x60000000

    def _resolve(self, symbol_manager: SymbolManager) -> bool:
        return True

    def _apply(self, dol: DolFile) -> bool:
        if dol.is_mapped(self.address.virtual_address):
            dol.write_uint32(self.address.virtual_address, self.data)
            return True
        return False


class Immediate16Hook(Hook):
    def __init__(self, address, symbol_name, modifier):
        self.address = address
        self.symbol_name = symbol_name
        self.modifier = modifier

    def _resolve(self, symbols):
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
                Logger.error('Unknown modifier: "{}"'.format(self.modifier))
            self.data = mask_field(self.data, 16, True)

    def _apply(self, dol: DolFile):
        if self.data and dol.is_mapped(self.address.virtual_address):
            dol.write_uint16(self.address.virtual_address, self.data)
            return True

    def write_geckocommand(self, f):
        if self.data:
            gecko_command = Write16(self.data, self.address.virtual_address)
            f.write(gecko_command.as_text() + "\n")
            return True


# Paired-Singles Load and Store have a 12-bit immediate field, unlike normal load/store instructions
class Immediate12Hook(Hook):
    def __init__(self, address, w, i, symbol_name, modifier):
        self.address = address
        self.w = w
        self.i = i
        self.symbol_name = symbol_name
        self.modifier = modifier

    def _resolve(self, symbols):
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
                Logger.error('Unknown modifier: "{}"'.format(self.modifier))
            self.data = mask_field(self.data, 12, True)
            self.data |= mask_field(self.i, 1, False) << 12
            self.data |= mask_field(self.w, 3, False) << 13

    def _apply(self, dol: DolFile):
        if self.data and dol.is_mapped(self.address.virtual_address):
            dol.write_uint16(self.address.virtual_address, self.data)
            return True

    def write_geckocommand(self, f):
        if self.data:
            gecko_command = Write16(self.data, self.address.virtual_address)
            f.write(gecko_command.as_text() + "\n")
            return True


class PatcherProtocol(Protocol):
    def __init__(self, profile: ProjectProfile):
        ...

    def apply(self) -> bool:
        ...


class GeckoPatcher(PatcherProtocol):
    def __init__(self, profile: GameCubeProfile, project_name: str):
        self.gecko_folder = profile.GeckoFolder
        # self.gecko_table = GeckoCodeTable(profile.GameID, project_name)

        self.ignored_gecko_files = profile.IgnoredGeckoFiles
        self.injection_address = profile.InjectionAddress

    @performance_profile
    def apply(self, dol_file: DolFile, final_binary: BytesIO) -> bool:
        Logger.info("Applying Gecko patches...")
        while (final_binary.getbuffer().nbytes % 4) != 0:
            final_binary.write(b"\x00")

        Logger.info(f"{GREEN}Gecko Codes{AnsiAttribute.RESET}")
        for gecko_txt in self.gecko_folder.find_files(".txt", recursive=True):
            if gecko_txt in self.ignored_gecko_files:
                continue
            gecko_table = GeckoCodeTable.from_text(open(gecko_txt, "r").read())

            for gecko_code in gecko_table:
                if gecko_code.is_enabled():
                    Logger.info(f"{GREEN}ENABLED {CYAN} ${gecko_code.name}")
                    for gecko_command in gecko_code:
                        if gecko_command.codetype not in SupportedGeckoCodetypes:
                            Logger.info(f"{ORANGE}Includes unsupported codetypes:")
                else:
                    Logger.info(f"{RED}DISABLED{CYAN} ${gecko_code.name}")

                vaddress = self.injection_address + final_binary.getbuffer().nbytes
                gecko_data = bytearray()
                for gecko_command in [item for item in gecko_code if isinstance(item, AsmInsert) or isinstance(item, AsmInsertXOR)]:
                    dol_file.seek(gecko_command._address + 0x80000000)
                    write_branch(dol_file, Address[UInt](DEFAULT_GAMECUBE_ADDRESS_SPACE, UInt(vaddress + len(gecko_data))))
                    gecko_data += bytes(gecko_command.value)[:-4]
                    gecko_data += assemble_branch(
                        Address[UInt](DEFAULT_GAMECUBE_ADDRESS_SPACE, UInt(vaddress + len(gecko_data))), Address[UInt](DEFAULT_GAMECUBE_ADDRESS_SPACE, UInt(gecko_command._address + 4 | 0x80000000))
                    )
                final_binary.write(gecko_data)
            gecko_table.apply(dol_file)
        return True


class GameCubeHookPatcher(PatcherProtocol):
    def __init__(self, profile: GameCubeProfile, symbol_manager: SymbolManager):
        self.symbol_manager = symbol_manager
        self.hooks = list[Hook]()
        self.ignored_hooks = profile.IgnoredHooks
        self.injection_address = profile.InjectionAddress

        self.duplicates = defaultdict[Address[UInt], list[tuple[Hook, str | None, int | None]]]()
        self.unique_addresses = set[Address[UInt]]()

        if profile.StringHooks:
            for address, string in profile.StringHooks.items():
                self.add_hook(StringHook(Address(DEFAULT_GAMECUBE_ADDRESS_SPACE, UInt(address)), string))

    def add_hook(self, hook: Hook, source_file=None, line_number=None):
        self.hooks.append(hook)
        self.check_duplicate_hooks(hook, source_file, line_number)

    def check_duplicate_hooks(self, hook: Hook, source_file: str | None, line_number: int | None):
        # May help fix stupid mistakes
        if hook.address not in self.unique_addresses:
            self.unique_addresses.add(hook.address)
        else:
            self.duplicates[hook.address].append((hook, source_file, line_number))

    def assert_duplicates(self):
        if self.duplicates:
            bad_hooks_string = ""
            for address, hook_info in self.duplicates.items():
                bad_hooks_string += f"{address.hex_virtual_address}\n"
                for hook, source_file, line_number in hook_info:
                    bad_hooks_string += f'\t{hook.symbol_name} in "{source_file}:{line_number}"\n'
            raise FreighterException(f"BranchHooks referencing different function symbols were found hooking into the same target address!\n{bad_hooks_string}")

    @performance_profile
    def apply(self, dol_file: DolFile, final_binary: BytesIO) -> bool:
        Logger.info("Applying hooks...")
        unresolved_hooks = list[Hook]()
        for hook in self.hooks:
            if not hook._resolve(self.symbol_manager):
                unresolved_hooks.append(hook)
        if unresolved_hooks:
            raise HookResolutionException(self.symbol_manager, unresolved_hooks)

        for hook in self.hooks:
            hook._apply(dol_file)
            Logger.info(hook)

        if final_binary.getbuffer().nbytes > 0:
            new_section: Section
            if len(dol_file.textSections) <= DolFile.MaxTextSections:
                new_section = TextSection(self.injection_address, final_binary)
            elif len(dol_file.dataSections) <= DolFile.MaxDataSections:
                new_section = DataSection(self.injection_address, final_binary)
            else:
                raise FreighterException("DOL is full! Cannot allocate any new sections.")
            dol_file.append_section(new_section)

        return True

    @performance_profile
    def find_pragma_hooks(self, source_files: list[SourceFile]):
        for source_file in source_files:
            if source_file in self.ignored_hooks:
                Logger.debug(f'Ignored parsing pragma injections for "{source_file}".')
                continue

            debug_hookstr = f'Created Hooks from "{source_file}":\n'
            is_c_linkage = False
            if source_file.path.suffix == ".c":
                is_c_linkage = True
            with open(source_file, "r", encoding="utf8") as f:
                lines = enumerate(f.readlines())
            for line_number, line in lines:
                line = line.split("//")[0].strip()
                if not line.startswith("#p"):
                    continue
                line = line.removeprefix("#pragma ")
                if line.startswith("hook"):
                    branch_type, *addresses = line.removeprefix("hook ").split(" ")
                    line_number, lines, function_symbol = self.recreate_gcc_symbol(source_file, lines, is_c_linkage)
                    if branch_type == "bl":
                        for address in addresses:
                            address = Address[UInt](DEFAULT_GAMECUBE_ADDRESS_SPACE, UInt(address))
                            hook = BranchHook(address, function_symbol, True)
                            debug_hookstr += f"{hook} at line {line_number}\n"
                            self.add_hook(hook)
                    elif branch_type == "b":
                        for address in addresses:
                            address = Address[UInt](DEFAULT_GAMECUBE_ADDRESS_SPACE, UInt(address))
                            hook = BranchHook(address, function_symbol)
                            debug_hookstr += f"{hook} at line {line_number}\n"
                            self.add_hook(hook)
                    else:
                        raise FreighterException(f"{branch_type} is not a valid supported branch type for #pragma hook!\n{line} Found in {CYAN}{source_file}{ORANGE} on line number {line_number + 1}")
                elif line.startswith("inject"):
                    inject_type, *addresses = line.removeprefix("inject ").split(" ")
                    if inject_type == "pointer":
                        line_number, lines, function_symbol = self.recreate_gcc_symbol(source_file, lines, is_c_linkage)
                        for address in addresses:
                            address = Address[UInt](DEFAULT_GAMECUBE_ADDRESS_SPACE, UInt(address))
                            hook = PointerHook(address, function_symbol)
                            debug_hookstr += f"{hook} at line {line_number}\n"
                            self.add_hook(hook)
                    elif inject_type == "string":
                        for address in addresses:
                            inject_string = ""
                            address = Address[UInt](DEFAULT_GAMECUBE_ADDRESS_SPACE, UInt(address))
                            hook = StringHook(address, inject_string)
                            debug_hookstr += f"{hook} at line {line_number}\n"
                            self.add_hook(hook)
                    else:
                        raise FreighterException(f"Arguments for {PURPLE}{line}{CYAN} are incorrect!\n" + f"{line} Found in {CYAN}{source_file}{ORANGE} on line number {line_number + 1}")
                elif line.startswith("nop"):
                    addresses = line.removeprefix("nop ").split(" ")
                    for address in addresses:
                        address = Address[UInt](DEFAULT_GAMECUBE_ADDRESS_SPACE, UInt(address))
                        hook = NOPHook(address)
                        debug_hookstr += f"{hook} at line {line_number}\n"
                        self.add_hook(hook)

            Logger.debug(debug_hookstr + "\n")
            self.assert_duplicates()

    re_function_name: Pattern[str] = re.compile(r".* (\w*(?=\()).*")
    re_parameter_names: Pattern[str] = re.compile(r"([^\]&*]\w+)(,|(\)\[)|(\)\()|\))")
    re_flip_const: Pattern[str] = re.compile(r"(const) ([:\[\]<>\w]*[^ *&])")
    re_flip_volatile: Pattern[str] = re.compile(r"(volatile) ([:\[\]<>\w]*[^ *&])")
    re_flip_const_volatile: Pattern[str] = re.compile(r"(const volatile) ([:\[\]<>\w]*[^ *&])")

    def recreate_gcc_symbol(self, source_file: SourceFile, lines: Iterator[tuple[int, str]], is_c_linkage: bool = False) -> tuple[int, Iterator[tuple[int, str]], str]:
        """TODO: This function doesnt account for transforming typedefs/usings back to their primitive or original typename"""
        """Also doesn't account for namespaces that arent in the function signature"""

        while True:
            line_number, line = next(lines)
            if 'extern "C"' in line:
                is_c_linkage = True
            if not line:
                continue
            if "(" in line:
                line = line.split("//")[0].strip()
                line = line.rsplit("{")[0]
                if is_c_linkage:
                    return line_number, lines, self.re_function_name.sub(r"\1", line, 1)
                try:
                    result: list[str] = re.findall(r"(.*)(\(.*\))", line)[0]
                    function_name, signature = result
                    namespace_parts = function_name.split("::")
                    if len(namespace_parts) > 1 and namespace_parts[-1] == namespace_parts[-2]:
                        Logger.info(f"'{line}' is a constructor")
                    else:
                        function_name = function_name.rsplit(" ", -1)[-1]
                except:
                    raise BadFunctionSignatureExecption(source_file, line_number, line)
                if signature == "()":
                    return line_number, lines, function_name + signature
                signature = self.re_parameter_names.sub(r"\2", signature)

                if "const " in signature or "volatile " in signature:
                    parameters = signature.split(",")
                    parameters[0] = parameters[0][1:]
                    parameters[-1] = parameters[-1][:-1]
                    result = []
                    for parameter in parameters:
                        parameter = parameter.lstrip()
                        if "volatile const" in parameter:
                            parameter = parameter.replace("volatile const", "const volatile")
                        if "const volatile" in parameter:
                            parameter = self.re_flip_const_volatile.sub(r"\2 \1", parameter)
                        elif "volatile" in parameter:
                            parameter = self.re_flip_volatile.sub(r"\2 \1", parameter)
                        else:
                            # c++filt returns demangled symbols with 'type const*' or 'type const&' rather than 'const type*' or 'const type&'
                            parameter = self.re_flip_const.sub(r"\2 \1", parameter)
                        # Passing types by value is implicitly const. c++filt returns a demangled symbol with const removed
                        if parameter[-1] not in ["*", "&"]:
                            parameter = parameter.replace("const", "").replace("volatile", "").rstrip()
                        result.append(parameter)
                    signature = f"({', '.join(result)})"

                return line_number, lines, function_name + signature


class HookResolutionException(Exception):
    def __init__(self, symbol_manager: SymbolManager, unresolved_hooks: list[Hook]):
        bad_hooks = "\n"

        for hook in unresolved_hooks:
            source_file = ""
            if hook.symbol_name:
                source_file = symbol_manager.get_symbol(hook.symbol_name).source
            bad_hooks += f'{ORANGE}{hook.symbol_name}{AnsiAttribute.RESET} found in {CYAN}"{source_file}"\n'

        message = f"""{ERROR} Freighter could not resolve hook addresses for the given symbols:
{bad_hooks}{AnsiAttribute.RESET}
Possible Reasons:{ORANGE}
    • If this is a external C++ Symbol, it's symbol definition may be missing from the "symbols"{ORANGE} folder
    • Freighter did not parse the function signature below the #pragma hook into the demangled Itanium ABI format and the lookup to get the target branch address failed.
    • The cache Freighter uses for incremental builds is faulty and needs to be reset. Use -cleanup option to reset this cache.
    • The compiler optimized out the function by inlining or completely discarding it therefore the symbol does not exist."""

        super().__init__(message)


class BadFunctionSignatureExecption(FreighterException):
    def __init__(self, source_file, line_number: int, line: str):
        message = f"""{ORANGE}Bad function signature!
'{line}' found on line {line_number} in '{source_file}'

When processing #pragma inject or pointer Freighter requires:
• {CYAN}The pragma to be placed above the function definition/forward declaration.
• {CYAN}The function defintion or forward declaration to be defined outside the class within a source file.
• {CYAN}The function signature must be on a single line.

Format: {WHITE}[[{CYAN}Attributes{WHITE}]] {PURPLE}CV-type qualifiers {GREEN}Decl-Specifiers {CYAN}ReturnType {GREEN}Namespaces{WHITE}::{RED}Class{WHITE}::{YELLOW}FunctionName{WHITE}({MAGENTA}Arguments{WHITE})
Example: {WHITE}[[{CYAN}gnu::always_inline{WHITE}]] {PURPLE}volatile {GREEN}const {CYAN}void* {GREEN}FooNamespace{WHITE}::{RED}BarClass{WHITE}::{YELLOW}myFunction{MAGENTA}{WHITE}({MAGENTA}int arg1{WHITE}, {MAGENTA}void(*functionPtr)(int){WHITE}, {MAGENTA}...{WHITE}) {PURPLE}const"""
        super().__init__(message)
