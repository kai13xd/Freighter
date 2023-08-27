from io import BytesIO
from os import SEEK_CUR
from struct import pack, unpack
from typing import Any, Generic, Type, cast, get_args


class BinaryFile(BytesIO):
    @property
    def length(self):
        return self.getbuffer().nbytes

    def __init__(self, path: str):
        with open(path, "rb") as f:
            BytesIO.__init__(self, f.read())

    def skip(self, count: int):
        self.seek(count, SEEK_CUR)

    def read_uchar(self):
        return BytesIO.read(self, 1)[0]

    def read_ushort(self):
        data = BytesIO.read(self, 2)
        return data[0] << 8 | data[1]

    def read_uint(self):
        return unpack(">I", BytesIO.read(self, 4))[0]

    def read_bytes(self, size: int):
        return unpack(f">{size}s", BytesIO.read(self, size))[0]

    def read_magic(self):
        return unpack(">4s", BytesIO.read(self, 4))[0]

    def write_uchar(self, val):
        self.write(pack(">B", val))

    def write_ushort(self, val):
        self.write(pack(">H", val))

    def write_uint(self, val):
        self.write(pack(">I", val))

    def write_pad32(self):
        next_aligned_pos = (self.tell() + 0x1F) & ~0x1F
        self.write(b"\x00" * (next_aligned_pos - self.tell()))


class FixedSizeBinaryData:
    size: int
    offset: int
    _bytes: bytearray

    def __init__(self, offset: int, size, string: str = ""):
        self.size = size
        self._bytes = bytearray(size)
        self._type = type
        self.offset = offset
        if string:
            self.data = string

    @property
    def data(self) -> str:
        return self._bytes.decode("ascii").rstrip("\0")

    @data.setter
    def data(self, data: str | bytes):
        if isinstance(data, str):
            bytestring = data.encode("cp1252")
            # if b"\xc2" in bytestring:
            # bytestring = bytestring.replace(b"\xc2", b"")
            self._bytes[0 : len(bytestring)] = bytestring
        else:
            self._bytes[0 : len(data)] = data

    @property
    def bytes(self) -> bytes:
        return self._bytes

    def read(self, file: BinaryFile):
        file.seek(self.offset)
        self._bytes = file.read_bytes(self.size)

    def __repr__(self):
        return f'"{self.data}"'
