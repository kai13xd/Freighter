import hashlib
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from os import PathLike
from os.path import isfile
from typing import Any

import jsonpickle
from freighter.config import ProjectConfig
from freighter.path import *
from freighter.config import FREIGHTER_LOCALAPPDATA, ProjectConfig
from freighter.arguments import Arguments


@dataclass
class Symbol:
    name = ""
    demangled_name = ""
    section = ""
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
    _address = 0

    @property
    def address(self):
        return self._address

    @address.setter
    def address(self, value: int):
        self._address = value

    @property
    def hex_address(self):
        return hex(self._address)

    @hex_address.setter
    def hex_address(self, value: str):
        self._address = int(value, 16)

    def __repr__(self) -> str:
        if self.is_c_linkage:
            return self.name
        else:
            return f"{self.demangled_name}"

    def __hash__(self):
        return hash((self.name, self.demangled_name, self.address, self.address))


class File(PathLike):
    def __init__(self, file_manager: "FileManager", path: FilePath) -> None:
        self.file_manager = file_manager
        self.filepath = path
        self.is_dirty = False
        self.sha256hash = "None"
        self.dependencies = set[str]()
        if self.filepath.exists():
            self.calculate_hash()
        if self.is_hash_same():
            self.restore_previous_state()
        self.file_manager.add_file(self)

    def calculate_hash(self):
        with open(self, "rb") as f:
            self.sha256hash = hashlib.file_digest(f, "sha256").hexdigest()

    def restore_previous_state(self):
        self.__dict__.update(self.file_manager.get_cached_file(self).__dict__)
        return self

    def is_hash_same(self) -> bool:
        if self.is_dirty:
            self.calculate_hash()
            self.is_dirty = False
        if self.sha256hash == self.file_manager.get_cached_hash(self):
            return True
        else:
            return False

    def __repr__(self) -> str:
        return self.filepath.__str__()

    def __fspath__(self):
        return self.filepath.__str__()


class HeaderFile(File):
    def __init__(self, file_manager: "FileManager", path: FilePath) -> None:
        File.__init__(self, file_manager, path)
        self.dependencies = self.get_includes(path)
        for include in self.dependencies.copy():
            # Use the work we already have done
            if include in self.file_manager:
                self.dependencies |= self.file_manager.get_file(include).dependencies
            else:
                for include in include.dependencies:
                    self.dependencies |= include.dependencies

    def get_includes(self, filepath: str | Path):
        filepath = Path(filepath)
        include_path: FilePath
        dependencies = set[HeaderFile]()
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
                        dependencies.add(HeaderFile(self.file_manager, resolved_path))
                        continue

                # Check include folders
                resolved_path = ""
                for include_folder in self.file_manager.include_folders:
                    resolved_path = FilePath(include_folder / include_path)
                    if resolved_path.exists():
                        dependencies.add(HeaderFile(self.file_manager, resolved_path))
                        break
                    else:
                        resolved_path = ""

                # Check the immediate source directory
                if not resolved_path:
                    resolved_path = FilePath(filepath.parent / include_path)
                    if resolved_path.exists():
                        dependencies.add(HeaderFile(self.file_manager, resolved_path))
                        continue

                if not resolved_path:
                    raise Exception(f'Could not find include file "{include_path}" found in "{self}"')
        return dependencies


class SourceFile(HeaderFile):
    def __init__(self, file_manager: "FileManager", path: FilePath) -> None:
        super().__init__(file_manager, path)
        object_filepath = FilePath(self.file_manager.temp_folder / (self.filepath.name + ".o"))
        self.object_file = ObjectFile(self.file_manager, object_filepath)
        self.file_manager.add_file(self.object_file)

    def needs_recompile(self) -> bool:
        # Always recompile if the config has been modified
        if not self.file_manager.project_config.is_hash_same():
            return True

        # Recompile deleted object files
        if not self.object_file.filepath.exists():
            return True

        # First check if the current file is modified
        if not self.is_hash_same():
            return True

        # Then check if the includes have been modified
        for dependency in self.dependencies:
            include_file = FileManager.filelist[str(dependency)]
            if not include_file.is_hash_same():
                return True
        return False


class ObjectFile(File):
    def __init__(self, file_manager: "FileManager", path: FilePath) -> None:
        self.symbols = dict[str, Symbol]()
        super().__init__(file_manager, path)
        self.source_name = self.filepath.stem

    def add_symbol(self, symbol: Symbol):
        self.symbols[symbol.demangled_name] = symbol
        self.symbols[symbol.name] = symbol


@dataclass
class FileManager:
    filelist: dict[str, File]
    previous_state: Any

    def __init__(self, project_config: ProjectConfig):
        self.filelist = dict[str, File]()
        self.filehash_path = FilePath(f"{FREIGHTER_LOCALAPPDATA}/{project_config.ProjectName}_FileList.json")
        if Arguments.clean:
            self.filehash_path.delete()
            self.previous_state = dict[str, File]()
        elif self.filehash_path.exists():
            with open(self.filehash_path, "r") as f:
                self.previous_state = jsonpickle.loads(f.read())
        else:
            self.previous_state = dict[str, File]()
        self.project_config = File(self, project_config.config_path)
        self.include_folders = project_config.SelectedProfile.IncludeFolders
        self.temp_folder = project_config.SelectedProfile.TemporaryFilesFolder

    def save_state(self):
        with open(self.filehash_path, "w") as f:
            filelist = self.filelist.copy()
            for file in filelist.values():
                del file.file_manager
                del file.is_dirty
                if not file.dependencies:
                    del file.dependencies
            f.write(str(jsonpickle.encode(filelist)))

    def get_cached_file(self, file: File) -> File:
        return self.previous_state[str(file)]

    def get_file(self, file: File) -> File:
        return self.filelist[str(file)]

    def add_file(self, file: File) -> None:
        self.filelist[str(file)] = file

    def __contains__(self, file: File) -> bool:
        return str(file) in self.filelist.keys()

    def is_cached(self, file: File) -> bool:
        return str(file) in self.previous_state.keys()

    def get_cached_hash(self, file: File) -> str:
        key = str(file)
        if key in self.previous_state.keys():
            return self.previous_state[key].sha256hash
        else:
            return ""
