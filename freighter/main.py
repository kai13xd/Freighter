import os

from freighter.config import *
from freighter.console import *
from freighter.project import FreighterProject


def main():
    os.system("cls" if os.name == "nt" else "clear")
    if not any((Arguments.build, Arguments.clean, Arguments.new, Arguments.importarg, Arguments.reset)):
        Arguments.print_help()

    # UserEnvironment
    if Arguments.reset:
        user_environment = UserEnvironment.reset()
    else:
        user_environment = UserEnvironment()

    # ProjectList
    project_manager = ProjectManager()

    if Arguments.new:
        project_manager.new_project(Arguments.new)
    if Arguments.importarg:
        project_manager.import_project()

    # ProjectConfig
    if Arguments.build:
        if Arguments.build.project_name in project_manager.Projects.keys():
            project = project_manager.Projects[Arguments.build.project_name]
        else:
            Console.print(f"{Arguments.build.project_name} is not a stored Project")
            project_manager.print()
            exit(0)
        os.chdir(project.ProjectPath)
        project_config = ProjectConfig()
        project_config.init(project.ConfigPath, Arguments.build.profile_name)

        freighter_project = FreighterProject(user_environment, project_config)
        if Arguments.clean:
            freighter_project.cleanup()
        freighter_project.build()
