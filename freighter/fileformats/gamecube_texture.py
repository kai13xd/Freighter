from PIL import Image, ImageFile
import numpy as np
from enum import IntEnum
from .bitcolorcache import *
from ..constants import *

from time import time
from struct import pack


class ImageFormat(IntEnum):
    RGB5A3 = 0


class GameCubeTexture:
    def __init__(self, image_path):
        self.input_image = Image.open(image_path)
        self.buffer = np.array(self.input_image)
        self.height, self.width, components = self.buffer.shape
        self.has_alpha = False
        if components == 4:
            self.has_alpha = True

    def get_image_blockview(self, np_array: np.ndarray, blocksize):
        return [np_array[x : x + 4, y : y + 4] for x in range(0, np_array.shape[0], blocksize) for y in range(0, np_array.shape[1], blocksize)]

    def encode(self, image_format: ImageFormat) -> bytes:
        start = time()

        encoded_data = bytes()
        match (image_format):
            case ImageFormat.RGB5A3:
                if self.has_alpha:
                    cache = BITCOLOR_CACHE[4]
                    alphacache = BITCOLOR_CACHE[3]
                    for block in self.get_image_blockview(self.buffer, 4):
                        for x, y in np.ndindex((4, 4)):
                            pixel = block[x, y]
                            result = alphacache[pixel[3]] << 12  # 3-bit alpha
                            result |= cache[pixel[0]] << 8  # 4-bit color
                            result |= cache[pixel[1]] << 4
                            result |= cache[pixel[2]] << 0
                            encoded_data += pack(">H", result)
                            # pixel = cache[pixel[0]], cache[pixel[1]], cache[pixel[2]], alphacache[pixel[3]]
                else:
                    cache = BITCOLOR_CACHE[5]
                    for block in self.get_image_blockview(self.buffer, 4):
                        for x, y in np.ndindex((4, 4)):
                            pixel = block[x, y]
                            result = 1 << 15  # No alpha flag
                            result |= cache[pixel[0]] << 10
                            result |= cache[pixel[1]] << 5
                            result |= cache[pixel[2]] << 0
                            encoded_data += pack(">H", result)
                            # pixel = cache[pixel[0]], cache[pixel[1]], cache[pixel[2]]

        console_print(f"Encoded Image in {time() - start} seconds")
        return encoded_data
        # result = Image.fromarray(self.buffer)
        # result.show("Encoded Preview")
