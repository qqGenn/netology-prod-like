"""Очистка кэша от устаревших файлов.

Скрипт предназначен для запуска по cron. Проходит по файлам кэша (*.json)
в cache/data/, проверяет timestamp из содержимого файла и удаляет файлы,
возраст которых превышает CACHE_TTL_SECONDS (по умолчанию 10 минут).

Запуск:
    python -m cache.cleanup
    python -m cache.cleanup --dry-run
    python -m cache.cleanup --cache-dir cache/data --ttl 600

При --dry-run удаление не выполняется, а выводится список файлов,
которые были бы удалены.
"""

import argparse
import json
import os
import time
from typing import Dict

from cache.cache_manager import CACHE_TTL_SECONDS
from core.log import logger


def _is_stale(cache_file: str, ttl_seconds: int) -> bool:
    """Проверяет, устарел ли кэш-файл по timestamp внутри него.

    Если timestamp отсутствует/некорректен или файл не читается как JSON —
    файл считается устаревшим (кэш всё равно не может его использовать).
    """
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        logger.warning(f"Кэш-файл повреждён/нечитаем, будет удалён: {cache_file}")
        return True

    timestamp = data.get("timestamp")
    if not isinstance(timestamp, (int, float)):
        logger.warning(f"В кэш-файле отсутствует timestamp, будет удалён: {cache_file}")
        return True

    return time.time() - timestamp > ttl_seconds


def cleanup_expired(
    cache_dir: str = "cache/data",
    ttl_seconds: int = CACHE_TTL_SECONDS,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Удаляет устаревшие файлы кэша.

    Returns:
        Словарь со счётчиками: checked, deleted, failed.
    """
    stats = {"checked": 0, "deleted": 0, "failed": 0}

    if not os.path.isdir(cache_dir):
        logger.warning(f"Директория кэша не найдена: {cache_dir}")
        return stats

    for filename in sorted(os.listdir(cache_dir)):
        if not filename.endswith(".json"):
            continue

        cache_file = os.path.join(cache_dir, filename)
        stats["checked"] += 1

        if not _is_stale(cache_file, ttl_seconds):
            continue

        if dry_run:
            logger.info(f"[dry-run] был бы удалён: {cache_file}")
            stats["deleted"] += 1
            continue

        try:
            os.remove(cache_file)
            logger.info(f"Удалён устаревший кэш-файл: {cache_file}")
            stats["deleted"] += 1
        except Exception as e:
            logger.error(f"Ошибка при удалении {cache_file}: {e}")
            stats["failed"] += 1

    logger.info(
        f"Очистка кэша завершена: проверено {stats['checked']}, "
        f"удалено {stats['deleted']}, ошибок {stats['failed']}"
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Очистка устаревших файлов кэша")
    parser.add_argument(
        "--cache-dir",
        default="cache/data",
        help="Путь к директории кэша (по умолчанию cache/data)",
    )
    parser.add_argument(
        "--ttl",
        type=int,
        default=CACHE_TTL_SECONDS,
        help=f"Максимальный возраст файла в секундах "
        f"(по умолчанию {CACHE_TTL_SECONDS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать, какие файлы были бы удалены, без фактического удаления",
    )
    args = parser.parse_args()

    cleanup_expired(
        cache_dir=args.cache_dir,
        ttl_seconds=args.ttl,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
