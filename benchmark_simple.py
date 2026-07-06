"""Простой бенчмарк для light_nmea и micropyGPS.
Работает на CPython и MicroPython без внешних зависимостей."""
import gc
import sys
import time

# Автоопределение платформы и количества повторений
_IS_MPY = hasattr(time, "ticks_us")

# Настраиваю путь только на CPython
if hasattr(sys, 'path') and 'win' in sys.platform or 'linux' in sys.platform:
    try:
        import os
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if base not in sys.path:
            sys.path.insert(0, base)
    except (AttributeError, ImportError):
        pass

from light_nmea.nmea0183_parser import LightNMEA

# Тестовые данные (без nav_gen)
TEST_PACKETS = (
    b"$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n",
    b"$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n",
    b"$GPGGA,092750.000,5545.1234,N,03731.0000,E,1,08,1.1,150.0,M,15.0,M,,*5B\r\n",
    b"$GPRMC,092750.000,A,5545.1234,N,03731.0000,E,0.02,31.66,280511,,,A*43\r\n",
    b"$GNGGA,123519,4807.038,N,01131.000,E,1,12,0.8,545.4,M,46.9,M,,*4E\r\n",
    b"$GNRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*63\r\n",
    b"$GPGSV,1,1,12,01,45,090,45,02,30,180,40,03,60,270,35,04,15,000,30*7B\r\n",
    b"$GPVTG,054.7,T,034.4,M,005.5,N,010.2,K*48\r\n",
)

ITERATIONS = 500_000
if _IS_MPY:
    ITERATIONS = 1333  # для MicroPython

def benchmark_light_nmea():
    """Бенчмарк light_nmea."""
    parser = LightNMEA()
    packets_count = len(TEST_PACKETS)

    gc.collect()
    mem_before = gc.mem_free() if hasattr(gc, 'mem_free') else 0

    start = time.ticks_ms() if hasattr(time, 'ticks_ms') else time.time() * 1000

    for _ in range(ITERATIONS):
        for packet in TEST_PACKETS:
            parser.parse_line(packet)

    end = time.ticks_ms() if hasattr(time, 'ticks_ms') else time.time() * 1000

    gc.collect()
    mem_after = gc.mem_free() if hasattr(gc, 'mem_free') else 0

    elapsed = end - start
    total_packets = ITERATIONS * packets_count
    speed = total_packets / (elapsed / 1000)
    mem_delta = mem_before - mem_after if mem_before > 0 else 0

    print(f"\n=== light_nmea ===")
    print(f"Пакетов обработано: {total_packets}")
    print(f"Время: {elapsed} мс")
    print(f"Скорость: {speed:.0f} pkt/s")
    if mem_before > 0:
        print(f"Память: -{mem_delta} байт")

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

    gc.collect()
    mem_before = gc.mem_free() if hasattr(gc, 'mem_free') else 0

    start = time.ticks_ms() if hasattr(time, 'ticks_ms') else time.time() * 1000

    for _ in range(ITERATIONS):
        for packet in TEST_PACKETS:
            for char in packet:
                gps.update(chr(char))

    end = time.ticks_ms() if hasattr(time, 'ticks_ms') else time.time() * 1000

    gc.collect()
    mem_after = gc.mem_free() if hasattr(gc, 'mem_free') else 0

    elapsed = end - start
    total_packets = ITERATIONS * packets_count
    speed = total_packets / (elapsed / 1000)
    mem_delta = mem_before - mem_after if mem_before > 0 else 0

    print(f"\n=== micropyGPS ===")
    print(f"Пакетов обработано: {total_packets}")
    print(f"Время: {elapsed} мс")
    print(f"Скорость: {speed:.0f} pkt/s")
    if mem_before > 0:
        print(f"Память: -{mem_delta} байт")

    return speed


def main():
    print("=" * 60)
    print("Бенчмарк NMEA-парсеров")
    print("=" * 60)
    print(f"Итераций: {ITERATIONS}")
    print(f"Пакетов в итерации: {len(TEST_PACKETS)}")

    speed_light = benchmark_light_nmea()
    speed_micro = benchmark_micropygps()

    if speed_micro > 0:
        ratio = speed_light / speed_micro
        print(f"\n=== Сравнение ===")
        print(f"light_nmea быстрее в {ratio:.1f}x раз")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()