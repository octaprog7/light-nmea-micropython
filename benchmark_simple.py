"""Простой бенчмарк для light_nmea и micropyGPS.
Работает на CPython и MicroPython без внешних зависимостей."""
import gc
import sys
import time

# Автоопределение платформы
_IS_MPY = hasattr(time, "ticks_us")

# Настройка путей для CPython
if hasattr(sys, 'path') and ('win' in sys.platform or 'linux' in sys.platform or 'darwin' in sys.platform):
    try:
        import os
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if base not in sys.path:
            sys.path.insert(0, base)
    except (AttributeError, ImportError):
        pass

from light_nmea.nmea0183_parser import LightNMEA

# Только общие, взаимно поддерживаемые типы пакетов (GGA и RMC)
TEST_PACKETS = (
    b"$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n",
    b"$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n",
    b"$GPGGA,092750.000,5545.1234,N,03731.0000,E,1,08,1.1,150.0,M,15.0,M,,*5B\r\n",
    b"$GPRMC,092750.000,A,5545.1234,N,03731.0000,E,0.02,31.66,280511,,,A*43\r\n",
    b"$GNGGA,123519,4807.038,N,01131.000,E,1,12,0.8,545.4,M,46.9,M,,*4E\r\n",
    b"$GNRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*63\r\n",
)

ITERATIONS = 300_000
if _IS_MPY:
    ITERATIONS = 1000  # Снижаю нагрузку для MCU


def get_time_ms():
    return time.ticks_ms() if _IS_MPY else 1_000 * time.time()


def get_time_diff(end, start):
    return time.ticks_diff(end, start) if _IS_MPY else (end - start)


def benchmark_light_nmea():
    """Бенчмарк light_nmea."""
    parser = LightNMEA()
    packets_count = len(TEST_PACKETS)

    # Замеряем чистую память ДО теста
    gc.collect()
    mem_before = gc.mem_free() if _IS_MPY else 0

    start = get_time_ms()

    for _ in range(ITERATIONS):
        for packet in TEST_PACKETS:
            parser.parse_line(packet)

    end = get_time_ms()

    # Замеряем память ПОСЛЕ теста строго ДО вызова gc.collect()
    mem_after = gc.mem_free() if _IS_MPY else 0

    elapsed = get_time_diff(end, start)
    total_packets = ITERATIONS * packets_count
    speed = total_packets / (elapsed / 1000)

    # Сколько памяти БЫЛО ВЫДЕЛЕНО за время работы алгоритма
    mem_delta = mem_before - mem_after if mem_before > 0 else 0

    print(f"\n=== light_nmea ===")
    print(f"Пакетов обработано: {total_packets}")
    print(f"Время: {elapsed:.1f} мс")
    print(f"Скорость: {speed:.0f} pkt/s")
    if _IS_MPY:
        print(f"Потребление RAM (аллокация): {mem_delta} байт")

    return speed


def benchmark_micropygps():
    """Бенчмарк micropyGPS (если установлен)."""
    try:
        from micropyGPS import MicropyGPS
    except ImportError:
        print("\n=== micropyGPS ===")
        print("Не установлен (пропущено)")
        return 0

    gps = MicropyGPS()
    packets_count = len(TEST_PACKETS)

    # Замеряем чистую память ДО теста
    gc.collect()
    mem_before = gc.mem_free() if _IS_MPY else 0

    start = get_time_ms()

    for _ in range(ITERATIONS):
        for packet in TEST_PACKETS:
            for char in packet:
                gps.update(chr(char))

    end = get_time_ms()

    # Замеряем память ПОСЛЕ теста строго ДО вызова gc.collect()
    mem_after = gc.mem_free() if _IS_MPY else 0

    elapsed = get_time_diff(end, start)
    total_packets = ITERATIONS * packets_count
    speed = total_packets / (elapsed / 1000)

    # Сколько памяти БЫЛО ВЫДЕЛЕНО за время работы алгоритма
    mem_delta = mem_before - mem_after if mem_before > 0 else 0

    print(f"\n=== micropyGPS ===")
    print(f"Пакетов обработано: {total_packets}")
    print(f"Время: {elapsed:.1f} мс")
    print(f"Скорость: {speed:.0f} pkt/s")
    if _IS_MPY:
        print(f"Потребление RAM: {mem_delta} байт")

    return speed

_WIDTH = 60

def main():
    print("=" * _WIDTH)
    print("Бенчмарк NMEA-парсеров")
    print("=" * _WIDTH)
    print(f"Итераций: {ITERATIONS}")
    print(f"Пакетов в итерации: {len(TEST_PACKETS)}")

    speed_light = benchmark_light_nmea()
    speed_micro = benchmark_micropygps()

    if speed_micro > 0:
        print(f"\n=== Сравнение ===")
        if speed_light >= speed_micro:
            ratio = speed_light / speed_micro
            print(f"light_nmea быстрее в {ratio:.1f}x раз.")
        else:
            ratio = speed_micro / speed_light
            print(f"micropyGPS быстрее в {ratio:.1f}x раз.")


    print("\n" + "=" * _WIDTH)


if __name__ == "__main__":
    main()
