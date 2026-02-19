import sys
import os
from dataclasses import dataclass
from jira import JIRA
from urllib3 import disable_warnings
from dotenv import load_dotenv

load_dotenv()
disable_warnings()


@dataclass
class Config:
    """Класс для хранения конфигурации"""
    jira_token: str
    project_id: str
    jira_server: str = "https://jira.mts.ru"

    @classmethod
    def from_env(cls):
        """Создает конфигурацию из переменных окружения"""
        jira_token = os.getenv('JIRA_TOKEN')
        project_id = os.getenv('PROJECT_ID')
        jira_server = os.getenv('JIRA_SERVER', 'https://jira.mts.ru')

        if not jira_token or not project_id:
            missing = []
            if not jira_token:
                missing.append('JIRA_TOKEN')
            if not project_id:
                missing.append('PROJECT_ID')
            raise ValueError(f"Отсутствуют обязательные переменные: {', '.join(missing)}")

        return cls(
            jira_token=jira_token,
            project_id=project_id,
            jira_server=jira_server
        )


def jira_search(v: str, config: Config):
    jira = JIRA(options={
        "server": config.jira_server,
        "verify": False
    }, token_auth=config.jira_token)

    vid = None
    versions = jira.project_versions(config.project_id)

    for version in versions:
        if version.name == v:
            print(f"Найдена версия: {version.name}")
            vid = version.id

    if vid is None:
        print(f"Версия {v} не найдена")
        return []

    issues = jira.search_issues(
        f'project = {config.project_id} '
        f'AND fixVersion = {vid} '
        f'OR issueFunction in '
        f'subtasksOf("project = {config.project_id} AND fixVersion = {vid}") '
        f'ORDER BY priority DESC, key ASC'
    )

    return [issue.key for issue in issues]


if __name__ == "__main__":
    try:
        # Загружаем конфигурацию
        config = Config.from_env()

        # Проверяем аргументы командной строки
        if len(sys.argv) < 2:
            print("Ошибка: не указана версия")
            print("Использование: python script.py <VERSION>")
            sys.exit(1)

        VERSION = sys.argv[1]
        tasks = jira_search(VERSION, config)

        if tasks:
            with open('tasks.txt', 'w') as f:
                for task in tasks:
                    print(task)
                    f.write(task + '\n')
            print(f"\nНайдено задач: {len(tasks)}. Результаты сохранены в tasks.txt")
        else:
            print("Задачи не найдены")

    except ValueError as e:
        print(f"Ошибка конфигурации: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка при выполнении: {e}")
        sys.exit(1)