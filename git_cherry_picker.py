#!/usr/bin/env python3
"""
Cherry-pick коммитов в хронологическом порядке (старые → новые).
Игнорирует задачи при построении порядка применения.
"""

import subprocess
import sys
import argparse
import os
import re
from typing import List, Set, Tuple, Optional
from dataclasses import dataclass


@dataclass
class GitCommit:
    """Информация о коммите."""
    hash: str
    subject: str
    author: str
    date: str  # ISO-8601
    timestamp: int  # Unix time (для сортировки)
    task_id: str = ""


class GitClient:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def run(self, cmd: List[str], check: bool = True) -> str:
        """Выполняет команду git."""
        if self.verbose:
            print(f" > {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return result.stdout.strip()

    def get_commits_by_tasks(self, branch: str, tasks: Set[str]) -> List[GitCommit]:
        """Получает коммиты из branch по задачам, в хронологическом порядке."""
        if not tasks:
            return []

        # Формат: хеш|тема|автор|дата-iso|родители|timestamp
        log_format = "%H|%s|%an|%ad|%P|%at"
        log_cmd = [
            'git', 'log', branch,
            '--format=' + log_format,
            '--date=iso',
            '--no-merges'  # Исключаем merge-коммиты на уровне git log
        ]

        # Добавляем grep-фильтры для каждой задачи
        for task in tasks:
            log_cmd.extend(['--grep', task])

        output = self.run(log_cmd, check=False)
        return self._parse_commits(output, tasks)

    def _parse_commits(self, output: str, tasks: Set[str]) -> List[GitCommit]:
        """Парсит и фильтрует коммиты, исключая merge."""
        commits = []
        for line in output.split('\n'):
            if not line:
                continue
            parts = line.split('|', 5)
            if len(parts) < 6:
                continue

            try:
                h, subject, author, date, parents, ts = parts
                task_id = self._extract_task_id(subject)

                # Игнорируем, если задача не из списка
                if not task_id or task_id not in tasks:
                    continue

                # Проверка merge по родителям (на всякий случай)
                if len(parents.split()) > 1:
                    continue

                commits.append(GitCommit(
                    hash=h,
                    subject=subject,
                    author=author,
                    date=date,
                    timestamp=int(ts),
                    task_id=task_id
                ))
            except (ValueError, IndexError):
                continue

        # ✅ СОРТИРУЕМ ТОЛЬКО ПО ВРЕМЕНИ (НЕ ПО ЗАДАЧАМ!)
        commits.sort(key=lambda c: c.timestamp)
        return commits

    def _extract_task_id(self, subject: str) -> Optional[str]:
        """Извлекает идентификатор задачи из темы коммита."""
        # Исправлено: убраны экранированные скобки $$
        patterns = [
            r'([A-Z]+-\d+)',    # ECOLOGY-2994
            r'$$([A-Z]+-\d+)$$', # [ECOLOGY-2994]
            r'#(\d+)',          # #1234 (GitHub)
        ]
        for p in patterns:
            m = re.search(p, subject)
            if m:
                return m.group(1)
        return None

    def checkout(self, branch: str) -> None:
        self.run(['git', 'checkout', branch])

    def cherry_pick(self, hash: str) -> None:
        """Выполняет cherry-pick и выбрасывает исключение при конфликте."""
        result = subprocess.run(
            ['git', 'cherry-pick', hash],
            capture_output=True,
            text=True
        )
        # Важно: cherry-pick возвращает 0 только при успехе.
        if result.returncode != 0:
            print("  ⚠ Конфликт! Ошибка выполнения команды cherry-pick.")
            raise subprocess.CalledProcessError(
                returncode=result.returncode,
                cmd=['git', 'cherry-pick', hash],
                output=result.stdout,
                stderr=result.stderr
            )

    def cherry_pick_skip(self) -> None:
        self.run(['git', 'cherry-pick', '--skip'])

    def cherry_pick_abort(self) -> None:
        self.run(['git', 'cherry-pick', '--abort'])


class CherryPicker:
    def __init__(self, git: GitClient, verbose: bool = False):
        self.git = git
        self.verbose = verbose

    def run(self, source: str, target: str, tasks: Set[str], dry_run: bool = False) -> None:
        print("=" * 70)
        print("Git Cherry Picker (в хронологическом порядке)")
        print("=" * 70)
        print(f"Источник: {source}")
        print(f"Цель:     {target}")
        print(f"Задач:    {len(tasks)}")
        if self.verbose:
            print(f"Список:   {', '.join(sorted(tasks))}")
        print(f"Демо:     {'Да' if dry_run else 'Нет'}")
        print("-" * 70)

        # Проверка источника
        if not self.git.run(['git', 'rev-parse', '--verify', source], check=False):
            print(f"Ошибка: ветка '{source}' не существует.")
            sys.exit(1)

        # Получаем коммиты
        commits = self.git.get_commits_by_tasks(source, tasks)

        if not commits:
            print("\nКоммиты для указанных задач не найдены.")
            return

        # Показываем сводку (в хронологическом порядке!)
        self._show_commits(commits)

        if dry_run:
            print("\nДемо-режим: изменения не применяются.")
            return

        # Подтверждение
        confirm = input(f"\nПрименить {len(commits)} коммит(ов)? [y/N]: ")
        if confirm.lower() != 'y':
            print("Отменено.")
            return

        # Применение
        original = self.git.run(['git', 'branch', '--show-current'])
        try:
            if target != original:
                self.git.checkout(target)
            self._apply_commits(commits)
        finally:
            if original and original != self.git.run(['git', 'branch', '--show-current']):
                self.git.checkout(original)

    def _show_commits(self, commits: List[GitCommit]) -> None:
        """Показывает коммиты в хронологическом порядке."""
        print(f"\nНайдено: {len(commits)} коммитов:")
        print("-" * 70)
        for i, c in enumerate(commits, 1):
            preview = c.subject[:60] + ("..." if len(c.subject) > 60 else "")
            print(f"{i:3}. {c.hash[:8]} | {c.date} | {preview} ({c.task_id})")

    def _show_conflicts(self) -> None:
        """Показывает список конфликтных файлов и запускает git diff с цветом."""
        print("\nКонфликтные файлы:")
        try:
            result = subprocess.run(
                ['git', 'diff', '--name-only', '--diff-filter=U'],
                capture_output=True,
                text=True,
                check=True
            )
            files = result.stdout.strip().split('\n')
            if files and files[0]:
                for i, f in enumerate(files, 1):
                    print(f"  {i}. {f}")
                print("\nДля просмотра изменений используйте 'd' (diff) в меню действий.")
            else:
                print("  Нет конфликтов.")
        except subprocess.CalledProcessError as e:
            print(f"  Ошибка при получении конфликтов: {e}")

    def _show_diff(self) -> None:
        """Показывает цветной diff всех конфликтных файлов (как в консоли Git)."""
        print("\nЗапуск 'git diff --cached' с цветовой подсветкой...")
        print("Для выхода нажмите 'q' (в less)")
        print("-" * 70)
        try:
            # Запускаем git diff с цветом и pager'ом
            subprocess.run(
                ['git', 'diff', '--cached', '--color=always'],
                check=True
            )
            print("-" * 70)
            print("Просмотр завершён.")
        except subprocess.CalledProcessError as e:
            print(f"Ошибка при выводе diff: {e}")

    def _handle_conflict(self, commit: GitCommit) -> Tuple[str, bool]:
        """
        Обрабатывает конфликт и возвращает (действие, успех).
        """
        print(f"\n{'=' * 70}")
        print(f"Конфликт при применении {commit.hash[:8]} ({commit.task_id})")
        print(f"Тема: {commit.subject}")
        print(f"{'=' * 70}\n")

        while True:
            self._show_conflicts()
            print("\nДоступные действия:")
            print("  (d)iff     - Показать цветной diff конфликтных файлов")
            print("  (l)ist     - Показать список конфликтных файлов (повтор)")
            print("  (c)ontinue - Продолжить без разрешения (git cherry-pick --continue --no-edit)")
            print("  (u)ours    - Использовать версию из вашей ветки (git checkout --ours)")
            print("  (t)heirs   - Использовать версию из коммита (git checkout --theirs)")
            print("  (m)anual   - Открыть в редакторе (ручное разрешение)")
            print("  (s)kip     - Пропустить этот коммит")
            print("  (a)bort    - Прервать весь cherry-pick")
            print()
            choice = input("Ваш выбор [d/l/c/u/t/m/s/a]: ").lower()

            if choice == 'd':
                self._show_diff()
            elif choice == 'l':
                self._show_conflicts()
            elif choice == 'c':
                return self._continue_or_skip()
            elif choice == 'u':
                self._resolve_conflicts('ours')
                return self._continue_or_skip()
            elif choice == 't':
                self._resolve_conflicts('theirs')
                return self._continue_or_skip()
            elif choice == 'm':
                self._open_in_editor()
                return self._continue_or_skip()
            elif choice == 's':
                self.git.cherry_pick_skip()
                return ('skip', True)
            elif choice == 'a':
                self.git.cherry_pick_abort()
                return ('abort', False)
            else:
                print("Неверный выбор. Попробуйте снова.")

    def _resolve_conflicts(self, strategy: str) -> None:
        """
        Применяет стратегию (ours/ theirs) ко всем конфликтным файлам.
        """
        print(f"\nПрименяем стратегию: {strategy.upper()}")
        try:
            result = subprocess.run(
                ['git', 'diff', '--name-only', '--diff-filter=U'],
                capture_output=True,
                text=True,
                check=True
            )
            files = result.stdout.strip().split('\n')
            if files and files[0]:
                for f in files:
                    if f and os.path.exists(f):
                        print(f"  Устанавливаю '{strategy}' для: {f}")
                        # ✅ ВАЖНО: git checkout --theirs/ours работает только на unmerged файлах
                        subprocess.run(
                            ['git', 'checkout', f'--{strategy}', f],
                            check=True
                        )
                        # Добавляем файл в индекс, чтобы git понял, что конфликт решён
                        subprocess.run(['git', 'add', f], check=True)
            else:
                print("  Нет файлов для обработки. Вы уверены, что есть конфликт?")
        except subprocess.CalledProcessError as e:
            print(f"  Ошибка при применении стратегии: {e}")
            print("  Попробуйте разрешить конфликты вручную.")

    def _open_in_editor(self) -> None:
        """Открывает конфликты в редакторе (по умолчанию — vim)."""
        try:
            result = subprocess.run(
                ['git', 'diff', '--name-only', '--diff-filter=U'],
                capture_output=True,
                text=True,
                check=True
            )
            files = result.stdout.strip().split('\n')
            if files and files[0]:
                editor = os.environ.get('EDITOR', 'vim')
                print(f"\nОткрываем файлы в редакторе: {editor}")
                subprocess.run([editor] + files, check=True)
            else:
                print("\nНет файлов для открытия.")
        except subprocess.CalledProcessError:
            print("\nНе удалось определить файлы для редактора.")

    def _continue_or_skip(self) -> Tuple[str, bool]:
        """
        После разрешения конфликтов пробуем continue с --no-edit (чтобы не зависать).
        """
        try:
            print("  Выполняем 'git cherry-pick --continue --no-edit'...")
            # ✅ ВАЖНО: --no-edit предотвращает открытие редактора
            self.git.run(['git', 'cherry-pick', '--continue', '--no-edit'], check=True)
            print("  ✓ Успешно продолжено!")
            return ('continue', True)
        except subprocess.CalledProcessError:
            print("\n⚠ Не удалось выполнить 'git cherry-pick --continue'.")
            choice = input("Пропустить этот коммит? [y/N]: ").lower()
            if choice == 'y':
                self.git.cherry_pick_skip()
                return ('skip', True)
            else:
                print("Повторите попытку 'continue' или 'abort'.")
                return ('continue', False)

    def _apply_commits(self, commits: List[GitCommit]) -> None:
        """Применяет коммиты последовательно с полной обработкой конфликтов."""
        successful, skipped, failed = 0, 0, 0

        for i, commit in enumerate(commits, 1):
            print(f"\n[{i}/{len(commits)}] Применение {commit.hash[:8]} ({commit.task_id})...")
            try:
                # ❗ ВАЖНО: cherry-pick будет выбрасывать исключение только при конфликте/ошибке
                self.git.cherry_pick(commit.hash)
                print("  ✓ Успешно")
                successful += 1
            except subprocess.CalledProcessError as e:
                print("  ✗ Конфликт или ошибка!")

                # Внутренний цикл: продолжаем until success или skip/abort
                while True:
                    action, success = self._handle_conflict(commit)

                    if action == 'abort':
                        print("\nCherry-pick прерван пользователем.")
                        failed = len(commits) - i + 1
                        return  # Выход из метода
                    elif action == 'skip':
                        skipped += 1
                        break  # Переход к следующему коммиту
                    elif action == 'continue':
                        if success:
                            successful += 1
                            break  # Переход к следующему коммиту
                        else:
                            print("  ⚠ Не удалось завершить cherry-pick --continue. Попробуйте снова.")

        print("\n" + "=" * 70)
        print(f"Итог: {successful} успешно, {skipped} пропущено, {failed} с ошибками")

# --- CLI ---

def parse_tasks(args: List[str]) -> Set[str]:
    """Парсит задачи из аргументов или файлов."""
    tasks = set()
    for arg in args:
        if os.path.isfile(arg):
            with open(arg, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        tasks.add(line)
        elif ',' in arg:
            tasks.update(t.strip() for t in arg.split(',') if t.strip())
        else:
            tasks.add(arg)
    return tasks


def main():
    parser = argparse.ArgumentParser(
        description='Cherry-pick в хронологическом порядке (игнорирует задачи при порядке)',
        epilog="""
Примеры:
  %(prog)s develop main ECOLOGY-2994 ECOLOGY-2995
  %(prog)s develop main tasks.txt
  %(prog)s main feature/v2.0 tasks.txt --dry-run
        """
    )
    parser.add_argument('source', help='Исходная ветка')
    parser.add_argument('target', help='Целевая ветка')
    parser.add_argument('tasks', nargs='+', help='Список задач или файл')
    parser.add_argument('--repo-dir', default='./', help='Директория репозитория')
    parser.add_argument('--dry-run', '-d', action='store_true', help='Только показать')
    parser.add_argument('--verbose', '-v', action='store_true', help='Детали')

    args = parser.parse_args()
    tasks = parse_tasks(args.tasks)

    if args.repo_dir:
        os.chdir(args.repo_dir)

    if not tasks:
        print("Ошибка: не указаны задачи!")
        sys.exit(1)

    git = GitClient(verbose=args.verbose)
    picker = CherryPicker(git, verbose=args.verbose)
    picker.run(args.source, args.target, tasks, dry_run=args.dry_run)


if __name__ == "__main__":
    main()