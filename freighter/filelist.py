from .config import FreighterConfig
import jsonpickle
from os.path import isfile
from os import PathLike
from pathlib import Path
import hashlib
from functools import cache
import os
import re
from dataclasses import dataclass
from typing import TypeAlias
from copy import deepcopy
import time


class File(PathLike):
    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        self.is_dirty = False
        self.relative_path = path.as_posix()
        self.sha256hash = ""
        if self.exists():
            self.calculate_hash()
            if self.is_hash_same():
                self.restore_previous_state()
                FileList.filelist[self.relative_path] = self
                return
        self.name = path.name
        self.stem = path.stem
        self.extension = path.suffix
        self.parent = path.parent.as_posix()
        self.dependencies = set[str]()
        FileList.filelist[self.relative_path] = self

    def set_dirty(self):
        self.is_dirty = True

    def exists(self) -> bool:
        return isfile(self)

    def calculate_hash(self):
        with open(self, "rb") as f:
            self.sha256hash = hashlib.file_digest(f, "sha256").hexdigest()

    def restore_previous_state(self):
        # Need to deepcopy so we don't accidentally use object references
        self.__dict__ = deepcopy(FileList.previous_state[self.relative_path].__dict__)

    def is_cached(self):
        return self.relative_path in FileList.previous_state.keys()

    def is_hash_same(self) -> bool:
        if self.is_dirty:
            self.calculate_hash()
            self.is_dirty = False
        if self.is_cached():
            return self.sha256hash == FileList.previous_state[self.relative_path].sha256hash
        else:
            return False

    def __fspath__(self) -> str:
        return self.relative_path

    def __repr__(self) -> str:
        return f"SourceFile object {self.relative_path}"

    def __str__(self) -> str:
        return self.relative_path


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


re_in_quotes = re.compile('"([^"]*)"')


class SourceFile(File):
    def __init__(self, path: Path) -> None:
        super().__init__(path)

        if self.extension in [".c", ".cpp"]:
            self.object_file_path = f"{FreighterConfig.project.TemporaryFilesFolder}{self.name}.o"
            self.object_file = ObjectFile(self.object_file_path)

        self.get_includes(path)
        for include in self.dependencies.copy():
            if include in FileList.filelist.keys():
                include_file = FileList.filelist[include]
                self.dependencies |= include_file.dependencies
            else:
                include_file = SourceFile(include)
                for include in include_file.dependencies:
                    self.dependencies |= include_file.dependencies

    def needs_recompile(self) -> bool:
        # Always recompile if the config has been modified
        if not FileList.filelist[FreighterConfig.config_path].is_hash_same():
            return True

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

    def get_includes(self, filepath: Path):
        filepath = Path(filepath)
        include_path: str
        with open(filepath, "r", encoding="utf8") as f:
            for line in f.readlines():
                if "<" in line:
                    continue
                if line.startswith("#include"):
                    include_path = re_in_quotes.findall(line)[0]

                    # Handle parent directory path lookups
                    if "../" in include_path:
                        include_path = Path.joinpath(Path(filepath.parent), include_path)
                        resolved_path = os.path.relpath(Path.resolve(include_path)).replace("\\", "/")
                        if isfile(resolved_path):
                            self.dependencies.add(resolved_path)
                            continue

                    # Check the immediate source directory
                    resolved_path = Path.joinpath(Path(filepath.parent), include_path)
                    if resolved_path.exists():
                        self.dependencies.add(resolved_path.as_posix())
                        continue

                    # Check include folders
                    resolved_path = ""
                    for include_folder in FreighterConfig.project.IncludeFolders:
                        resolved_path = Path.joinpath(Path(include_folder), include_path)
                        if resolved_path.is_file():
                            self.dependencies.add(resolved_path.as_posix())
                            break
                        else:
                            resolved_path = ""
                    if not resolved_path:
                        raise Exception(f"Could not find include file found in {include_path} for {self.relative_path}")


class ObjectFile(File):
    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        self.symbols = dict[str, Symbol]()
        self.source_file_name = path.stem
        super().__init__(path)

    def add_symbol(self, symbol: Symbol):
        self.symbols[symbol.demangled_name] = symbol
        self.symbols[symbol.name] = symbol


class FileList:
    previous_state: dict[str, File]
    filelist: dict[str, File | SourceFile | ObjectFile]

    @classmethod
    def init(cls):
        try:
            if isfile(f"{FreighterConfig.project.ProjectName}_filehashes.json"):
                with open(f"{FreighterConfig.project.ProjectName}_filehashes.json", "r") as f:
                    cls.previous_state = jsonpickle.loads(f.read())
            else:
                cls.previous_state = dict[str, File]()
        except:
            cls.previous_state = dict[str, File]()
        cls.filelist = dict[str, File]()

    @classmethod
    def save_state(cls):
        with open(f"{FreighterConfig.project.ProjectName}_filehashes.json", "w") as f:
            f.write(jsonpickle.encode(cls.filelist, indent=4))
