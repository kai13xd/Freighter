import os

from freighter.config import *
from freighter.console import *
from freighter.project import *


def main():
    os.system("cls" if os.name == "nt" else "clear")
    if not any((Arguments.build, Arguments.clean, Arguments.new, Arguments.importarg, Arguments.reset)):
        Arguments.print_help()
    if Arguments.appdata:
        FREIGHTER_LOCALAPPDATA.reveal()
    # UserEnvironment
    if Arguments.reset:
        user_environment = UserEnvironment.reset()
    else:
        user_environment = UserEnvironment()

    # ProjectList
    project_manager = ProjectManager()

    if Arguments.new:
        project_manager.new_project()
    if Arguments.importarg:
        project_manager.import_project()

    # ProjectConfig
    if Arguments.build:
        project_name = Arguments.build.project_name
        if project_manager.has_project(project_name):
            project = project_manager.Projects[project_name]
        else:
            Console.print(f"{project_name} is not a stored Project")
            project_manager.print()
            exit(0)
        os.chdir(project.ProjectPath)
        project_config = ProjectConfig.load(project.ConfigPath)
        project_config.set_profile(Arguments.build.profile_name)

        if isinstance(project_config, GameCubeProjectConfig):
            freighter_project = FreighterGameCubeProject(user_environment, project_config)
        elif isinstance(project_config, SwitchProjectConfig):
            freighter_project = FreighterSwitchProject(user_environment, project_config)
        else:
            raise FreighterException("wtf")

        if Arguments.clean:
            freighter_project.cleanup()
        freighter_project.build()
