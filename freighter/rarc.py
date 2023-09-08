from __future__ import annotations

import os
from enum import IntFlag
from io import BufferedIOBase, BufferedReader, BufferedWriter, BytesIO
from itertools import chain
from struct import pack, unpack

from attrs import define, field
from freighter.logging import *
from freighter.path import *
from freighter.yaz0 import decompress, read_uint16, read_uint32


def write_uint32(f: BufferedIOBase, val):
    f.write(pack(">I", val))


def write_uint16(f: BufferedIOBase, val):
    f.write(pack(">H", val))


def write_uint8(f: BufferedIOBase, val):
    f.write(pack(">B", val))


def write_pad32(f: BufferedIOBase):
    position = f.tell()
    next_aligned_pos = (position + 0x1F) & ~0x1F
    f.write(b"\x00" * (next_aligned_pos - position))


class FileListingFlags(IntFlag):
    FILE = 0x01
    DIRECTORY = 0x02
    COMPRESSED = 0x04
    UNKNOWN_FLAG_0x8 = 0x8
    DATA_FILE = 0x10  # unsure, opposed to REL file?
    REL_FILE = 0x20  # REL = dynamic link libraries
    UNKNOWN_FLAG_0x40 = 0x40
    YAZ0 = 0x80  # if not set but COMPRESSED is set, use yay0?

    @property
    def is_file(self):
        return self & FileListingFlags.FILE

    @property
    def is_dir(self):
        return self & FileListingFlags.DIRECTORY

    @property
    def is_compressed(self):
        return self & FileListingFlags.COMPRESSED

    @property
    def is_rel(self):
        return self & FileListingFlags.DATA_FILE

    @property
    def is_data(self):
        return self & FileListingFlags.REL_FILE

    @property
    def is_yaz0(self):
        return self & FileListingFlags.YAZ0

    def to_string(self):
        result = []
        if self.is_compressed and self.is_yaz0:
            result.append("yaz0_compressed")
        if self.is_rel:
            result.append("rel")
        return "|".join(result)

    @classmethod
    def from_string(cls, string: str):
        result = cls.FILE
        for setting in string.split("|"):
            if setting == "yaz0_compressed":
                result |= cls.DATA_FILE
                result |= cls.COMPRESSED
                result |= cls.YAZ0
            elif setting == "rel":
                result |= cls.REL_FILE
        return result

    @classmethod
    @property
    def default(cls):
        # Default is a uncompressed Data File
        return cls.FILE | cls.DATA_FILE

    def __str__(self):
        return str(self.__dict__)


DATA = [0]


# Hashing algorithm taken from Gamma and LordNed's WArchive-Tools, hope it works
def hash_name(name: str):
    hash = 0
    multiplier = 1
    if len(name) + 1 == 2:
        multiplier = 2
    elif len(name) + 1 >= 3:
        multiplier = 3

    for letter in name:
        hash = (hash * multiplier) & 0xFFFF
        hash = (hash + ord(letter)) & 0xFFFF

    return hash


class StringTable(object):
    def __init__(self):
        self._strings = BytesIO()
        self._stringmap = dict[str, int]()

    def write_string(self, string: str):
        if string not in self._stringmap:
            offset = self._strings.tell()
            self._strings.write(string.encode("shift-jis"))
            self._strings.write(b"\x00")
            self._stringmap[string] = offset

    def get_string_offset(self, string: str):
        return self._stringmap[string]

    def size(self):
        return self._strings.tell()  # len(self._strings.getvalue())

    def write_to(self, f: BufferedWriter):
        f.write(self._strings.getvalue())


def stringtable_get_name(f: BufferedReader | BytesIO, stringtable_offset: int, offset: int):
    current = f.tell()
    f.seek(stringtable_offset + offset)

    stringlen = 0
    while f.read(1) != b"\x00":
        stringlen += 1

    f.seek(stringtable_offset + offset)

    filename = f.read(stringlen)
    try:
        decodedfilename = filename.decode("shift-jis")
    except:
        print("filename", filename)
        print("failed")
        raise
    f.seek(current)

    return decodedfilename


def split_path(path: str):  # Splits path at first backslash encountered
    for i, char in enumerate(path):
        if char == "/" or char == "\\":
            if len(path) == i + 1:
                return path[:i], None
            else:
                return path[:i], path[i + 1 :]

    return path, None


@define
class ARCDirectory:
    name: str
    _nodeindex: int | None
    parent: "ARCDirectory | None" = field(default=None)
    files: dict[str, "ARCFile"] = field(factory=dict)
    subdirs: dict[str, "ARCDirectory"] = field(factory=dict)

    @classmethod
    def from_dir(cls, path: DirectoryPath, follow_symlinks: bool = False) -> "ARCDirectory":
        dirname = path.stem
        # print(dirname, path)
        arc_dir = cls(dirname, None)
        for entry in path.find_files_and_dirs():
            # print(entry.path, dirname)
            if isinstance(entry, DirectoryPath):
                newdir = ARCDirectory.from_dir(entry, follow_symlinks=follow_symlinks)
                arc_dir.subdirs[entry.name] = newdir
                newdir.parent = arc_dir

            elif isinstance(entry, FilePath):
                file = ARCFile.from_file(entry)
                arc_dir.files[entry.name] = file

        return arc_dir

    @classmethod
    def from_node(cls, f: BufferedReader | BytesIO, _name: str, stringtable_offset: int, globalentryoffset: int, dataoffset: int, nodelist: list, currentnodeindex: int, parents=None):
        # print("=============================")
        # print("Creating new node with index", currentnodeindex)
        name, unknown, entrycount, entryoffset = nodelist[currentnodeindex]
        if name is None:
            name = _name

        newdir = cls(name, currentnodeindex)

        firstentry = globalentryoffset + entryoffset
        # print("Node", currentnodeindex, name, entrycount, entryoffset)
        # print("offset", f.tell())
        for i in range(entrycount):
            offset = globalentryoffset + (entryoffset + i) * 20
            f.seek(offset)

            fileentry_data = f.read(20)

            fileid, hashcode, flags, padbyte, nameoffset, filedataoffset, datasize, padding = unpack(">HHBBHIII", fileentry_data)
            # print("offset", hex(firstentry+i*20), fileid, flags, nameoffset)
            flags = FileListingFlags(flags)
            name = stringtable_get_name(f, stringtable_offset, nameoffset)

            # print("name", name, fileid)

            if name == "." or name == ".." or name == "":
                continue
            # print(name, nameoffset)

            if flags.is_dir and not flags.is_file:  # fileid == 0xffff: # entry is a sub directory
                # fileentrydata = f.read(12)
                # nodeindex, datasize, padding = unpack(">III", fileentrydata)
                nodeindex = filedataoffset

                name = stringtable_get_name(f, stringtable_offset, nameoffset)
                # print(name, hashcode, hash_name(name))

                newparents = [currentnodeindex]
                if parents is not None:
                    newparents.extend(parents)

                if nodeindex in newparents:
                    print("Detected recursive directory: ", name)
                    print(newparents, nodeindex)
                    print("Skipping")
                    continue

                subdir = ARCDirectory.from_node(f, name, stringtable_offset, globalentryoffset, dataoffset, nodelist, nodeindex, parents=newparents)
                subdir.parent = newdir

                newdir.subdirs[subdir.name] = subdir

            else:  # entry is a file
                # if flags.is_compressed:
                #     print("File is compressed")
                # if flags.is_yaz0:
                #     print("File is yaz0 compressed")
                f.seek(offset)
                file = ARCFile.from_fileentry(f, stringtable_offset, dataoffset, fileid, hashcode, flags, nameoffset, filedataoffset, datasize)
                newdir.files[file.name] = file

        return newdir

    def walk(self, _path: str | None = None):
        if _path is None:
            dirpath = self.name
        else:
            dirpath = _path + "/" + self.name

        # print("Yielding", dirpath)

        yield (dirpath, self.subdirs.keys(), self.files.keys())

        for dirname, dir in self.subdirs.items():
            # print("yielding subdir", dirname)
            yield from dir.walk(dirpath)

    def __getitem__(self, path: str) -> "ARCDirectory|ARCFile":
        name, rest = split_path(path)

        if rest is None or rest.strip() == "":
            if name in self.subdirs:
                return self.subdirs[name]
            elif name in self.files:
                return self.files[name]
            else:
                raise FileNotFoundError(path)
        elif name in self.files:
            raise RuntimeError("File", name, "is a directory in path", path, "which should not happen!")
        else:
            return self.subdirs[name][rest]

    def __setitem__(self, path: str, entry: "ARCDirectory|ARCFile"):
        name, rest = split_path(path)

        if rest is None or rest.strip() == "":
            if isinstance(entry, ARCFile):
                if name in self.subdirs:
                    raise FileExistsError("Cannot add file, '{}' already exists as a directory".format(path))

                self.files[name] = entry
            elif isinstance(entry, ARCDirectory):
                if name in self.files:
                    raise FileExistsError("Cannot add directory, '{}' already exists as a file".format(path))

                self.subdirs[name] = entry
            else:
                raise TypeError("Entry should be of type File or Directory but is type {}".format(type(entry)))

        elif name in self.files:
            raise RuntimeError("File", name, "is a directory in path", path, "which should not happen!")
        else:
            return self.subdirs[name][rest]

    def extract_to(self, path: DirectoryPath):
        current_dirpath = path / self.name
        os.makedirs(current_dirpath, exist_ok=True)

        for filename, file in self.files.items():
            filepath = current_dirpath.make_filepath(filename)
            with open(filepath, "w+b") as f:
                file.dump(f)

        for dirname, dir in self.subdirs.items():
            dir.extract_to(current_dirpath)

    def absolute_path(self):
        name = self.name
        parent = self.parent
        while parent is not None:
            name = parent.name + "/" + name
            parent = parent.parent

        return name


@define(slots=False)
class ARCFile(BytesIO):
    name: str
    _fileid: int = field(init=False)

    def __init__(self, filename: str, fileid: int = 0, hashcode: int = 0, flags: int = 0):
        super().__init__()
        self.name = filename
        self._fileid = fileid
        self._hashcode = hashcode
        self._flags = flags
        if flags:
            self.filetype = FileListingFlags(flags)
        else:
            self.filetype = FileListingFlags.default

    def is_yaz0_compressed(self):
        if self._flags & FileListingFlags.COMPRESSED and not self._flags & FileListingFlags.YAZ0:
            print("Warning, file {0} is compressed but not with yaz0!".format(self.name))
        return self.filetype.is_compressed and self.filetype.is_yaz0

    @classmethod
    def from_file(cls, file_path: FilePath):
        file = cls(file_path.name)
        with open(file_path, "rb") as f:
            file.write(f.read())
            file.seek(0)
        return file

    @classmethod
    def from_fileentry(cls, f: BufferedReader, stringtable_offset: int, globaldataoffset: int, fileid: int, hashcode: int, flags: int, nameoffset: int, filedataoffset: int, datasize: int):
        filename = stringtable_get_name(f, stringtable_offset, nameoffset)
        """print("-----")
        print("File", len(filename))
        print("size", datasize)
        print(hex(stringtable_offset), hex(nameoffset))
        print(hex(datasize))"""
        file = cls(filename, fileid, hashcode, flags)

        f.seek(globaldataoffset + filedataoffset)
        file.write(f.read(datasize))
        DATA[0] += datasize
        # Reset file position
        file.seek(0)

        return file

    def dump(self, f: BufferedReader):
        if self.is_yaz0_compressed():
            decompress(self)
        else:
            f.write(self.getvalue())


@define
class Archive:
    root: ARCDirectory

    @classmethod
    def from_dir(cls, path: DirectoryPath, follow_symlinks=False):
        return cls(ARCDirectory.from_dir(path, follow_symlinks=follow_symlinks))

    @classmethod
    def from_file(cls, io: BufferedReader):
        # print("ok")
        f = io
        header = f.read(4)

        if header == b"Yaz0":
            # Decompress first
            # print("Yaz0 header detected, decompressing...")
            # start = time.time()

            f.seek(0)
            f = decompress(f)
            # with open("decompressed.bin", "wb") as g:
            #    decompress(f,)

            f.seek(0)

            header = f.read(4)
            # print("Finished decompression.")
            # print("Time taken:", time.time() - start)

        if header == b"RARC":
            pass
        else:
            raise RuntimeError("Unknown file header: {} should be Yaz0 or RARC".format(header))

        size = read_uint32(f)
        f.read(4)  # unknown

        data_offset = read_uint32(f) + 0x20
        f.read(16)  # Unknown
        node_count = read_uint32(f)
        f.read(8)  # Unknown
        file_entry_offset = read_uint32(f) + 0x20
        f.read(4)  # Unknown
        stringtable_offset = read_uint32(f) + 0x20
        f.read(8)  # Unknown
        nodes = list[tuple[str, Any, Any, Any]]()

        # print("Archive has", node_count, " total directories")

        # print("data offset", hex(data_offset))
        for i in range(node_count):
            nodetype = f.read(4)
            nodedata = f.read(4 + 2 + 2 + 4)
            nameoffset, unknown, entrycount, entryoffset = unpack(">IHHI", nodedata)

            if i == 0:
                dir_name = stringtable_get_name(f, stringtable_offset, nameoffset)
            else:
                dir_name = ""

            nodes.append((dir_name, unknown, entrycount, entryoffset))

        rootfoldername = nodes[0][0]
        return cls(ARCDirectory.from_node(f, rootfoldername, stringtable_offset, file_entry_offset, data_offset, nodes, 0))

    def __getitem__(self, path: str) -> ARCDirectory | ARCFile:
        dirname, rest = split_path(path)

        if rest is None or rest.strip() == "":
            if dirname != self.root.name:
                raise FileNotFoundError(path)
            else:
                return self.root
        else:
            return self.root[rest]

    def __setitem__(self, path: str, entry):
        dirname, rest = split_path(path)

        if rest is None or rest.strip() == "":
            if dirname != self.root.name:
                raise RuntimeError("Cannot have more than one directory in the root.")
            elif isinstance(entry, ARCDirectory):
                self.root = entry
            else:
                raise TypeError("Root entry should be of type directory but is type '{}'".format(type(entry)))
        else:
            self.root[rest] = entry

    def extract_to(self, path):
        self.root.extract_to(path)

    def write_arc(self, f: BufferedWriter, filelisting: dict[str, tuple[int, FileListingFlags]], maxindex: int = 0):
        stringtable = StringTable()
        entries = BytesIO()
        data = BytesIO()
        nodecount = 1
        entries = 0

        # Set up string table with all directory and file names
        stringtable.write_string(".")
        stringtable.write_string("..")
        stringtable.write_string(self.root.name)

        for dir, subdirnames, filenames in self.root.walk():
            nodecount += len(subdirnames)
            entries += len(subdirnames) + len(filenames)

            for name in subdirnames:
                stringtable.write_string(name)

            for name in filenames:
                stringtable.write_string(str(name))

        f.write(b"RARC")
        f.write(b"FOO ")  # placeholder for filesize
        write_uint32(f, 0x20)  # Unknown but often 0x20?
        f.write(b"BAR ")  # placeholder for data offset
        f.write(b"\x00" * 16)  # 4 unknown ints

        write_uint32(f, nodecount)
        write_uint32(f, 0x20)  # unknown
        f.write(b"\x00" * 4)  # 1 unknown ints

        # aligned_file_entry_offset = (0x20 + 44 + (nodecount*16) + 0x1f) & 0x20
        # write_uint32(f, aligned_file_entry_offset)  # Offset to file entries aligned to multiples of 0x20
        write_uint32(f, 0xF0F0F0F0)

        f.write(b"\x00" * 4)  # 1 unknown int

        # aligned_stringtable_offset = aligned_file_entry_offset + ((entries * 20) + 0x1f) & 0x20
        # write_uint32(f, aligned_stringtable_offset)
        write_uint32(f, 0xF0F0F0F0)

        f.write(b"\x00" * 8)  # 2 unknown ints

        first_file_entry_index = 0

        dirlist = list[ARCDirectory]()

        # aligned_data_offset = aligned_stringtable_offset + (stringtable.size() + 0x1f) & 0x20

        for i, dirinfo in enumerate(self.root.walk()):
            dirpath, dirnames, filenames = dirinfo
            dir: ARCDirectory = self[dirpath]
            dir._nodeindex = i

            dirlist.append(dir)

            if i == 0:
                nodetype = b"ROOT"
            else:
                nodetype = dir.name.upper().encode("shift-jis")[:4]
                if len(nodetype) < 4:
                    nodetype = nodetype + (b"\x00" * (4 - len(nodetype)))

            f.write(nodetype)
            write_uint32(f, stringtable.get_string_offset(dir.name))
            hash = hash_name(dir.name)

            entrycount = len(dirnames) + len(filenames)
            write_uint16(f, hash)
            write_uint16(f, entrycount + 2)

            write_uint32(f, first_file_entry_index)
            first_file_entry_index += entrycount + 2  # Each directory has two special entries being the current and the parent directories

        write_pad32(f)

        current_file_entry_offset = f.tell()
        # assert f.tell() == aligned_file_entry_offset
        fileid = maxindex

        def key_compare(val):
            if filelisting is not None:
                if val[0] in filelisting:
                    return filelisting[val[0]][0]
            return maxindex + 1

        for dir in dirlist:
            # print("Hello", dir.absolute_path())
            abspath = dir.absolute_path()
            files = list[tuple[str, ARCFile]]()

            for filename, file in dir.files.items():
                files.append((abspath + "/" + filename, file))

            files.sort(key=key_compare)

            for filepath, file in files:
                filemeta = FileListingFlags.default
                if filelisting is not None:
                    if filepath in filelisting:
                        fileid, filemeta = filelisting[filepath]
                        write_uint16(f, fileid)
                        # print("found filemeta")
                    else:
                        write_uint16(f, fileid)
                else:
                    write_uint16(f, fileid)
                filename = file.name
                write_uint16(f, hash_name(filename))
                # print("Writing filemeta", str(filemeta))
                write_uint8(f, filemeta)
                write_uint8(f, 0)  # padding
                # f.write(b"\x11\x00") # Flag for file+padding
                write_uint16(f, stringtable.get_string_offset(filename))

                filedata_offset = data.tell()
                write_uint32(f, filedata_offset)  # Write file data offset

                data.write(file.getvalue())  # Write file data

                write_uint32(f, data.tell() - filedata_offset)  # Write file size
                write_pad32(data)
                write_uint32(f, 0)

                fileid += 1

            specialdirs = [(".", dir), ("..", dir.parent)]

            for subdirname, subdir in chain(specialdirs, dir.subdirs.items()):
                write_uint16(f, 0xFFFF)
                write_uint16(f, hash_name(subdirname))
                f.write(b"\x02\x00")  # Flag for directory+padding
                write_uint16(f, stringtable.get_string_offset(subdirname))

                if subdir is None:
                    child_nodeindex = 0xFFFFFFFF
                else:
                    child_nodeindex = subdir._nodeindex
                write_uint32(f, child_nodeindex)
                write_uint32(f, 0x10)
                write_uint32(f, 0)  # Padding

        write_pad32(f)
        assert f.tell() % 0x20 == 0
        current_stringtable_offset = f.tell()
        stringtable.write_to(f)

        write_pad32(f)
        stringtablesize = f.tell() - current_stringtable_offset

        current_data_offset = f.tell()

        f.write(data.getvalue())

        rarc_size = f.tell()

        f.seek(4)
        write_uint32(f, rarc_size)
        f.seek(12)
        write_uint32(f, current_data_offset - 0x20)
        write_uint32(f, rarc_size - current_data_offset)
        write_uint32(f, rarc_size - current_data_offset)

        f.seek(40)

        total_file_entries = first_file_entry_index
        write_uint32(f, total_file_entries)
        write_uint32(f, current_file_entry_offset - 0x20)
        write_uint32(f, stringtablesize)
        write_uint32(f, current_stringtable_offset - 0x20)


import time


def create_arc(input_dir: DirectoryPath, output_path: FilePath):
    start = time.time()
    if input_dir.exists:
        dirs = input_dir.find_dirs()
        dir_count = len(dirs)
        if dir_count == 0:
            raise RuntimeError(f"Directory {input_dir} contains no folders! Exactly one folder should exist.")
        elif dir_count > 1:
            raise RuntimeError(f"Directory {input_dir} contains multiple folders! Only one folder should exist.")
        Logger.log(LogLevel.Info, f'Creating arc file "{output_path}"')
        archive = Archive.from_dir(dirs[0])
        filelisting = dict[str, tuple[int, FileListingFlags]]()
        maxindex = 0

        filelisting_path = input_dir.make_filepath("filelisting.txt")
        if filelisting_path.exists:
            with open(filelisting_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#"):
                        continue
                    result = line.rsplit(" ", 1)
                    if len(result) == 2:
                        path, fileid = result
                        filelisting_meta = FileListingFlags.default
                    else:
                        path, fileid, metadata = result
                        filelisting_meta = FileListingFlags.from_string(metadata)
                        # print(metadata, filelisting_meta)

                    filelisting[path] = (int(fileid), filelisting_meta)
                    if int(fileid) > maxindex:
                        maxindex = int(fileid)
        else:
            print("no filelisting")

        with open(output_path, "wb") as f:
            archive.write_arc(f, filelisting, maxindex)

        print(f"Done in {time.time() - start} seconds")


def extract_arc(input_path: FilePath, output_path: FilePath):
    print(f"Extracting {input_path}")
    with open(input_path, "rb") as f:
        archive = Archive.from_file(f)
    archive.extract_to(output_path)

    with open(output_path / "filelisting.txt", "w") as f:
        f.write("# DO NOT TOUCH THIS FILE\n")
        for dirpath, dirnames, filenames in archive.root.walk():
            currentdir: ARCDirectory = archive[dirpath]
            # for name in dirnames:
            #
            #    dir = currentdir[name]
            #    f.write(dirpath+"/"+name)
            #    f.write("\n")

            for name in filenames:
                file: ARCFile = currentdir[name]
                f.write(dirpath + "/" + name)
                f.write(" ")
                f.write(str(file._fileid))
                meta = file.filetype.to_string()
                # print(hex(file._flags), file.filetype.to_string())
                if meta:
                    f.write(" ")
                    f.write(meta)
                f.write("\n")
