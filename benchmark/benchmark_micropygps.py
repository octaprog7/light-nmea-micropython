# Copyright 2026 Roman Shevchik
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# benchmark_micropygps.py
# Сравнение light_nmea с micropyGPS через run_dual_benchmark
import gc
import os
import sys
from nav_gen import get_nav_packet
# Импортирую из утилит только самое необходимое
from benchmark.bench_utils import get_cross_platform_root, TimeInterval, ITERATIONS, run_dual_benchmark

# Защита от REPL/IDE на уровне запускаемого модуля
try:
    _current_file = __file__
except NameError:
    # имя несуществующего файла для возврата текущей рабочей папки
    _current_file = "empty_dummy.py"

# Определяю корень проекта
base_dir = get_cross_platform_root(_current_file)
# Вставляет на нулевую позицию списка поиска путей sys.path.
sys.path.insert(0, base_dir)


def bench_light_nmea() -> float:
    """Мой парсер."""
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


def bench_micropyGPS() -> float:
    """micropyGPS - конкурент для MicroPython."""
    try:
        from micropyGPS import MicropyGPS
    except ImportError:
        # Для MicroPython возвращаем большое число, чтобы бенчмарк не падал
        return 999999.0

    gps = MicropyGPS()

    timer = TimeInterval()
    gc.collect()

    timer.start()
    for _ in range(ITERATIONS):
        packet = get_nav_packet()
        # micropyGPS требует посимвольного скармливания
        for byte in packet:
            gps.update(chr(byte))
        _ = gps.latitude
    return timer.stop()


def main():
    # Оркестратор сам напечатает заголовки, прогреет циклы и построит таблицу
    run_dual_benchmark("light_nmea", bench_light_nmea, "micropyGPS", bench_micropyGPS)


if __name__ == "__main__":
    main()
