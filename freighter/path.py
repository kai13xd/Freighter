from functools import cache, cached_property
from glob import glob
from os import getcwd, makedirs, remove
from os.path import expanduser, expandvars, isdir, isfile, realpath, abspath
from pathlib import PurePosixPath, PureWindowsPath
from platform import system
from shutil import rmtree
from os import PathLike
from freighter.colors import *
from freighter.console import Console, PrintType
from freighter.exceptions import FreighterException


class Path(PureWindowsPath):
    @classmethod
    @property
    def home(cls):
        return DirectoryPath(expanduser("~"))

    @classmethod
    @property
    def cwd(cls):
        return DirectoryPath(getcwd())

    # @property
    @cached_property
    def name(self) -> str:
        if self.parts:
            return self.parts[-1]
        else:
            return ""

    # @property
    @cached_property
    def root(self):
        if super().root:
            return "/"

    # @property
    @cached_property
    def anchor(self) -> str:
        if self.drive:
            return self.drive + "/"
        else:
            return ""

    # @property
    @cached_property
    def parts(self) -> tuple[str]:
        old_parts = super().parts
        if not old_parts:
            return tuple()
        parts = []
        parts.append(super().parts[0].replace("\\", "/"))
        parts[1:] += super().parts[1:]
        return tuple(parts)

    # @property
    @cached_property
    def parent(self):
        return DirectoryPath(super().parent)

    def resolve(self, strict=False):
        from errno import EBADF, ELOOP, ENOENT, ENOTDIR

        _WINERROR_NOT_READY = 21  # drive exists but is not accessible
        _WINERROR_INVALID_NAME = 123  # fix for bpo-35306
        _WINERROR_CANT_RESOLVE_FILENAME = 1921  # broken symlink pointing to itself

        def check_eloop(e):
            winerror = getattr(e, "winerror", 0)
            if e.errno == ELOOP or winerror == _WINERROR_CANT_RESOLVE_FILENAME:
                raise RuntimeError("Symlink loop from %r" % e.filename)

        try:
            s = realpath(self, strict=strict)
        except OSError as e:
            check_eloop(e)
            raise
        p = self.__class__._from_parts((s,))

        # In non-strict mode, realpath() doesn't raise on symlink loops.
        # Ensure we get an exception by calling stat()
        if not strict:
            try:
                p.stat()
            except OSError as e:
                check_eloop(e)
        return p

    def __repr__(self):
        return f"{self.__class__.__name__}('{str(self)}')"

    @cache
    def __str__(self):
        if not self.parts:
            return ""
        if self.drive:
            return "/".join(self.parts).replace("//", "/")
        return "/".join(self.parts)


class DirectoryPath(Path):
    def exists(self) -> bool:
        if isdir(self):
            Console.print(f'{ORANGE}Directory Found "{self}"!', PrintType.VERBOSE)
            return True
        else:
            Console.print(f'The folder "{self}" does not exist', PrintType.INFO)  # relative to the cwd "{getcwd()}"')
            return False

    def assert_exists(self) -> bool:
        if self.exists():
            return True
        else:
            raise FreighterException(f'The folder "{self}" does not exist')  # relative to the cwd "{getcwd()}"')

    def delete(self, ask_confirm: bool = False):
        if not self.exists():
            return
        if ask_confirm and input(f'Confirm deletion of directory "{self}"?\nType "yes" to confirm:\n') == "yes":
            rmtree(self)
        

    def find_files(self, *extensions: str, recursive=False):
        globbed = list[str]()
        if extensions:
            for extension in extensions:
                globstr = f"{self}/**/*{extension}"
                globbed += glob(globstr, recursive=recursive,)
        else:
            globbed = glob(f"{self}/*", recursive=recursive)
        
        result = list[FilePath]()
        for path in globbed:
            result.append(FilePath(path))
        return result

    def find_dirs(self, recursive=False):
        result = list[DirectoryPath]()
        for globbed in glob(f"**/**", recursive=recursive):
            result.append(DirectoryPath(globbed))
        return result

    @staticmethod
    def expandvars(path: str):
        return DirectoryPath(expandvars(path))

    def create_filepath(self, filename: str):
        return FilePath(self / filename)

    def create(self):
        if not isdir(self):
            makedirs(self, exist_ok=True)

    def absolute(self):
        return self.__class__(abspath(self))


class FilePath(Path):
    def exists(self) -> bool:
        if isfile(self):
            Console.print(f'{ORANGE}File Found "{self}"!', PrintType.VERBOSE)
            return True
        else:
            Console.print(f'The file "{self}" does not exist', PrintType.WARN)  # relative to the cwd "{getcwd()}"')
            return False

    def delete(self, ask_confirm: bool = False):
        if not self.exists():
            return
        if ask_confirm and input(f'Confirm deletion of file "{self}"?\nType "yes" to confirm:\n') == "yes":
            remove(self)
        

    def assert_exists(self):
        if self.exists():
            return
        else:
            raise FreighterException(f'The file "{self}" does not exist')  # relative to the cwd "{getcwd()}"')

    @staticmethod
    def expandvars(path: str):
        return DirectoryPath(expandvars(path))

    def absolute(self):
        return DirectoryPath(abspath(self))
