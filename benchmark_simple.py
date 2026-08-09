"""Простой бенчмарк для light_nmea и micropyGPS.
Работает на CPython и MicroPython без внешних зависимостей."""
import gc
import sys
import time

try:
    import micropython
    _IS_MPY = True
except ImportError:
    _IS_MPY = False

_HAS_NATIVE = False
_HAS_VIPER = False

try:
    from micropython import native
    _HAS_NATIVE = True
except ImportError:
    def native(f): return f

try:
    from micropython import viper
    _HAS_VIPER = True
except ImportError:
    def viper(f): return f

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

ITERATIONS = 30_000
if _IS_MPY:
    ITERATIONS = ITERATIONS // 30


def get_mem_alloc():
    """Кроссплатформенное измерение выделенной памяти."""
    if _IS_MPY:
        return gc.mem_alloc()
    else:
        import tracemalloc
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return current


def get_time_ms():
    if _IS_MPY:
        return time.ticks_ms()
    else:
        return 1_000 * time.perf_counter()


def get_time_diff(end, start):
    if _IS_MPY:
        return time.ticks_diff(end, start)
    else:
        return end - start


@native
def benchmark_light_nmea():
    """Бенчмарк light_nmea."""
    parser = LightNMEA()
    packets_count = len(TEST_PACKETS)

    # Прогрев
    for _ in range(100):
        for packet in TEST_PACKETS:
            parser.parse_line(packet)

    gc.collect()
    mem_alloc_before = get_mem_alloc()

    start = get_time_ms()

    for _ in range(ITERATIONS):
        for packet in TEST_PACKETS:
            parser.parse_line(packet)

    end = get_time_ms()
    gc.collect()
    mem_alloc_after = get_mem_alloc()

    elapsed = get_time_diff(end, start)
    total_packets = ITERATIONS * packets_count
    speed = total_packets / (elapsed / 1000)

    mem_delta = mem_alloc_after - mem_alloc_before

    print(f"\n=== light_nmea ===")
    print(f"Packets processed: {total_packets}")
    print(f"Duration of execution: {elapsed:.1f} ms")
    print(f"Speed: {speed:.0f} pkt/s")
    if _IS_MPY:
        print(f"RAM usage: {mem_delta} bytes")

    return speed


@native
def benchmark_micropygps():
    """Бенчмарк micropyGPS (если установлен)."""
    try:
        from micropyGPS import MicropyGPS
    except ImportError:
        print("\n=== micropyGPS ===")
        print("Not installed (skipped)")
        return 0

    gps = MicropyGPS()
    packets_count = len(TEST_PACKETS)

    # Разогрев
    for _ in range(100):
        for packet in TEST_PACKETS:
            for char in packet:
                gps.update(chr(char))

    gc.collect()
    mem_alloc_before = get_mem_alloc()

    start = get_time_ms()

    for _ in range(ITERATIONS):
        for packet in TEST_PACKETS:
            for char in packet:
                gps.update(chr(char))

    end = get_time_ms()
    gc.collect()
    mem_alloc_after = get_mem_alloc()

    elapsed = get_time_diff(end, start)
    total_packets = ITERATIONS * packets_count
    speed = total_packets / (elapsed / 1000)

    mem_delta = mem_alloc_after - mem_alloc_before

    print(f"\n=== micropyGPS ===")
    print(f"Packets processed: {total_packets}")
    print(f"Duration of execution: {elapsed:.1f} ms")
    print(f"Speed: {speed:.0f} pkt/s")
    if _IS_MPY:
        print(f"RAM usage: {mem_delta} bytes")

    return speed


_WIDTH = 60


@native
def main():
    if _IS_MPY and (not _HAS_NATIVE and not _HAS_VIPER):
        print('\n')
        print("WARNING: Code is running in interpreter mode!")
        print("To speed up execution, use firmware with native/viper support!")

    print()
    print("=" * _WIDTH)
    print("NMEA parser benchmark")
    print("=" * _WIDTH)
    print(f"Iterations: {ITERATIONS}")
    print(f"NMEA-0183 Packets per iteration: {len(TEST_PACKETS)}")

    speed_light = benchmark_light_nmea()
    speed_micro = benchmark_micropygps()

    if speed_micro > 0:
        print(f"\n=== Comparison ===")
        if speed_light >= speed_micro:
            ratio = speed_light / speed_micro
            print(f"light_nmea is {ratio:.1f}x times faster.")
        else:
            ratio = speed_micro / speed_light
            print(f"micropyGPS is {ratio:.1f}x times faster.")

    print("\n" + "=" * _WIDTH)


if __name__ == "__main__":
    main()