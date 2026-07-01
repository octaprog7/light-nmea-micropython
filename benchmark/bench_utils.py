"""Инструменты для бенчмарков"""
# bench_utils.py
import os
import gc
import time


# Автоопределение платформы и количества повторений
_IS_MPY = hasattr(time, "ticks_us")

if _IS_MPY:
    ITERATIONS = 1_111
else:
    ITERATIONS = 333_333


def print_line_separator(separator: str, width: int = 60):
    print(width * separator)


class TimeInterval:
    def __init__(self):
        self._start: int | float = 0.0
        if _IS_MPY:
            self._time_func = time.ticks_us
            return
        self._time_func = time.process_time

    def start(self) -> int | float:
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

def run_benchmark(name: str, func, runs: int = 3) -> float:
    """Главная функция бенчмарка: выполняет прогрев, находит минимальное
    время выполнения из N прогонов (runs) и отправляет результат на печать."""
    # Прогрев (2 прогона)
    rng = range(2)
    print(f"Прогрев {name} путем выполения. Количество циклов: {rng.stop}")
    for idx in range(2):
        try:
            func()
            print(f"Выполняется прогрев: {100 * (1 + idx) / rng.stop}%")
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
    res = print_result(name, elapsed=best_time)
    return res[0] if isinstance(res, tuple) else res


def run_dual_benchmark(name1: str, func1, name2: str, func2) -> tuple[float, float]:
    """Универсальная функция для сравнения двух парсеров."""
    wdth = 70
    cache_name = "last_ln_pps.txt"

    bench_step = os.environ.get("BENCH_STEP")
    skip_light = bench_step is not None and bench_step != "1"

    print_line_separator("=", wdth)
    print(f"СРАВНЕНИЕ ПАРСЕРОВ ({ITERATIONS} пакетов)")
    print_line_separator("=", wdth)
    print()

    if skip_light and name1 == "light_nmea":
        print(f"Тестирую {name1:<15}... ПРОПУЩЕНО (Уже протестирован на шаге 1)")
        with open(cache_name, "r") as f:
            pps1 = float(f.read().strip())
    else:
        pps1 = run_benchmark(name1, func1)

        # Если прилетел кортеж, извлекаем из него чистое число PPS
        if isinstance(pps1, tuple):
            pps1 = float(pps1[0])

        if name1 == "light_nmea" and bench_step == "1":
            with open(cache_name, "w") as f:
                f.write(f"{pps1:.2f}")

    pps2 = run_benchmark(name2, func2)

    if isinstance(pps2, tuple):
        pps2 = float(pps2[0])

    if pps1 > 0.0:
        results = [(name1, pps1), (name2, pps2)]
        results.sort(key=lambda x: x[1], reverse=True)

        print()
        print_line_separator("=", wdth)
        print("РЕЗУЛЬТАТЫ")
        print_line_separator("=", wdth)
        print(f"{'Парсер':<25} | {'Пакетов/сек':<15}")
        print_line_separator("-", wdth)

        for name, pps in results:
            print(f"{name:<25} | {pps:>13.0f}")

        if len(results) >= 2:
            fastest_name, fastest_pps = results[0]
            slowest_name, slowest_pps = results[1]

            ratio = fastest_pps / slowest_pps
            print()
            print("ОТНОСИТЕЛЬНАЯ СКОРОСТЬ ВЫПОЛНЕНИЯ:")
            print(f"  {fastest_name} в {ratio:.1f}x быстрее, чем {slowest_name}")

    print_line_separator("=", wdth)
    return pps1, pps2





