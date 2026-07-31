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

# Copyright 2026 Roman Shevchik
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://apache.org

import gc
from nav_gen import get_nav_packet
from light_nmea.nmea0183_parser import LightNMEA
from light_nmea.nmea0183_stats import GNSSStats

try:
    import micropython
    IS_MPY = True
except ImportError:
    IS_MPY = False

ITERATIONS = 1_000_000
if IS_MPY:
    ITERATIONS = 1_500

GC_CALL_LIMIT = 500
call_gc_collect = True

def main():
    gps = LightNMEA(trust_gga_fix=True)
    stats = GNSSStats()

    try:
        gc.threshold(8192)  # Запускать GC, когда свободно < 8 КБ
    except AttributeError as ex:
        if 'threshold' not in str(ex):
            raise  # Перевыбрасываю, если ошибка НЕ про 'threshold'!

    mem_before = stats.get_memory_usage()
    print(f"Используемая память до теста [КБ]: {mem_before:.0f}")

    print("=== ТЕСТИРОВАНИЕ БИБЛИОТЕКИ LightNMEA ===")
    print(f"Имитация потока данных из UART ({ITERATIONS} пакетов)...\n")

    stats.start()
    step_show = ITERATIONS // 5

    for idx in range(ITERATIONS):
        packet = get_nav_packet()
        is_recognized = gps.parse_line(packet)
        stats.update(is_recognized, gps.valid, gps.constellation)
        # [ФИКС] - есть валидные координаты. Валидные координаты - это координаты, которые GPS-модуль считает достоверными на основе данных со спутников.
        # [ПОИСК] - пакет распознан, но нет фикса
        # [ИГНОР.] - пакет не распознан
        if 0 == idx % step_show :
            # status = 'НЕТ'
            if is_recognized and gps.has_coordinates():
                if gps.valid:
                    print(f"#{idx:7d} [ФИКС]    lat={gps.latitude:.6f}, "
                          f"lon={gps.longitude:.6f}, sats={gps.satellites}, "
                          f"speed={gps.speed or 0:.1f}, course={gps.course or 0:.1f}")
                    status = 'ФИКС'
                else:
                    print(f"#{idx:7d} [ПОИСК] Фикс потерян!")
                    status = 'ПОИСК'
            elif is_recognized:
                # Распознан, но нет координат (VTG)
                print(f"#{idx:7d} [ДАННЫЕ] speed={gps.speed or 0:.1f}, "
                      f"course={gps.course or 0:.1f}, sats={gps.satellites or 0}")
                status = 'ДАННЫЕ'
            else:
                print(f"#{idx:7d} [ИГНОР.] {packet[:30]}...")
                status = 'ИГНОР'

            # speed и course в вывод
            print(f"#[{status}] lat={gps.latitude or 0:.6f}, "
                  f"lon={gps.longitude or 0:.6f}, sats={gps.satellites or 0}, "
                  f"speed={gps.speed or 0:.1f}, course={gps.course or 0:.1f}")

        if call_gc_collect and idx > 0 and idx % GC_CALL_LIMIT == 0:
            gc.collect()

    # Итоги
    stats.report()
    GNSSStats.print_state(gps)

    mem_after = stats.get_memory_usage()
    print(f"Используемая память после теста [КБ]: {mem_after:.0f}")

    delta_ram = mem_after - mem_before

    if delta_ram > 0:
        print(f"Результат: Потребление ОЗУ выросло на {delta_ram:.0f} КБ.")
    elif delta_ram < 0:
        print(f"Результат: Потребление ОЗУ уменьшилось на {abs(delta_ram):.0f} КБ.")
    else:
        print("Потребление ОЗУ не изменилось!")


if __name__ == "__main__":
    main()