import sys
from jira import JIRA
from urllib3 import disable_warnings
disable_warnings()

token = "YOUR_PERSONAL_TOKEN_HERE"
PROJECT_ID = "24108"


def jira_search(v: str):
    jira = JIRA(options={
        "server": "https://jira.mts.ru",
        "verify": False
    }, token_auth=token)
    vid = None
    versions = jira.project_versions(PROJECT_ID)
    for version in versions:
        if version.name == v:
            print("Found version: " + version.name)
            vid = version.id

    if vid is None:
        return None
    issues = jira.search_issues(
        f'project = {PROJECT_ID} '
        f'AND fixVersion = {vid} '
        f'OR issueFunction in '
        f'subtasksOf("project = {PROJECT_ID} AND fixVersion = {vid}") '
        f'ORDER BY priority DESC, key ASC'
    )
    keys = []
    for issue in issues:
        keys.append(issue.key)
    return keys


if __name__ == "__main__":
    # Проверяем, передан ли аргумент
    if len(sys.argv) < 2:
        print("Ошибка: не указана версия")
        print("Использование: python script.py <VERSION>")
        sys.exit(1)

    VERSION = sys.argv[1]  # Берем версию из аргументов командной строки
    tasks = jira_search(VERSION)
    with open('tasks.txt', 'w') as f:
        for task in tasks:
            print(task)
            f.write(task + '\n')