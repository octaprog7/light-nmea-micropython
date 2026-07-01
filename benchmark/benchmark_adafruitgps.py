#!/usr/bin/env python3
"""
Benchmark Adafruit GPS vs light_nmea on CPython.
Uses mock UART to emulate GPS module behavior.
"""
import gc
import os
import sys
import platform
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from nav_gen import get_nav_packet

# Импортируем только необходимое
from benchmark.bench_utils import (
    TimeInterval,
    ITERATIONS,
    run_dual_benchmark,
    print_line_separator
)

try:
    import adafruit_gps
except ImportError:
    print("ERROR: adafruit_gps is not installed.")
    print("Install it with: pip install adafruit-circuitpython-gps")
    raise


def get_cpu_frequency_mhz() -> float:
    """Измеряет или считывает текущую физическую частоту CPU в МГц."""
    system = platform.system()

    if system == "Linux":
        try:
            with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "r") as f:
                return float(f.read().strip()) / 1000.0
        except (FileNotFoundError, PermissionError, ValueError):
            # Защита от отсутствия sysfs, нехватки прав в контейнере или битых данных
            pass

    elif system == "Windows":
        try:
            cmd = "wmic cpu get CurrentClockSpeed"
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().split()
            # Фильтруем только цифры
            digits = [x for x in output if x.isdigit()]
            if digits:
                return float(digits[0])
        except (subprocess.CalledProcessError, IndexError, ValueError):
            # Защита от отсутствия wmic в новых Windows 11 или пустых ответов консоли
            pass
    return 0.0


class MockUART:
    def __init__(self, packet_func, count):
        self._packet_func = packet_func
        self._count = count
        self._idx = 0

    def readline(self):
        if self._idx < self._count:
            pkt = self._packet_func()
            self._idx += 1
            return pkt
        return None

    @property
    def in_waiting(self):
        return max(0, self._count - self._idx)

    def write(self, data):
        pass


def bench_adafruit_wrapper() -> float:
    uart = MockUART(get_nav_packet, ITERATIONS)
    gps = adafruit_gps.GPS(uart)
    timer = TimeInterval()
    gc.collect()
    timer.start()
    for _ in range(ITERATIONS):
        gps.update()
    return timer.stop()


def bench_light_nmea_wrapper() -> float:
    from light_nmea.nmea0183_parser import LightNMEA
    gps = LightNMEA(trust_gga_fix=True, enable_diagnostics=False)
    timer = TimeInterval()
    gc.collect()
    timer.start()
    for _ in range(ITERATIONS):
        packet = get_nav_packet()
        gps.parse_line(packet)
        _ = gps.valid
        _ = gps.latitude
    return timer.stop()


def get_parsed_stats():
    """Отдельный замер количества успешно обработанных пакетов."""
    uart = MockUART(get_nav_packet, ITERATIONS)
    gps = adafruit_gps.GPS(uart)
    parsed_ada = 0
    for _ in range(ITERATIONS):
        if gps.update():
            parsed_ada += 1
    return ITERATIONS, parsed_ada


def main():
    width = 70
    # Запуск
    pps_ln, pps_ada = run_dual_benchmark("light_nmea", bench_light_nmea_wrapper, "adafruit_gps", bench_adafruit_wrapper)

    # Сбор статистики
    parsed_ln, parsed_ada = get_parsed_stats()
    current_mhz = get_cpu_frequency_mhz()

    # Расчет удельной эффективности на МГц
    eff_light = pps_ln / current_mhz
    eff_ada = pps_ada / current_mhz
    ratio_parsed = parsed_ln / parsed_ada if parsed_ada > 0 else 1.0

    # Вывод расширенного отчета
    print()
    print_line_separator("=", width)
    print("РАСШИРЕННАЯ СТАТИСТИКА:")
    print_line_separator("=", width)
    print(f"Успешно обработано adafruit_gps: {parsed_ada} из {ITERATIONS}")
    print(f"Успешно обработано light_nmea:   {parsed_ln} из {ITERATIONS}")
    print(f"Частота CPU в момент теста:       {current_mhz:.1f} MHz")
    print(f"Удельная эффективность:          light_nmea: {eff_light:.2f} пак/MHz")
    print(f"                                 adafruit_gps: {eff_ada:.2f} пак/MHz")
    print_line_separator("-", width)
    print(f"parsed light_nmea / parsed adafruit_gps: {ratio_parsed:.6f}")
    print_line_separator("=", width)


if __name__ == "__main__":
    main()
