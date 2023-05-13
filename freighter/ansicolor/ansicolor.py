import sys
from typing import overload

from enum import StrEnum
from functools import cache
from dataclasses import dataclass, field


@dataclass
class Color:
    _red: float = field(init=False, repr=False)
    _green: float = field(init=False, repr=False)
    _blue: float = field(init=False, repr=False)
    _hue: float = field(init=False, repr=False)
    _saturation: float = field(init=False, repr=False)
    _luminance: float = field(init=False, repr=False)

    @overload
    def __init__(self, red: int, green: int, blue: int) -> None:
        ...

    @overload
    def __init__(self, red: float, green: float, blue: float) -> None:
        ...

    def __init__(self, red: int | float, green: int | float, blue: int | float) -> None:
        if isinstance(red, int):
            self._red = max(0, min(1, float(red / 255)))
        if isinstance(green, int):
            self._green = max(0, min(1, float(green / 255)))
        if isinstance(blue, int):
            self._blue = max(0, min(1, float(blue / 255)))
        self._recalculate_hsl()

    @property
    def red(self) -> float:
        return self._red

    @red.setter
    def red(self, red: int | float):
        if isinstance(red, float):
            self._red = max(0, min(1, red))
        else:
            red = max(255, min(0, red))
            self._red = float(red / 255)
        self._recalculate_hsl()

    @property
    def green(self):
        return self._green

    @green.setter
    def green(self, green: int | float):
        if isinstance(green, float):
            self._green = max(0, min(1, green))
        else:
            red = max(255, min(0, green))
            self._green = float(red / 255)
        self._recalculate_hsl()

    @property
    def blue(self):
        return self._blue

    @blue.setter
    def blue(self, blue: int | float):
        if isinstance(blue, float):
            self._blue = max(0, min(1, blue))
        else:
            blue = max(255, min(0, blue))
            self._blue = float(blue / 255)
        self._recalculate_hsl()

    @property
    def hue(self) -> float:
        return self._hue

    @hue.setter
    def hue(self, hue: float) -> None:
        self.hue = max(0, min(1, hue))
        self._recalculate_color()

    @property
    def saturation(self) -> float:
        return self._saturation

    @saturation.setter
    def saturation(self, saturation: float) -> None:
        self.saturation = max(0, min(1, saturation))
        self._recalculate_color()

    @property
    def luminance(self) -> float:
        return self._luminance

    @luminance.setter
    def luminance(self, luminance: float) -> None:
        self._luminance = max(0, min(1, luminance))
        self._recalculate_color()

    @property
    def hex(self) -> str:
        return f"#{int(self._red * 255):02x}{int(self._green * 255):02x}{int(self._blue * 255):02x}"

    @property
    def rgb(self):
        return int(self._red * 255), int(self._green * 255), int(self._blue * 255)

    def _recalculate_hsl(self) -> None:
        max_value = max(self._red, self._green, self._blue)
        min_value = min(self._red, self._green, self._blue)
        delta = max_value - min_value

        # calculate hue
        if delta == 0:
            self._hue = 0
        elif max_value == self._red:
            self._hue = ((self._green - self._blue) / delta) % 6
        elif max_value == self._green:
            self._hue = (self._blue - self._red) / delta + 2
        else:
            self._hue = (self._red - self._green) / delta + 4
        self._hue *= 60

        # calculate lightness and saturation
        self._luminance = (max_value + min_value) / 2
        if delta == 0:
            self._saturation = 0
        else:
            self._saturation = delta / (1 - abs(2 * self._luminance - 1))

    def _recalculate_color(self) -> None:
        c = (1 - abs(2 * self._luminance - 1)) * self._saturation
        x = c * (1 - abs((self._hue / 60) % 2 - 1))
        m = self._luminance - c / 2

        if self._hue < 60:
            r, g, b = c, x, 0
        elif self._hue < 120:
            r, g, b = x, c, 0
        elif self._hue < 180:
            r, g, b = 0, c, x
        elif self._hue < 240:
            r, g, b = 0, x, c
        elif self._hue < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x

        self._red, self._green, self._blue = (r + m), (g + m), (b + m)


class AnsiAttribute(StrEnum):
    RESET = "\x1b[0m"
    BOLD = "\x1b[1m"
    DARK = "\x1b[2m"
    ITALIC = "\x1b[3m"
    UNDERLINE = "\x1b[4m"
    BLINK = "\x1b[5m"
    REVERSE = "\x1b[7m"
    CONCEALED = "\x1b[8m"
    STRIKETHROUGH = "\x1b[9m"


class AnsiColor(StrEnum):
    NONE = AnsiAttribute.RESET
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


class AnsiBrightColor(StrEnum):
    BLACK = "\033[90m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"


@dataclass
class AnsiTrueColor(Color):
    ansi_code: str

    @overload
    def __init__(self, red: int, green: int, blue: int, is_background: bool = False) -> None:
        ...

    @overload
    def __init__(self, red: float, green: float, blue: float, is_background: bool = False) -> None:
        ...

    def __init__(self, red: int | float, green: int | float, blue: int | float, is_background: bool = False) -> None:
        super().__init__(red, green, blue)
        r, g, b = self.rgb
        if is_background:
            self.ansi_code = f"\x1b[48;2;{r};{g};{b}m"
        else:
            self.ansi_code = f"\x1b[38;2;{r};{g};{b}m"

    def __str__(self):
        return self.ansi_code

    def __repr__(self):
        return f"AnsiTrueColor({self.ansi_code})"


class AnsiBackground(StrEnum):
    NONE = AnsiAttribute.RESET
    BLACK = "\x1b[40m"
    RED = "\x1b[41m"
    GREEN = "\x1b[42m"
    YELLOW = "\x1b[43m"
    BLUE = "\x1b[44m"
    MAGENTA = "\x1b[45m"
    CYAN = "\x1b[46m"
    WHITE = "\x1b[47m"


class AnsiBrightBackground(StrEnum):
    BLACK = "\x1b[100m"
    RED = "\x1b[101m"
    GREEN = "\x1b[102m"
    YELLOW = "\x1b[103m"
    BLUE = "\x1b[104m"
    MAGENTA = "\x1b[105m"
    CYAN = "\x1b[106m"
    WHITE = "\x1b[107m"


def ansi_format(
    text: str,
    *attributes: AnsiColor | AnsiBrightColor | AnsiTrueColor | AnsiBackground | AnsiBrightBackground | AnsiAttribute,
) -> str:
    for attribute in attributes:
        text = f"{attribute}{text}"
    return f"{text}{AnsiAttribute.RESET}"
