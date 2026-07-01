#!/usr/bin/env python3
import os
import sys
import subprocess

os_path = os.path

ROOT_DIR = os_path.dirname(os_path.abspath(__file__))
BENCH_FOLDER = os_path.join(ROOT_DIR, "benchmark")


def print_separator(char: str, width: int = 70):
    print(char * width, flush=True)


def main():
    width = 70
    if not os_path.exists(BENCH_FOLDER):
        print(f"[ОШИБКА] Директория {BENCH_FOLDER} не найдена!", flush=True)
        sys.exit(1)

    # Ищем файлы бенчмарков
    bench_files = [f for f in os.listdir(BENCH_FOLDER) if f.startswith("benchmark_") and f.endswith(".py")]
    bench_files.sort()

    print_separator("=", width)
    print(f"СТАРТ СВОДНОГО ТЕСТИРОВАНИЯ ПАРСЕРОВ ({len(bench_files)} тестов)", flush=True)
    print_separator("=", width)
    print(flush=True)

    # Очищаем старый файл кэша перед стартом, если он остался
    cache_file = os_path.join(BENCH_FOLDER, "last_ln_pps.txt")
    if os_path.exists(cache_file):
        os.remove(cache_file)

    successful = 0
    failed = 0

    for index, file_name in enumerate(bench_files, start=1):
        print(f"\n-> Запуск сценария: {file_name}", flush=True)
        print_separator("-", width)

        try:
            env_vars = os.environ.copy()
            env_vars["PYTHONUNBUFFERED"] = "1"  # Живой вывод прогрева без задержек
            env_vars["BENCH_STEP"] = str(index)

            # Прямой запуск: IDE контролирует его нативно, пути не сдваиваются
            result = subprocess.run(
                [sys.executable, file_name],
                cwd=BENCH_FOLDER,  # Выполняем строго из папки benchmark
                env=env_vars
            )

            if result.returncode == 0:
                successful += 1
            else:
                print(f"[СБОЙ] Сценарий {file_name} завершился с кодом: {result.returncode}", flush=True)
                failed += 1

        except Exception as e:
            print(f"[ОШИБКА] Не удалось запустить {file_name}: {e}", flush=True)
            failed += 1

        print_separator("-", width)

    # Чистим кэш после завершения всех тестов
    if os.path.exists(cache_file):
        os.remove(cache_file)

    print(flush=True)
    print_separator("=", width)
    print("ИТОГОВЫЕ РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ", flush=True)
    print_separator("=", width)
    print(f"Успешно выполнено : {successful}", flush=True)
    print(f"Выполнено со сбоем: {failed}", flush=True)
    print_separator("=", width)


if __name__ == "__main__":
    main()
