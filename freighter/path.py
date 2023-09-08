from __future__ import annotations
import ntpath
import os
import subprocess
from errno import ELOOP
from glob import glob
from pathlib import PurePath
from shutil import rmtree
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from io import TextIOWrapper, BufferedRandom
_WINERROR_CANT_RESOLVE_FILENAME = 1921  # broken symlink pointing to itself


class Path(PurePath):
    _raw_paths: list[str]
    _drv: str
    _root: str
    _tail_cached: list[str]
    _str: str | None
    _str_normcase_cached: str
    _parts_normcase_cached: list[str]
    _lines_cached: str
    _hash: int

    def __init__(self, *args):
        paths = list[str]()
        self._str = None
        for arg in args:
            path: str = os.fspath(arg)
            if os.path == ntpath:  # type: ignore
                path = path.replace("\\", "/")
            paths.append(path)
        self._raw_paths = paths

    def __new__(cls, *args, **kwargs):
        return object.__new__(cls)

    @staticmethod
    def home() -> DirectoryPath:
        return DirectoryPath(os.path.expanduser("~"))

    @staticmethod
    def cwd() -> DirectoryPath:
        return DirectoryPath(os.getcwd())

    @property
    def name(self) -> str:
        if self.parts:
            return self.parts[-1]
        else:
            return ""

    @property
    def exists(self) -> bool:
        return os.path.exists(self)

    @property
    def root(self) -> str:
        if super().root:
            self._root = "/"
            return self._root
        else:
            return ""

    @property
    def anchor(self) -> str:
        drive = self.drive
        if drive:
            return drive + "/"
        else:
            return ""

    @property
    def stem(self) -> str:
        """The final path component, minus its last suffix."""
        name = self.name
        i = name.rfind(".")
        if 0 < i < len(name) - 1:
            return name[:i]
        else:
            return name

    @property
    def parent(self) -> "DirectoryPath":
        return DirectoryPath(super().parent)

    @property
    def windows_path(self):
        return str(self).replace("/", "\\")

    def reveal(self) -> None:
        if isinstance(self, FilePath):
            subprocess.run(["explorer.exe", "/select", self.absolute])
        elif isinstance(self, DirectoryPath):
            subprocess.run(["explorer.exe", self.absolute])

    def resolve(self, strict=False):
        """
        Make the path absolute, resolving all symlinks on the way and also
        normalizing it.
        """

        def check_eloop(e):
            winerror = getattr(e, "winerror", 0)
            if e.errno == ELOOP or winerror == _WINERROR_CANT_RESOLVE_FILENAME:
                raise RuntimeError("Symlink loop from %r" % e.filename)

        try:
            s = os.path.realpath(self, strict=strict)
        except OSError as e:
            check_eloop(e)
            raise
        p = self.__class__._from_parts((s,))  # type: ignore

        # In non-strict mode, realpath() doesn't raise on symlink loops.
        # Ensure we get an exception by calling stat()
        if not strict:
            try:
                p.stat()
            except OSError as e:
                check_eloop(e)

        return self.__class__(p)

    def encode(self, encoding: str):
        return str(self).encode(encoding=encoding)

    def assert_exists(self):
        if self.exists:
            return
        else:
            raise FileExistsError(f'The path "{self}" does not exist')

    def __repr__(self):
        return f"{self.__class__.__name__}('{str(self)}')"

    @property
    def parts(self):
        return super().parts

    def __str__(self):
        if self._str:
            return self._str
        else:
            parts = self.parts
            if self.drive:
                self._str = self.anchor + "/".join(parts[1:])
            else:
                self._str = "/".join(parts)
        return self._str


    @property
    def absolute(self):
        return self.__class__(os.path.abspath(self))


Path.__fspath__ = Path.__str__


class DirectoryPath(Path):
    def delete(self):
        if os.path.isdir(self):
            rmtree(self)

    def ask_delete(self) -> bool:
        if os.path.isdir(self) and input(f'Confirm deletion of directory "{self}"?\nType "yes" to confirm:\n') == "yes":
            rmtree(self)
            return True
        else:
            return False

    def find_files(self, *extensions: str, recursive=False):
        globbed = list[str]()
        if extensions:
            for extension in extensions:
                globstr = f"{self}/**/*{extension}"
                globbed += glob(globstr, recursive=recursive)
        else:
            globbed = glob(f"{self}/*", recursive=recursive)
        result = list[FilePath]()
        if not globbed:
            return result
        else:
            for path in globbed:
                result.append(FilePath(path))
            return result

    def find_dirs(self, recursive: bool = False) -> list[DirectoryPath]:
        result = list[DirectoryPath]()
        for globbed in glob(f"{self}/*/", recursive=recursive):
            result.append(DirectoryPath(globbed))
        return result

    def find_files_and_dirs(self, recursive=False):
        return self.find_dirs(recursive=recursive) + self.find_files(recursive=recursive)

    @staticmethod
    def expandvars(path: str):
        return DirectoryPath(os.path.expandvars(path))

    def make_filepath(self, filename: str):
        return FilePath(str(self) + "/" + filename)

    def open_file_as_text(self, filename: str) -> TextIOWrapper:
        return open(str(self) + "/" + filename, "w+", encoding="utf-8")

    def create(self):
        os.makedirs(self, exist_ok=True)


class FilePath(Path):
    def delete(self):
        if os.path.isfile(self):
            os.remove(self)
        return False

    def open_as_text(self) -> TextIOWrapper:
        return open(self, "w+", encoding="utf-8")

    def open_as_binary(self) -> BufferedRandom:
        return open(self, "r+b")

    def ask_delete(self) -> bool:
        if os.path.isfile(self) and input(f'Confirm deletion of file "{self}"?\nType "yes" to confirm:\n') == "yes":
            os.remove(self)
            return True
        else:
            return False

    @staticmethod
    def expandvars(path: str):
        return FilePath(os.path.expandvars(path))
