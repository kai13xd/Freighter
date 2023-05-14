from .config import FreighterConfig

import hashlib
import re
import jsonpickle
import os

from os.path import isfile
from os import PathLike
from pathlib import Path
from dataclasses import dataclass
from copy import deepcopy


@dataclass
class Symbol:
    name = ""
    demangled_name = ""
    section = ""
    address = 0
    hex_address = ""
    size = 0
    is_complete_constructor = False
    is_base_constructor = False
    is_undefined = True
    is_weak = False
    is_function = False
    is_data = False
    is_bss = False
    is_rodata = False
    is_c_linkage = False
    is_absolute = False
    source_file = ""
    library_file = ""

    def __repr__(self) -> str:
        if self.is_c_linkage:
            return self.name
        else:
            return f"{self.demangled_name}"

    def __hash__(self):
        return hash((self.name, self.demangled_name, self.address, self.address))


class File(PathLike):
    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        self.is_dirty = False
        self.relative_path = path.as_posix()
        self.sha256hash = ""
        self.name = path.name
        self.stem = path.stem
        self.extension = path.suffix
        self.parent = path.parent.absolute().as_posix()
        self.dependencies = set[str]()
        if self.exists():
            self.calculate_hash()
            if self.is_hash_same():
                self.restore_previous_state()
        FileList.add(self)

    def exists(self) -> bool:
        return isfile(self)

    def calculate_hash(self):
        with open(self, "rb") as f:
            self.sha256hash = hashlib.file_digest(f, "sha256").hexdigest()

    def restore_previous_state(self):
        file = FileList.previous_state[self.relative_path]
        self.dependencies = file.dependencies
        if hasattr(file, "symbols"):
            self.symbols = file.symbols

    def is_hash_same(self) -> bool:
        if self.is_dirty:
            self.calculate_hash()
            self.is_dirty = False
        if FileList.is_cached(self):
            return self.sha256hash == FileList.get_cached_hash(self)
        else:
            return False

    def __fspath__(self) -> str:
        return self.relative_path

    def __repr__(self) -> str:
        return f"SourceFile object {self.relative_path}"

    def __str__(self) -> str:
        return self.relative_path


class HeaderFile(File):
    def __init__(self, path: str | Path) -> None:
        File.__init__(self, path)
        self.dependencies = self.get_includes(path)
        for include in self.dependencies.copy():
            # Use the work we already have done
            if FileList.contains(include):
                self.dependencies |= FileList.get(include).dependencies
            else:
                include_file = HeaderFile(include)
                for include in include_file.dependencies:
                    self.dependencies |= include_file.dependencies

    def get_includes(self, filepath: str | Path):
        filepath = Path(filepath)
        include_path: str
        dependencies = set[str]()
        with open(filepath, "r", encoding="utf8") as f:
            lines = f.readlines()

        for line in lines:
            if "<" in line:
                continue
            # if line.startswith("#i"):
            if line.startswith("#include"):
                include_path = re.findall(r'"([^"]*)"', line)[0]

                # Handle parent directory path lookups
                if "../" in include_path:
                    include_path = filepath.parent.joinpath(include_path)
                    resolved_path = os.path.relpath(Path.resolve(Path(include_path))).replace("\\", "/")
                    if isfile(resolved_path):
                        dependencies.add(resolved_path)
                        continue

                # Check the immediate source directory
                resolved_path = Path.joinpath(Path(filepath.parent), include_path)
                if resolved_path.exists():
                    dependencies.add(resolved_path.as_posix())
                    continue

                # Check include folders
                resolved_path = ""
                for include_folder in FreighterConfig.profile.IncludeFolders:
                    resolved_path = Path.joinpath(Path(include_folder), include_path)
                    if resolved_path.is_file():
                        dependencies.add(resolved_path.as_posix())
                        break
                    else:
                        resolved_path = ""
                if not resolved_path:
                    raise Exception(f'Could not find include file "{include_path}" found in "{self.relative_path}"')
        return dependencies


class SourceFile(HeaderFile):
    def __init__(self, path: str | Path) -> None:
        HeaderFile.__init__(self, path)
        if self.extension in [".c", ".cpp"]:
            self.object_file_path = f"{FreighterConfig.profile.TemporaryFilesFolder}{self.name}.o"
            self.object_file = ObjectFile(self.object_file_path)
            FileList.add(self.object_file)

    def needs_recompile(self) -> bool:
        # Always recompile if the config has been modified
        if FileList.filelist[FreighterConfig.project_toml_path].is_hash_same():
            return False

        # Recompile deleted object files
        if not self.object_file.exists():
            return True

        # First check if the current file is modified
        if not self.is_hash_same():
            return True

        # Then check if the includes have been modified
        for dependency in self.dependencies:
            include_file = FileList.filelist[dependency]
            if not include_file.is_hash_same():
                return True
        return False


class ObjectFile(File):
    def __init__(self, path: str | Path) -> None:
        self.symbols = dict[str, Symbol]()
        File.__init__(self, path)
        self.source_file_name = self.stem

    def add_symbol(self, symbol: Symbol):
        self.symbols[symbol.demangled_name] = symbol
        self.symbols[symbol.name] = symbol


class FileList:
    previous_state: dict[str, File | SourceFile | ObjectFile]
    filelist = dict[str, File | SourceFile | ObjectFile]()

    @classmethod
    def init(cls):
        filehash_path = "temp/filehashes.json"
        try:
            if isfile(filehash_path):
                with open(filehash_path, "r") as f:
                    cls.previous_state = jsonpickle.loads(f.read())
            else:
                cls.previous_state = dict[str, File]()
        except:
            cls.previous_state = dict[str, File]()

    @classmethod
    def save_state(cls):
        filehash_path: str = "temp/filehashes.json"
        with open(filehash_path, "w") as f:
            f.write(jsonpickle.encode(cls.filelist, indent=4))

    @classmethod
    def add(cls, file: str | File):
        if isinstance(file, File):
            cls.filelist[file.relative_path] = file
        else:
            cls.filelist[file] = File(file)

    @classmethod
    def get(cls, file: str | File) -> File:
        if isinstance(file, File):
            return cls.filelist[file.relative_path]
        else:
            return cls.filelist[file]

    @classmethod
    def contains(cls, file: str | Path | File) -> bool:
        if isinstance(file, File):
            return file.relative_path in cls.filelist.keys()
        if isinstance(file, Path):
            return file.as_posix() in cls.filelist.keys()
        else:
            return file in cls.filelist.keys()

    @classmethod
    def is_cached(cls, file: str | File) -> bool:
        if isinstance(file, File):
            return file.relative_path in cls.previous_state.keys()
        else:
            return file in cls.previous_state.keys()

    @classmethod
    def get_cached_hash(cls, file: str | File) -> str:
        if isinstance(file, File):
            return cls.previous_state[file.relative_path].sha256hash
        else:
            return cls.previous_state[file].sha256hash
