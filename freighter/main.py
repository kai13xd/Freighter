import os

from freighter.config import *
from freighter.console import *
from freighter.project import FreighterProject


def main():
    os.system("cls" if os.name == "nt" else "clear")
    if not any((Arguments.build, Arguments.clean, Arguments.new, Arguments.add, Arguments.reset)):
        Arguments.print_help()

    # UserEnvironment
    if Arguments.reset:
        user_environment = UserEnvironment.reset()
    else:
        user_environment = UserEnvironment()

    # ProjectList
    project_list = ProjectListConfig()

    if Arguments.new:
        project_list.new_project(Arguments.new)
    if Arguments.add:
        project_list.add_project(Arguments.add)

    # ProjectConfig
    if Arguments.build:
        project = project_list.Projects[Arguments.build.project_name]
        os.chdir(project.ProjectPath)
        project_config = ProjectConfig()
        project_config.init(project.ConfigPath, Arguments.build.profile_name)

        freighter_project = FreighterProject(user_environment, project_config)
        if Arguments.clean:
            freighter_project.cleanup()
        freighter_project.build()
