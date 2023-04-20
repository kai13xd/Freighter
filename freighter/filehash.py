from os.path import isfile
import os
from os import PathLike
from pathlib import Path
import re
import hashlib
import jsonpickle


re_in_quotes = re.compile('"([^"]*)"')


class SourceFile(PathLike):
    previous_filelist_state = dict[str, object]()
    filelist = dict[str, object]()

    def __init__(self, path: Path) -> None:
        self.name = path.name
        self.dependencies = set[str]()
        self.stem = path.stem
        self.extension = path.suffix
        self.relative_path = path.as_posix()
        self.parent = path.parent.as_posix()

        self.filelist[self.relative_path] = self  # Add this to the global filelist
        with open(self.relative_path, "rb") as f:
            self.sha256hash = hashlib.file_digest(f, "sha256").hexdigest()
        self.get_includes(path)
        for include in self.dependencies.copy():
            if include in self.filelist.keys():
                include_file = self.filelist[include]
                self.dependencies |= include_file.dependencies
            else:
                include_file = SourceFile(Path(include))
                self.filelist[include] = include_file  # Recursively initalize to populate global filelist
                for include in include_file.dependencies:
                    self.dependencies |= include_file.dependencies

    def needs_recompile(self) -> bool:
        from .devkit_tools import Project  # import to get the ProjectProfile

        # New files always need to be compiled
        if self.relative_path not in self.previous_filelist_state.keys():
            return True

        # Recompile deleted object files
        if not isfile(f"{Project.profile.TemporaryFilesFolder}{self.name}.o"):
            return True

        # First check if the current file is modified
        if self.sha256hash != self.previous_filelist_state[self.relative_path].sha256hash:
            return True

        # Then check if the includes have been modified
        for dependency in self.dependencies:
            include_file = self.filelist[dependency]
            if include_file.sha256hash != self.previous_filelist_state[include_file.relative_path].sha256hash:
                return True
        return False

    def get_includes(self, filepath: Path):
        from .devkit_tools import Project  # import to get the ProjectProfile

        include_path: str
        with open(filepath, "r", encoding="utf8") as f:
            for line in f.readlines():
                if "<" in line:
                    continue
                if line.startswith("#include"):
                    include_path = re_in_quotes.findall(line)[0]

                    # Handle parent directory path lookups
                    if "../" in include_path:
                        include_path = Path.joinpath(filepath.parent, include_path)
                        resolved_path = os.path.relpath(Path.resolve(include_path)).replace("\\", "/")
                        if isfile(resolved_path):
                            self.dependencies.add(resolved_path)
                            continue

                    # Check the immediate source directory
                    resolved_path = Path.joinpath(filepath.parent, include_path)
                    if resolved_path.exists():
                        self.dependencies.add(resolved_path.as_posix())
                        continue

                    # Check include folders
                    resolved_path = ""
                    for include_folder in Project.profile.IncludeFolders:
                        resolved_path = Path.joinpath(Path(include_folder), include_path)
                        if resolved_path.is_file():
                            self.dependencies.add(resolved_path.as_posix())
                            break
                        else:
                            resolved_path = ""
                    if not resolved_path:
                        raise Exception(f"Could not find include file found in {include_path}")

    @staticmethod
    def load_filehashes():
        from .devkit_tools import Project  # import to get the ProjectProfile

        if isfile(f"{Project.profile.ProjectName}_filehashes.json"):
            with open(f"{Project.profile.ProjectName}_filehashes.json", "r") as f:
                SourceFile.previous_filelist_state = jsonpickle.loads(f.read())

    @staticmethod
    def save_filehashes():
        from .devkit_tools import Project  # import to get the ProjectProfile

        with open(f"{Project.profile.ProjectName}_filehashes.json", "w") as f:
            f.write(jsonpickle.dumps(SourceFile.filelist, indent=4))

    # def __getstate__(self):
    #     return {"sha256hash": self.sha256hash, "dependencies": self.dependencies}

    def __repr__(self) -> str:
        return f"SourceFile object {self.relative_path}"

    def __str__(self) -> str:
        return self.relative_path

    def __fspath__(self) -> str:
        return self.relative_path
