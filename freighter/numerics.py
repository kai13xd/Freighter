from dataclasses import dataclass

from freighter.exceptions import FreighterException


@dataclass
class Number(int):
    _min: int
    _max: int

    def __init__(self, value: int):
        if value < self._min:
            raise FreighterException(f"Char is over range of {min}")
        elif value > self._max:
            raise FreighterException(f"Char is under the range of {max}")
        self = value

    @property
    def min(self):
        return self._min

    @property
    def max(self):
        return self._max

    @property
    def hex(self) -> str:
        return hex(self)

    @property
    def binary(self) -> str:
        return bin(self)

    def __repr__(self) -> str:
        return f"{str(int(self))} = {self.hex}"

    def __str__(self) -> str:
        return str(int(self))


class Char(Number):
    _min: int = -128
    _max: int = 127

    def __init__(self, value: int | Number):
        Number.__init__(self, value)


class Int(Number):
    _min: int = -2147483646
    _max: int = 2147483647

    def __init__(self, value: int | Number):
        Number.__init__(self, value)


class UInt(Number):
    _min: int = 0
    _max: int = 4294967295

    def __init__(self, value: int | Number):
        Number.__init__(self, value)
