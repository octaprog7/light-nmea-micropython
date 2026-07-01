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

# benchmark_pynmea2.py
# Быстрое сравнение light_nmea с pynmea2 через run_dual_benchmark
import os
import gc
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from nav_gen import get_nav_packet

# Импортируем только TimeInterval, константу и вашу новую дуальную функцию
from benchmark.bench_utils import TimeInterval, ITERATIONS, run_dual_benchmark


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
        # Честный доступ к полям
        _ = gps.valid
        _ = gps.latitude
    return timer.stop()


def bench_pynmea2() -> float:
    """pynmea2 - самый популярный NMEA-парсер."""
    import pynmea2

    timer = TimeInterval()
    gc.collect()

    timer.start()
    for _ in range(ITERATIONS):
        packet = get_nav_packet()
        try:
            # pynmea2 работает со строками
            msg = pynmea2.parse(packet.decode('ascii').strip())
            # Честный доступ к полям
            if hasattr(msg, 'latitude'):
                _ = msg.latitude
                _ = msg.longitude
        except pynmea2.ParseError:
            pass
    return timer.stop()


def main():
    # Вызываем одну общую функцию, которая делает вообще ВСЁ
    run_dual_benchmark("light_nmea", bench_light_nmea, "pynmea2", bench_pynmea2)


if __name__ == "__main__":
    main()
