from .binaryfile import *
from ..exceptions import FreighterException


class BNR(BinaryFile):
    def __init__(self, path: str = ""):
        if path:
            BinaryFile.__init__(self, path)
        self.magic = FixedSizeBinaryData(0x0, 0x4, "BNR1")
        self.padding = FixedSizeBinaryData(0x4, 0x1C)
        self.banner_image = FixedSizeBinaryData(0x1F, 0x1800)
        self.title = FixedSizeBinaryData(0x1820, 0x20)
        self.short_maker = FixedSizeBinaryData(0x1840, 0x20)
        self.gamename = FixedSizeBinaryData(0x1860, 0x40)
        self.maker = FixedSizeBinaryData(0x18A0, 0x40)
        self.description = FixedSizeBinaryData(0x18E0, 0x80)

    @classmethod
    def read(cls, path: str):
        bnr = cls(path)
        if bnr.length > 6496:
            raise FreighterException("BNR file size mismatch. BNR files are always 0x1960 or 6496 bytes!")
        bnr.magic.read(bnr)
        bnr.banner_image.read(bnr)
        bnr.title.read(bnr)
        bnr.short_maker.read(bnr)
        bnr.gamename.read(bnr)
        bnr.maker.read(bnr)
        bnr.description.read(bnr)
        return bnr

    def save(self, filepath: str) -> None:
        with open(filepath, "wb") as f:
            f.write(self.magic.bytes)
            f.write(self.padding.bytes)
            f.write(self.banner_image.bytes)
            f.write(self.title.bytes)
            f.write(self.short_maker.bytes)
            f.write(self.gamename.bytes)
            f.write(self.maker.bytes)
            f.write(self.description.bytes)
