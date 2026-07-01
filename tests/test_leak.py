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

# test_leak.py
import gc
import time
from nav_gen import get_nav_packet
from light_nmea.nmea0183_parser import LightNMEA
from light_nmea.nmea0183_stats import GPSStats

ITERATIONS = 1_000_000

_DELIM = 60

def main():
    gps = LightNMEA(trust_gga_fix=True)
    stats = GPSStats()

    print("=" * _DELIM)
    print("ТЕСТ НА УТЕЧКУ: 3 ПРОГОНА В ОДНОМ ПРОЦЕССЕ")
    print("=" * _DELIM)
    print()

    for run in range(1, 4):
        gc.collect()
        time.sleep(0.3)

        mem_before = stats.get_memory_usage()
        print(f"Прогон {run}:")
        print(f"  До теста:    {mem_before:8.0f} КБ")

        stats.start()
        for _ in range(ITERATIONS):
            packet = get_nav_packet()
            is_recognized = gps.parse_line(packet)
            stats.update(is_recognized, gps.valid)
        stats.stop()

        mem_after = stats.get_memory_usage()
        delta = mem_after - mem_before

        print(f"  После теста: {mem_after:8.0f} КБ")
        print(f"  Дельта:      {delta:+8.0f} КБ")
        print(f"  Скорость:    {stats.packets_per_sec:.0f} пакетов/сек")
        print()

        stats.reset()

    print("=" * _DELIM)
    print("ИНТЕРПРЕТАЦИЯ:")
    print("  Если дельта УМЕНЬШАЕТСЯ (500 -> 10 -> 2) -> НЕТ утечки")
    print("  Если дельта ОДИНАКОВАЯ (500 -> 500 -> 500) -> ЕСТЬ утечка")
    print("=" * _DELIM)


if __name__ == "__main__":
    main()