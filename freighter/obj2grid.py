# obj2grid.py by Yoshi2
# In command line: Type "python obj2grid.py -h" for help
# Feel free to do with the code whatever but please credit me.
# Also I'm not responsible for any bugs caused by modification to the code :)


from struct import pack, unpack
from math import floor, ceil
from re import match
from freighter.path import *
import time
import numpy as np


def read_vertex(v_data):
    split = v_data.split("/")
    if len(split) == 3:
        vnormal = int(split[2])
    else:
        vnormal = None
    v = int(split[0])
    return v, vnormal


def coordinates_same(vertices, v1, v2):
    x_same = vertices[v1][0] == vertices[v2][0]
    y_same = vertices[v1][1] == vertices[v2][1]
    z_same = vertices[v1][2] == vertices[v2][2]

    return x_same and y_same and z_same


def read_obj(objfile, flip_yz=False):
    vertices = []
    faces = []
    # face_normals = []
    normals = []

    floor_type = 0x00

    for i, line in enumerate(objfile):
        line = line.strip()
        args = line.split(" ")

        if len(args) == 0 or line.startswith("#"):
            continue
        cmd = args[0]

        if cmd == "v":
            # if "" in args:
            #     args.remove("")
            x, y, z = map(float, args[1:4])

            if flip_yz:
                vertices.append((x, z, y))
            else:
                vertices.append((x, y, z))
        elif cmd == "f":
            # if it uses more than 3 vertices to describe a face then we panic!
            # no triangulation yet.
            if len(args) != 4:
                raise RuntimeError("Model needs to be triangulated! Only faces with 3 vertices are supported.")
            v1, v2, v3 = map(read_vertex, args[1:4])
            faces.append((v1, v2, v3, floor_type))

            """if (coordinates_same(vertices, v1[0]-1, v2[0]-1) 
                or coordinates_same(vertices, v2[0]-1, v3[0]-1)
                or coordinates_same(vertices, v1[0]-1, v3[0]-1)):
                
                print("hoi")"""

        # elif cmd == "vn":
        #     nx, ny, nz = map(float, args[1:4])
        #     if flip_yz:
        #         normals.append((nx, nz, ny))
        #     else:
        #         normals.append((nx, ny, nz))

        elif cmd == "usemtl":
            assert len(args) >= 2

            matname = " ".join(args[1:])

            floor_type_match = match("^(.*?)(0x[0-9a-fA-F]{2})(.*?)$", matname)

            if floor_type_match is not None:
                floor_type = int(floor_type_match.group(2), 16)
            else:
                floor_type = 0x00

    # objects.append((current_object, vertices, faces))
    return vertices, faces  # , normals


def collides(face_v1, face_v2, face_v3, box_mid_x, box_mid_z, box_size_x, box_size_z):
    min_x = min(face_v1[0], face_v2[0], face_v3[0]) - box_mid_x
    max_x = max(face_v1[0], face_v2[0], face_v3[0]) - box_mid_x
    half_x = box_size_x / 2.0
    if max_x < -half_x or min_x > +half_x:
        return False
    
    min_z = min(face_v1[2], face_v2[2], face_v3[2]) - box_mid_z
    max_z = max(face_v1[2], face_v2[2], face_v3[2]) - box_mid_z
    half_z = box_size_z / 2.0
    if max_z < -half_z or min_z > +half_z:
        return False

    return True


def read_int(f):
    return unpack(">I", f.read(0x4))[0]


def read_float_tripple(f):
    return unpack(">fff", f.read(0xC))


def write_int(f, val):
    f.write(pack(">I", val))


def write_float(f, val):
    f.write(pack(">f", val))


def write_and_replace_out(f, data, offset, replace=b"\x00" * 4):
    assert len(replace) == 4
    f.write(data[:offset])
    f.write(replace)
    f.write(data[offset + 4 :])


def calc_middle(vertices, v1, v2, v3):
    x1, y1, z1 = vertices[v1]
    x2, y2, z2 = vertices[v2]
    x3, y3, z3 = vertices[v3]

    return (x1 + x2 + x3) / 3.0, (y1 + y2 + y3) / 3.0, (z1 + z2 + z3) / 3.0


def calc_middle_of_2(vertices, v1, v2):
    x1, y1, z1 = vertices[v1]
    x2, y2, z2 = vertices[v2]

    return (x1 + x2) / 2.0, (y1 + y2) / 2.0, (z1 + z2) / 2.0


def normalize_vector(v1):
    n = (v1[0] ** 2 + v1[1] ** 2 + v1[2] ** 2) ** 0.5
    return v1[0] / n, v1[1] / n, v1[2] / n


def create_vector(v1, v2):
    return v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2]


def cross_product(v1, v2):
    cross_x = v1[1] * v2[2] - v1[2] * v2[1]
    cross_y = v1[2] * v2[0] - v1[0] * v2[2]
    cross_z = v1[0] * v2[1] - v1[1] * v2[0]
    return cross_x, cross_y, cross_z


def round_away_from_zero(val, fac):
    if val < 0:
        val -= val % fac
    else:
        val += fac - (val % fac)

    return val


def subdivide_grid(minx, minz, gridx_start, gridx_end, gridz_start, gridz_end, cell_size, triangles, vertices, result):
    # print("Subdivision with", gridx_start, gridz_start, gridx_end, gridz_end, (gridx_start+gridx_end) // 2, (gridz_start+gridz_end) // 2)
    if gridx_start == gridx_end - 1 and gridz_start == gridz_end - 1:
        if gridx_start not in result:
            result[gridx_start] = {}
        result[gridx_start][gridz_start] = triangles
        return 

    # assert gridx_end > gridx_start or gridz_end > gridz_start

    halfx = (gridx_start + gridx_end) // 2
    halfz = (gridz_start + gridz_end) // 2

    quadrants = ([], [], [], [])
    # x->
    # 2 3 ^
    # 0 1 z
    coordinates = ((0, gridx_start, halfx, gridz_start, halfz), (1, halfx, gridx_end, gridz_start, halfz), (2, gridx_start, halfx, halfz, gridz_end), (3, halfx, gridx_end, halfz, gridz_end))  # Quadrant 0  # Quadrant 1  # Quadrant 2  # Quadrant 3
    skip = []
    if gridx_start == halfx:
        skip.append(0)
        skip.append(2)
    if halfx == gridx_end:
        skip.append(1)
        skip.append(3)
    if gridz_start == halfz:
        skip.append(0)
        skip.append(1)
    if halfz == gridz_end:
        skip.append(2)
        skip.append(3)

    for i, face in triangles:
        v1_index, v2_index, v3_index = face

        v1 = vertices[v1_index[0] - 1]
        v2 = vertices[v2_index[0] - 1]
        v3 = vertices[v3_index[0] - 1]

        for quadrant, startx, endx, startz, endz in coordinates:
            if quadrant not in skip:
                area_size_x = (endx - startx) * cell_size
                area_size_z = (endz - startz) * cell_size

                if collides(v1, v2, v3, minx + startx * cell_size + area_size_x // 2, minz + startz * cell_size + area_size_z // 2, area_size_x, area_size_z):
                    # print(i, "collided")
                    quadrants[quadrant].append((i, face))

    for quadrant, startx, endx, startz, endz in coordinates:
        # print("Doing subdivision, skipping:", skip)
        if quadrant not in skip:
            # print("doing subdivision with", coordinates[quadrant])
            subdivide_grid(minx, minz, startx, endx, startz, endz, cell_size, quadrants[quadrant], vertices, result)


class PikminCollision:
    def __init__(self, f):
        # Read vertices
        vertex_count = read_int(f)
        vertices = []
        for i in range(vertex_count):
            x, y, z = read_float_tripple(f)
            vertices.append((x, y, z))
        assert vertex_count == len(vertices)

        # Read faces
        face_count = read_int(f)
        faces = []
        for i in range(face_count):
            v1 = read_int(f)
            v2 = read_int(f)
            v3 = read_int(f)
            norm_x, norm_y, norm_z = read_float_tripple(f)
            rest = list(unpack(">" + "f" * (0x34 // 4), f.read(0x34)))

            faces.append([(v1, v2, v3), (norm_x, norm_y, norm_z), rest])

        self.vertices = vertices
        self.faces = faces

        # Read all
        self.tail_offset = f.tell()
        f.seek(0)
        self.data = f.read(self.tail_offset)

        # Store the tail header because we don't know how to change/read it yet
        self.tail_header = f.read(0x28)

        # Read the face groups.
        # Each group is: 4 bytes face count, then 4 bytes face index per face.
        face_groups = []

        while True:
            val = f.read(0x04)

            assert len(val) == 4 or len(val) == 0
            if len(val) == 0:
                break

            data_count = unpack(">I", val)[0]

            group = []

            for i in range(data_count):
                group.append(read_int(f))
            face_groups.append(group)

        self.face_groups = face_groups


def generate_collision(input_model: FilePath, output_folder: DirectoryPath, cell_size: int, flipyz: bool):
    start = time.time()
    output_mapcode = output_folder / "mapcode.bin"
    output_grid = output_folder / "grid.bin"
    assert cell_size > 0

    with open(input_model, "r") as f:
        obj_verts, obj_faces = read_obj(f, flip_yz=(flipyz))

    # print("Writing to", output_grid)

    with open(output_grid, "wb") as f:
        skipped_faces = {}
        smallest_x = smallest_y = smallest_z = +99999999
        biggest_x = biggest_y = biggest_z = -99999999
        write_int(f, len(obj_verts))

        for x, y, z in obj_verts:
            if x > biggest_x:
                biggest_x = x
            if x < smallest_x:
                smallest_x = x

            if y > biggest_y:
                biggest_y = y
            if y < smallest_y:
                smallest_y = y

            if z > biggest_z:
                biggest_z = z
            if z < smallest_z:
                smallest_z = z

            write_float(f, x)
            write_float(f, y)
            write_float(f, z)

        seek_here = f.tell()
        write_int(f, len(obj_faces))

        for i, face in enumerate(obj_faces):
            v1_index, v1_normalindex = face[0]
            v2_index, v2_normalindex = face[1]
            v3_index, v3_normalindex = face[2]

            v1 = obj_verts[v1_index - 1]
            v2 = obj_verts[v2_index - 1]
            v3 = obj_verts[v3_index - 1]

            v1tov2 = create_vector(v1, v2)
            v2tov3 = create_vector(v2, v3)
            v3tov1 = create_vector(v3, v1)

            v1tov3 = create_vector(v1, v3)

            cross_norm = cross_product(v1tov2, v1tov3)
            if cross_norm[0] == cross_norm[1] == cross_norm[2] == 0.0:
                skipped_faces[i] = True
                # print("Found face which was a single line: Face", i, face, "(vertex index,vertex normal index)")
                # raise RuntimeError("Can't continue like this so we will quit now. \n"
                #                    "Find and delete the troublesome face from the obj file and try again")
                tan1 = tan2 = tan3 = norm = [0.0, 0.0, 0.0]
                a = b = c = d = 0
            else:
                norm = normalize_vector(cross_norm)

                tan1 = normalize_vector(cross_product(v1tov2, norm))
                tan2 = normalize_vector(cross_product(v2tov3, norm))
                tan3 = normalize_vector(cross_product(v3tov1, norm))

                norm_x, norm_y, norm_z = norm

                midx = (v1[0] + v2[0] + v3[0]) / 3.0
                midy = (v1[1] + v2[1] + v3[1]) / 3.0
                midz = (v1[2] + v2[2] + v3[2]) / 3.0
                a = norm_x * midx + norm_y * midy + norm_z * midz
                b = tan1[0] * v1[0] + tan1[1] * v1[1] + tan1[2] * v1[2]
                c = tan2[0] * v2[0] + tan2[1] * v2[1] + tan2[2] * v2[2]
                d = tan3[0] * v3[0] + tan3[1] * v3[1] + tan3[2] * v3[2]

            write_int(f, v1_index - 1)
            write_int(f, v3_index - 1)
            write_int(f, v2_index - 1)

            for val in norm:
                write_float(f, val)
            write_float(f, a)

            for val in tan1:
                write_float(f, val)
            write_float(f, b)

            for val in tan2:
                write_float(f, val)
            write_float(f, c)

            for val in tan3:
                write_float(f, val)
            write_float(f, d)

        faces = []
        for face in obj_faces:
            if face not in skipped_faces:
                faces.append(face)

        return_seek = f.tell()
        f.seek(seek_here)
        write_int(f, len(faces))  # len(obj_faces)-len(skipped_faces))
        f.seek(return_seek)

        box_size_x = cell_size
        box_size_z = cell_size

        # print("original dimensions are", smallest_x, smallest_z, biggest_x, biggest_z)
        smallest_x = max(-6000.0, smallest_x)
        smallest_z = max(-6000.0, smallest_z)
        biggest_x = min(6000.0, biggest_x)
        biggest_z = min(6000.0, biggest_z)
        # print("dimensions are changed to", smallest_x, smallest_z, biggest_x, biggest_z)
        start_x = floor(smallest_x / box_size_x) * box_size_x
        start_z = floor(smallest_z / box_size_z) * box_size_z
        end_x = ceil(biggest_x / box_size_x) * box_size_x
        end_z = ceil(biggest_z / box_size_z) * box_size_z
        diff_x = abs(end_x - start_x)
        diff_z = abs(end_z - start_z)
        grid_size_x = int(diff_x // box_size_x)
        grid_size_z = int(diff_z // box_size_z)

        write_float(f, float(start_x))
        write_float(f, float(smallest_y))
        write_float(f, float(start_z))

        write_float(f, float(end_x))
        write_float(f, float(biggest_y))
        write_float(f, float(end_z))

        write_int(f, grid_size_x)
        write_int(f, grid_size_z)

        write_float(f, box_size_x)
        write_float(f, box_size_z)

        # print("collision size:")
        # print(start_x, start_z, end_x, end_z)
        # print(start_x + grid_size_x * box_size_x, start_z + grid_size_z * box_size_z)

        triangles = [(i, face[:3]) for i, face in enumerate(faces)]

        grid = {}
        # print("starting off with", len(triangles), "triangles")
        subdivide_grid(start_x, start_z, 0, grid_size_x, 0, grid_size_z, cell_size, triangles, obj_verts, grid)

        for ix in range(grid_size_x):
            # print("progress: {0} ({1}:{2})".format(ix, grid_size_x, grid_size_z))

            for iz in range(grid_size_z):
                # spot = f.tell()
                if ix not in grid or iz not in grid[ix]:
                    write_int(f, 0)
                else:
                    group = grid[ix][iz]
                    # print(ix, iz, "writing a group with", len(group), "triangles")
                    write_int(f, len(group))

                    for i, face in group:
                        write_int(f, i)
        f.seek(0)

    # print("Writing mapcode to", output_mapcode)

    with open(output_mapcode, "wb") as f:
        write_int(f, len(obj_faces))

        # for i in range(len(obj_faces)):
        #    f.write(b"\x00")
        for _, _, _, floortype in obj_faces:
            f.write(bytes([floortype]))
