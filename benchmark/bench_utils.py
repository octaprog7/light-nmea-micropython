"""Инструменты для бенчмарков"""
# bench_utils.py
import os
import gc
import time

# Автоопределение платформы и количества повторений
_IS_MPY = hasattr(time, "ticks_us")

try:
    from micropython import const
except ImportError:
    def const(x): return x

# === Константы ===
_WARMUP_RUNS = const(2)
_BENCHMARK_RUNS = const(3)
_DEFAULT_WIDTH = const(60)
_DUAL_BENCH_WIDTH = const(70)
_CACHE_FILE = "last_ln_pps.txt"


ITERATIONS = 333_333
if _IS_MPY:
    ITERATIONS = 1_111


def print_line_separator(separator: str, width: int = _DEFAULT_WIDTH):
    print(width * separator)


class TimeInterval:
    def __init__(self):
        self._start = 0.0
        if _IS_MPY:
            self._time_func = time.ticks_us
        else:
            self._time_func = time.process_time

    def start(self):
        """Запоминает и возвращает момент старта."""
        self._start = self._time_func()
        return self._start

    def stop(self) -> float:
        """Возвращает чистый интервал времени в секундах."""
        _stop = self._time_func()
        if _IS_MPY:
            return 1E-6 * time.ticks_diff(_stop, self._start)
        return _stop - self._start


def print_result(name: str, elapsed: float, iterations: int = ITERATIONS) -> float:
    """Вычисляет пакеты в секунду (PPS) на основе переданного времени
    и выводит отформатированную строку в консоль.
    """
    pps = iterations / elapsed if elapsed > 0 else 0.0
    print(f"Тестирую {name:<15}... OK ({pps:.0f} п/с)")
    return pps


def run_benchmark(name: str, func, runs: int = _BENCHMARK_RUNS) -> float:
    """Главная функция бенчмарка: выполняет прогрев, находит минимальное
    время выполнения из N прогонов (runs) и отправляет результат на печать."""
    # Прогрев
    print(f"Прогрев {name} путем выполнения. Количество циклов: {_WARMUP_RUNS}")
    for idx in range(_WARMUP_RUNS):
        try:
            func()
            print(f"Выполняется прогрев: {100 * (1 + idx) / _WARMUP_RUNS:.0f}%")
        except Exception:
            pass
    print(f"Прогрев завершен. Поехали!")

    # Первый замер
    gc.collect()
    best_time = func()

    # Поиск минимума времени выполнения
    for _ in range(runs - 1):
        gc.collect()
        elapsed = func()
        if elapsed < best_time:
            best_time = elapsed

    # Вывод в консоль и возврат пакетов в секунду (PPS)
    return print_result(name, elapsed=best_time)


def run_dual_benchmark(name1: str, func1, name2: str, func2) -> tuple:
    """Универсальная функция для сравнения двух парсеров."""
    cache_name = _CACHE_FILE

    bench_step = os.environ.get("BENCH_STEP")
    skip_light = bench_step is not None and bench_step != "1"

    print_line_separator("=", _DUAL_BENCH_WIDTH)
    print(f"СРАВНЕНИЕ ПАРСЕРОВ ({ITERATIONS} пакетов)")
    print_line_separator("=", _DUAL_BENCH_WIDTH)
    print()

    if skip_light and name1 == "light_nmea":
        print(f"Тестирую {name1:<15}... ПРОПУЩЕНО (Уже протестирован на шаге 1)")
        with open(cache_name, "r") as f:
            pps1 = float(f.read().strip())
    else:
        pps1 = run_benchmark(name1, func1)

        if name1 == "light_nmea" and bench_step == "1":
            with open(cache_name, "w") as f:
                f.write(f"{pps1:.2f}")

    pps2 = run_benchmark(name2, func2)

    if pps1 > 0.0:
        results = [(name1, pps1), (name2, pps2)]
        results.sort(key=lambda x: x[1], reverse=True)

        print()
        print_line_separator("=", _DUAL_BENCH_WIDTH)
        print("РЕЗУЛЬТАТЫ")
        print_line_separator("=", _DUAL_BENCH_WIDTH)
        print(f"{'Парсер':<25} | {'Пакетов/сек':<15}")
        print_line_separator("-", _DUAL_BENCH_WIDTH)

        for name, pps in results:
            print(f"{name:<25} | {pps:>13.0f}")

        if len(results) >= 2:
            fastest_name, fastest_pps = results[0]
            slowest_name, slowest_pps = results[1]

            ratio = fastest_pps / slowest_pps
            print()
            print("ОТНОСИТЕЛЬНАЯ СКОРОСТЬ ВЫПОЛНЕНИЯ:")
            print(f"  {fastest_name} в {ratio:.1f}x быстрее, чем {slowest_name}")

    print_line_separator("=", _DUAL_BENCH_WIDTH)
    return pps1, pps2

def get_parent_dir(path: str) -> str:
    """Возвращает родительскую директорию (аналог os.path.dirname для MicroPython)."""
    path = path.rstrip('/\\')
    idx = path.rfind('/')
    if idx == -1:
        idx = path.rfind('\\')
    return path[:idx] if idx != -1 else ''