from PIL import Image, ImageFile
import numpy as np
from enum import IntEnum
from .bitcolorcache import *
from ..console import *
from time import time
from struct import pack
import moderngl


class ImageFormat(IntEnum):
    RGB5A3 = 0


FRAGMENT_SHADER = b"""
#version 430
in vec2 vert_pos;
uniform sampler2D inputImage;
out vec3 fragColor;
out int encodedData[];
vec3 BitColorTruncate(vec3 rgba,int bitdepth)
{
    
    ivec3 color=ivec3(rgba*255.);
    
    switch(bitdepth){
        case 0:
        return vec3(0,0,0);
        case 1:
        color=(color>>7)*255;
        break;
        case 2:
        color=(color>>6)*85;
        break;
        case 3:
        color=(color>>5)*36;
        break;
        case 4:
        color=(color>>4)*17;
        break;
        case 5:
        color=(color>>3)*8;
        break;
        case 6:
        color=(color>>2)*4;
        break;
        case 7:
        color=(color>>1)*2;
        break;
        case 8:
        return rgba;
    }
    return vec3(color)/255.;
}
vec3 BitColor(vec3 rgba,int bitdepth)
{
    
    ivec3 color=ivec3(rgba*255.);
    
    switch(bitdepth){
        case 0:
        return vec3(0,0,0);
        case 1:
        color=(color>>7);
        break;
        case 2:
        color=(color>>6);
        break;
        case 3:
        color=(color>>5);
        break;
        case 4:
        color=(color>>4);
        break;
        case 5:
        color=(color>>3);
        break;
        case 6:
        color=(color>>2);
        break;
        case 7:
        color=(color>>1);
        break;
        case 8:
        return rgba;
    }
    return vec3(color)/255.;
}
void main()
{
    vec3 color=vec3(texture2D(inputImage,vert_pos)).rgb;
    encodedData[0]=int(BitColor(color,5).r);
    fragColor=BitColorTruncate(color,5);
}"""


class GameCubeTexture:
    ctx = moderngl.create_standalone_context()

    prog = ctx.program(
        vertex_shader="""
                #version 330
                in vec2 vertices;
                out vec2 vert_pos;
                void main() {
                    vert_pos = 0.5*(vertices + 1.0);
                    gl_Position = vec4(vertices, 0.0, 1.0);
                }
            """,
        fragment_shader=FRAGMENT_SHADER,
    )

    vao = ctx.simple_vertex_array(prog, ctx.buffer(np.array([1.0, 1.0, -1.0, 1.0, -1.0, -1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0]).astype("f4").tobytes()), "vertices")

    def __init__(self, image_path):
        self.input_image = Image.open(image_path)
        self.buffer = np.array(self.input_image)
        self.result = np.array(self.input_image)
        self.height, self.width, self.components = self.buffer.shape

        print(f"Pixel Count: {self.height * self.width}")

        self.has_alpha = False
        if self.components == 4:
            self.has_alpha = True

    def get_image_blockview(self, np_array: np.ndarray, blocksize):
        return [np_array[x : x + blocksize, y : y + blocksize] for x in range(0, np_array.shape[0], blocksize) for y in range(0, np_array.shape[1], blocksize)]

    def gpu_encode_test(self):
        self.ctx.texture(self.input_image.size, self.components, self.buffer).use()

        fbo = self.ctx.simple_framebuffer(self.input_image.size)
        fbo.use()

        self.vao.render(moderngl.TRIANGLE_STRIP)

        Image.frombytes("RGB", fbo.size, fbo.read()).show()

    def encode(self, image_format: ImageFormat) -> bytes:
        encoded_data = bytes()

        if image_format == ImageFormat.RGB5A3:
            print(f"Block Count: {self.height * self.width / 16}")
            self.block_view = self.get_image_blockview(self.buffer, 4)

            indicies = [(0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2), (1, 3), (2, 0), (2, 1), (2, 2), (2, 3), (3, 0), (3, 1), (3, 2), (3, 3)]
            if self.has_alpha:
                cache = BITCOLOR_CACHE[4]
                alphacache = BITCOLOR_CACHE[3]
                for block in self.block_view:
                    for x, y in indicies:
                        pixel = block[x, y]
                        result = alphacache[pixel[3]] << 12  # 3-bit alpha
                        result |= cache[pixel[0]] << 8  # 4-bit color
                        result |= cache[pixel[1]] << 4
                        result |= cache[pixel[2]] << 0
                        encoded_data += pack(">H", result)
                        # pixel = cache[pixel[0]], cache[pixel[1]], cache[pixel[2]], alphacache[pixel[3]]
            else:
                cache = BITCOLOR_CACHE[5]
                # truncated_cache = TRUNCATED_BITCOLOR_CACHE[5]
                for block in self.block_view:
                    for x, y in indicies:
                        pixel = block[x, y]
                        result = 1 << 15  # No alpha flag
                        result |= cache[pixel[0]] << 10
                        result |= cache[pixel[1]] << 5
                        result |= cache[pixel[2]] << 0
                        encoded_data += pack(">H", result)
                        # block[x, y] = truncated_cache[pixel[0]], truncated_cache[pixel[1]], truncated_cache[pixel[2]]
        # result = Image.fromarray(self.buffer)
        # result.show("Encoded Preview")

        return encoded_data
