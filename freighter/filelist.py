import hashlib
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from os import PathLike
from os.path import isfile
from typing import ClassVar

import jsonpickle
from freighter.config import ProjectConfig
from freighter.path import *


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
    def __init__(self, path: FilePath) -> None:
        self.filepath = path
        self.is_dirty = False
        self.sha256hash = ""
        self.dependencies = set[str]()
        if self.filepath.exists():
            self.calculate_hash()
            if self.is_hash_same():
                self.restore_previous_state()
        FileList.add(self)

    def calculate_hash(self):
        with open(self, "rb") as f:
            self.sha256hash = hashlib.file_digest(f, "sha256").hexdigest()

    def restore_previous_state(self):
        file = FileList.previous_state[str(self)]
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

    def __repr__(self) -> str:
        return self.filepath.__str__()

    def __fspath__(self):
        return self.filepath.__str__()


class HeaderFile(File):
    def __init__(self, path: FilePath) -> None:
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
        include_path: FilePath
        dependencies = set[FilePath]()
        with open(filepath, "r", encoding="utf8") as f:
            lines = f.readlines()

        for line in lines:
            if "<" in line:
                continue
            # if line.startswith("#i"):
            if line[3:] == "#in":
                include_path = FilePath(re.findall(r'"([^"]*)"', line)[0])

                # Handle parent directory path lookups
                if "../" in include_path.parts:
                    include_path = FilePath(filepath.parent / include_path)
                    resolved_path = os.path.relpath(FilePath.resolve(include_path))
                    if isfile(resolved_path):
                        dependencies.add(resolved_path)
                        continue

                # Check include folders
                resolved_path = ""
                for include_folder in FileList.include_folders:
                    resolved_path = FilePath(include_folder / include_path)
                    if resolved_path.exists():
                        dependencies.add(resolved_path)
                        break
                    else:
                        resolved_path = ""

                # Check the immediate source directory
                if not resolved_path:
                    resolved_path = FilePath(filepath.parent / include_path)
                    if resolved_path.exists():
                        dependencies.add(resolved_path)
                        continue

                if not resolved_path:
                    raise Exception(f'Could not find include file "{include_path}" found in "{self}"')
        return dependencies


class SourceFile(HeaderFile):
    def __init__(self, path: FilePath) -> None:
        super().__init__(path)
        if self.filepath.suffix in [".c", ".cpp"]:
            object_filepath = FilePath(FileList.temp_folder / (self.filepath.name + ".o"))
            self.object_file = ObjectFile(object_filepath)
            FileList.add(self.object_file)

    def needs_recompile(self) -> bool:
        # Always recompile if the config has been modified
        if not FileList.filelist[str(FileList.config_path)].is_hash_same():
            return True

        # Recompile deleted object files
        if not self.object_file.filepath.exists():
            return True

        # First check if the current file is modified
        if not self.is_hash_same():
            return True

        # Then check if the includes have been modified
        for dependency in self.dependencies:
            include_file = FileList.filelist[str(dependency)]
            if not include_file.is_hash_same():
                return True
        return False


class ObjectFile(File):
    def __init__(self, path: FilePath) -> None:
        self.symbols = dict[str, Symbol]()
        super().__init__(path)
        self.source_file_name = self.filepath.stem

    def add_symbol(self, symbol: Symbol):
        self.symbols[symbol.demangled_name] = symbol
        self.symbols[symbol.name] = symbol


from freighter.config import FREIGHTER_LOCALAPPDATA, ProjectConfig


class FileList:
    previous_state: dict[str, File]
    filelist = dict[str, File]()
    include_folders: list[DirectoryPath]
    temp_folder: DirectoryPath
    filehash_path: FilePath
    @classmethod
    def __init__(cls, project_config: ProjectConfig):
        cls.filehash_path = FilePath(f"{FREIGHTER_LOCALAPPDATA}/{project_config.ProjectName}_FileList.json")
        if cls.filehash_path.exists():
            with open(cls.filehash_path, "r") as f:
                cls.previous_state = jsonpickle.loads(f.read())
        else:
            cls.previous_state = dict[str, File]()
        cls.config_path = project_config.config_path
        cls.include_folders = project_config.selected_profile.IncludeFolders
        cls.temp_folder = project_config.selected_profile.TemporaryFilesFolder
        File(cls.config_path)

    @classmethod
    def save_state(cls):
        with open(cls.filehash_path, "w") as f:
            f.write(jsonpickle.encode(cls.filelist))

    @classmethod
    def add(cls, file: File):
        cls.filelist[str(file)] = file

    @classmethod
    def get(cls, file: File) -> File:
        return cls.filelist[str(file)]

    @classmethod
    def contains(cls, file: File) -> bool:
        return str(file) in cls.filelist.keys()

    @classmethod
    def is_cached(cls, file: File) -> bool:
        return str(file) in cls.previous_state.keys()

    @classmethod
    def get_cached_hash(cls, file: File) -> str:
        return cls.previous_state[str(file)].sha256hash
