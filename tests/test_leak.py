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
# test_leak.py
import gc
import time
from nav_gen import get_nav_packet
from light_nmea.nmea0183_parser import LightNMEA
from light_nmea.nmea0183_stats import GNSSStats

ITERATIONS = 1_000_000
_DELIM = 60


def main():
    print("=" * _DELIM)
    print("ТЕСТ НА УТЕЧКУ: АНАЛИЗ БАЗОВОЙ ПАМЯТИ (ОДИН ПРОЦЕСС)")
    print("=" * _DELIM)
    print()

    # Для хранения базовой памяти перед каждым прогоном
    base_memories = []

    for run in range(1, 4):
        # Пересоздаю объекты, чтобы поймать утечки при их переинициализации
        gps = LightNMEA(trust_gga_fix=True)
        stats = GNSSStats()

        # Жесткая очистка памяти перед замером точки старта
        gc.collect()
        time.sleep(0.5)  # Даем ОС обновить метрики RSS

        # Замеряю базовую память процесса ДО начала создания объектов цикла
        mem_baseline = stats.get_memory_usage()
        base_memories.append(mem_baseline)

        print(f"Прогон {run}:")
        print(f"Базовая память процесса: {mem_baseline:8.0f} КБ")

        stats.start()
        for _ in range(ITERATIONS):
            packet = get_nav_packet()
            is_recognized = gps.parse_line(packet)
            stats.update(is_recognized, gps.valid)
        stats.stop()

        # Локальный замер для информации
        mem_after = stats.get_memory_usage()
        print(f"Пиковая память в прогоне: {mem_after:8.0f} КБ")
        print(f"Скорость обработки:       {stats.packets_per_sec:.0f} пакетов/сек")
        print()

    print("=" * _DELIM)
    print("АНАЛИЗ ТРЕНДА:")
    print("=" * _DELIM)

    # Считаю, насколько увеличилась базовая память между шагами
    diff_1_2 = base_memories[1] - base_memories[0]
    diff_2_3 = base_memories[2] - base_memories[1]

    print(f"  Изменение базы (Прогон 1 -> 2): {diff_1_2:+8.0f} КБ")
    print(f"  Изменение базы (Прогон 2 -> 3): {diff_2_3:+8.0f} КБ")
    print()

    # Интерпретация по базовой памяти (учитываем погрешность выделения ОЗУ в 32 КБ)
    if diff_2_3 > 32:
        print("ИТОГОВЫЙ ВЫВОД: ОБНАРУЖЕНА УТЕЧКА ПАМЯТИ!")
        print("  Базовая память процесса продолжает расти со временем.")
    else:
        print("ИТОГОВЫЙ ВЫВОД: УТЕЧЕК НЕТ.")
        print("  Память стабилизировалась, аллокатор использует ее повторно.")
    print("=" * _DELIM)


if __name__ == "__main__":
    main()