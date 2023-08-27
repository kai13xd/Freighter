## Implementation of a yaz0 decoder/encoder in Python, by Yoshi2
## Using the specifications in http://www.amnoid.de/gc/yaz0.txt

import hashlib
import math
import os
import re
import struct
from io import BytesIO
from timeit import default_timer as time
from typing import BinaryIO


def read_uint32(f):
    return struct.unpack(">I", f.read(4))[0]


def read_uint16(f):
    # return unpack(">H", f.read(2))[0]
    data = f.read(2)
    return data[0] << 8 | data[1]


def read_uint8(f):
    return f.read(1)[0]


def write_limited(f, data, limit):
    if f.tell() >= limit:
        pass
    else:
        f.write(data)


class yaz0:
    def __init__(self, inputobj: BytesIO, outputobj: BytesIO | None = None, compress=False):
        self.compressFlag = compress
        self.fileobj = inputobj

        if outputobj == None:
            self.output = BytesIO()
        else:
            self.output = outputobj

        # A way to discover the total size of the input data that
        # should be compatible with most file-like objects.
        self.fileobj.seek(0, 2)
        self.maxsize = self.fileobj.tell()
        self.fileobj.seek(0)

        if self.compressFlag == False:
            self.header = self.fileobj.read(4)
            if self.header != b"Yaz0":
                raise RuntimeError("File is not Yaz0-compressed! Header: {0}".format(self.header))

            self.decompressedSize = struct.unpack(">I", self.fileobj.read(4))[0]
            nothing = self.fileobj.read(8)  # Unused data

        else:
            self.output.write(b"Yaz0")

            self.output.write(struct.pack(">I", self.maxsize))
            self.output.write(b"\0" * 8)

    def decompress(self):
        fileobj = self.fileobj
        output = self.output

        while output.tell() < self.decompressedSize:
            # The codebyte tells us what we need to do for the next 8 steps.
            codeByte = fileobj.read(1)
            # print("codeByte {0} at position {1}".format(codeByte, fileobj.tell()))

            # if fileobj.tell() >= self.maxsize:
            #     # We have reached the end of the compressed file, but the amount
            #     # of written data does not match the decompressed size.
            #     # This is generally a sign of the compressed file being invalid.
            #     raise RuntimeError("The end of file has been reached." "{0} bytes out of {1} written.".format(output.tell(), self.decompressedSize))

            for bit_number, bit in enumerate(self.__bit_iter__(codeByte)):
                if bit:
                    ## The bit is set to 1, we do not need to decompress anything.
                    ## Write the data to the output.
                    byte = fileobj.read(1)

                    output.write(byte)
                    # if output.tell() < self.decompressedSize:
                    #     output.write(byte)
                    # else:
                    #     print("Decompressed size already reached. " "Disregarding Byte {0}, ascii: [{1}]".format(hex(ord(byte)), byte))

                else:
                    if output.tell() >= self.decompressedSize:
                        # print(
                        #     "Bit at position {0} in byte {1} tells us that there "
                        #     "is more data to be decompressed, but we have reached "
                        #     "the decompressed size!".format(bit_number, codeByte)
                        # )
                        continue

                    ## Time to work some decompression magic. The next two bytes will tell us
                    ## where we find the data to be copied and how much data it is.
                    byte1 = ord(fileobj.read(1))
                    byte2 = ord(fileobj.read(1))

                    byteCount = byte1 >> 4
                    byte1_lowerNibble = byte1 & 0xF

                    if byteCount == 0:
                        # We need to read a third byte which tells us
                        # how much data we have to read.
                        byte3 = ord(fileobj.read(1))

                        byteCount = byte3 + 0x12
                    else:
                        byteCount += 2

                    moveDistance = (byte1_lowerNibble << 8) | byte2

                    normalPosition = output.tell()
                    moveTo = normalPosition - (moveDistance + 1)

                    # if moveTo < 0:
                    #     raise RuntimeError(
                    #         "Invalid Seek Position: Trying to move from " "{0} to {1} (MoveDistance: {2})".format(normalPosition, moveTo, moveDistance + 1)
                    #     )

                    # We move back to a position that has the data we will copy to the front.
                    output.seek(moveTo)
                    toCopy = bytearray(output.read(byteCount))

                    if len(toCopy) < byteCount:
                        # The data we have read is less than what we should read,
                        # so we will repeat the data we have read so far until we
                        # have reached the bytecount.
                        newCopy = bytearray(toCopy)
                        diff = byteCount - len(toCopy)

                        # Append full copy of the current string to our new copy
                        for i in range(diff // len(toCopy)):
                            newCopy += toCopy

                        # Append the rest of the copy to the new copy
                        newCopy += toCopy[: (diff % len(toCopy))]
                        toCopy = newCopy

                    # print "Copying: '{0}', {1} bytes at position {2}".format(toCopy, byteCount, moveTo)

                    output.seek(normalPosition)

                    # if self.decompressedSize - normalPosition < byteCount:
                    #     diff = self.decompressedSize - normalPosition
                    #     oldCopy = map(hex, map(ord, toCopy))
                    #     print("Difference between current position and " "decompressed size is smaller than the length " "of the current string to be copied.")
                    #     if diff < 0:
                    #         raise RuntimeError(
                    #             "We are already past the compressed size, "
                    #             "this shouldn't happen! Uncompressed Size: {0}, "
                    #             "current position: {1}.".format(self.decompressedSize, normalPosition)
                    #         )
                    #     elif diff == 0:
                    #         toCopy = b""
                    #         print("toCopy string (content: '{0}') has been cleared because " "current position is close to decompressed size.".format(oldCopy))
                    #     else:
                    #         toCopy = toCopy[:diff]
                    #         print(len(toCopy), diff)
                    #         print(
                    #             "toCopy string (content: '{0}') has been shortened to {1} byte/s "
                    #             "because current position is close to decompressed size.".format(oldCopy, diff)
                    #         )

                    output.write(toCopy)

        # print("Done!", codeByte)
        # print("Check the output position and uncompressed size (should be the same):")
        # print("OutputPos: {0}, uncompressed Size: {1}".format(output.tell(), self.decompressedSize))

        return output

    def __build_byte__(self, byteCount, position) -> tuple[bytes, bytes]:
        # if position >= 2**12:
        #     raise RuntimeError("{0} is outside of the range for 12 bits!".format(position))
        # if byteCount > 0xf:
        #     raise RuntimeError("{0} is too much for 4 bits.".format(byteCount))

        positionNibble = position >> 8
        positionByte = position & 0xFF

        byte1 = (byteCount << 4) | positionNibble

        return bytes(byte1), bytes(positionByte)

    # A simple iterator for iterating over the bits of a single byte
    def __bit_iter__(self, byte):
        byte = ord(byte)
        byte = bin(byte)[2:].rjust(8, "0")
        for bit in byte:
            yield bit != "0"


#
#    Helper Functions for easier usage of
#    the compress & decompress methods of the module.
#


# Take a compressed string, decompress it and return the
# results as a string.
def decompress(f):
    yaz0obj = yaz0(BytesIO(f.read()), compress=False)
    return yaz0obj.decompress()


# Take a file-like object, decompress it and return the
# results as a StringIO object.
def decompress_fileobj(f):
    yaz0obj = yaz0(f, compress=False)
    return yaz0obj.decompress()


# Take a file name and decompress the contents of that file.
# If outputPath is given, save the results to a file with
# the name defined by outputPath, otherwise return the results
# as a StringIO object.
def decompress_file(filenamePath: str, outputPath: str = ""):
    with open(filenamePath, "rb") as f:
        yaz0obj = yaz0(BytesIO(f.read()), compress=False)

        result = yaz0obj.decompress()

        if outputPath:
            with open(outputPath, "wb") as output:
                result = result.getvalue()
                output.write(result)

            result = None

    return result
