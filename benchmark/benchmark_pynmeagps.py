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
# along with this program.  If not, see <https://gnu.org>.

# benchmark_pynmeagps.py
# Быстрое сравнение light_nmea с pynmeagps через run_dual_benchmark
import os
import gc
import sys
from nav_gen import get_nav_packet
# Импортируем только то, что нужно конкретно этому файлу
from benchmark.bench_utils import TimeInterval, ITERATIONS, run_dual_benchmark, get_cross_platform_root

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


class PacketStream:
    """Ленивый стрим пакетов для NMEAReader."""

    def __init__(self, count):
        self.count = count
        self.generated = 0
        self._buffer = b""

    def read(self, size=-1):
        if not self._buffer:
            if self.generated >= self.count:
                return b""
            self._buffer = get_nav_packet()
            self.generated += 1

        if size < 0 or size >= len(self._buffer):
            data = self._buffer
            self._buffer = b""
            return data
        else:
            data = self._buffer[:size]
            self._buffer = self._buffer[size:]
            return data


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


def bench_pynmeagps() -> float:
    """pynmeagps - современный NMEA-парсер от semuconsulting."""
    from pynmeagps import NMEAReader

    stream = PacketStream(ITERATIONS)
    reader = NMEAReader(stream)

    timer = TimeInterval()
    gc.collect()

    timer.start()
    for _ in range(ITERATIONS):
        try:
            raw, parsed = reader.read()
            if parsed:
                _ = parsed.valid
                if hasattr(parsed, 'lat'):
                    _ = parsed.lat
        except Exception:
            pass
    return timer.stop()


def main():
    # Всего одна строчка кода делает ВСЮ работу по запуску и выводу таблицы!
    run_dual_benchmark("light_nmea", bench_light_nmea, "pynmeagps", bench_pynmeagps)


if __name__ == "__main__":
    main()
