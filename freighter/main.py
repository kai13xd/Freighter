from __future__ import annotations

import os
from freighter.arguments import Arguments
from freighter.logging import *
from freighter.project import *

USERENVIRONMENT_PATH = FilePath(FREIGHTER_LOCALAPPDATA / "UserEnvironment.toml")


def main():
    os.system("cls" if os.name == "nt" else "clear")
    enabled_logs = {LogLevel.Info, LogLevel.Warning, LogLevel.Error, LogLevel.Exception}
    if Arguments.debug:
        enabled_logs.add(LogLevel.Debug)
    if Arguments.profiler:
        enabled_logs.add(LogLevel.Performance)
    Logger(enabled_logs)
    # try:
    if not any((Arguments.build, Arguments.clean, Arguments.new, Arguments.import_project, Arguments.reset)):
        Arguments.print_help()

    if Arguments.appdata:
        FREIGHTER_LOCALAPPDATA.reveal()

    # UserEnvironment
    if Arguments.reset:
        Logger.info("Resetting UserEnvironment...")
        USERENVIRONMENT_PATH.ask_delete()
        user_environment = UserEnvironmentConfig(USERENVIRONMENT_PATH)
        user_environment.save()
        exit(0)

    if not (user_environment := UserEnvironmentConfig.load(USERENVIRONMENT_PATH)):
        user_environment = UserEnvironmentConfig(USERENVIRONMENT_PATH)
        user_environment.save()

    # ProjectManager

    if not (project_manager := ProjectListConfig.load(PROJECTLIST_PATH)):
        project_manager = ProjectListConfig(PROJECTLIST_PATH)
        project_manager.save()

    if Arguments.new:
        project_manager.new_project()

    if Arguments.import_project:
        project_manager.import_project()

    # ProjectConfig
    if Arguments.build:
        project_name = Arguments.build.project_name
        if project_manager.has_project(project_name):
            project = project_manager.Projects[project_name]
        else:
            os._exit(0)
        os.chdir(project.ProjectPath)
        # ProjectConfig
        project_config = ProjectConfig.load_dynamic(project.ConfigPath, Arguments.build.profile_name)

        # FreighterProject
        if isinstance(project_config, GameCubeProjectConfig):
            freighter_project = GameCubeProject(user_environment, project_config, Arguments.clean)
        elif isinstance(project_config, SwitchProjectConfig):
            freighter_project = SwitchProject(user_environment, project_config, Arguments.clean)
        else:
            raise FreighterException("wtf")  # satisfy type checker

        freighter_project.build()


# except:
# Logger.log(LogLevel.Exception, traceback.format_exc())
# Logger._log.close()
# os._exit(1)
