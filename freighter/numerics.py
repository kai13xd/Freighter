from __future__ import annotations

from typing import Self, Protocol, SupportsIndex, SupportsInt, TYPE_CHECKING


from freighter.exceptions import FreighterException

if TYPE_CHECKING:
    from _collections_abc import Buffer


class SupportsTrunc(Protocol):
    def __trunc__(self) -> int:
        ...


class Number(int):
    _min: int
    _max: int

    def __new__(cls, value: int | str | bytes | bytearray | SupportsInt | SupportsIndex | SupportsTrunc = ...) -> Self:
        if isinstance(value, int):
            object = super(Number, cls).__new__(cls, value)
        elif isinstance(value, str) and value.startswith("0x"):
            object = super(Number, cls).__new__(cls, value, 16)
        elif isinstance(value, float):
            object = super(Number, cls).__new__(cls, value.__trunc__())
        else:
            raise FreighterException(f"{value.__class__.__name__} is not a supported type for {cls.__name__}")

        if object < object._min:
            raise FreighterException(f"{object.__class__.__name__} is under range of {object._min}")
        elif object > object._max:
            raise FreighterException(f"{object.__class__.__name__} is over the range of {object._max}")

        return object

    @property
    @classmethod
    def min(cls):
        return cls._min

    @property
    @classmethod
    def max(cls):
        return cls._max

    @property
    def hex(self) -> str:
        return hex(self)

    @property
    def binary(self) -> str:
        return bin(self)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self}) {self.hex}"

    def __str__(self) -> str:
        return str(int(self))

    def __add__(self, value: int) -> Self:
        return self.__class__(super().__add__(value))

    def __sub__(self, value: int) -> Self:
        return self.__class__(super().__sub__(value))

    def __mul__(self, value: int) -> Self:
        return self.__class__(super().__mul__(value))


class Char(Number):
    _min: int = -127
    _max: int = 127


class UChar(Number):
    _min: int = 0
    _max: int = 255


class Short(Number):
    _min: int = -32768
    _max: int = 32767


class UShort(Number):
    _min: int = 0
    _max: int = 65535


class Int(Number):
    _min: int = -2147483646
    _max: int = 2147483647


class UInt(Number):
    _min: int = 0
    _max: int = 4294967295


class Long(Number):
    _min: int = -9223372036854775808
    _max: int = 9223372036854775807


class ULong(Number):
    _min: int = 0
    _max: int = 18446744073709551615
