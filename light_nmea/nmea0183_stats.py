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

import gc
import sys
import time
from array import array

# Импортирую константы из парсера
try:
    from light_nmea.nmea0183_parser import (
        FIX_AUTONOMOUS, FIX_DGPS, FIX_ESTIMATED, FIX_NOT_VALID,
        FIX_RTK_FIXED, FIX_RTK_FLOAT,
        CST_UNKNOWN, CST_GPS, CST_GLONASS, CST_GALILEO,
        CST_BEIDOU, CST_QZSS, CST_NAVIC, CST_MULTI
    )
except ImportError:
    try:
        # Для обычного Python (CPython) внутри пакета
        from .nmea0183_parser import (
            FIX_AUTONOMOUS, FIX_DGPS, FIX_ESTIMATED, FIX_NOT_VALID,
            FIX_RTK_FIXED, FIX_RTK_FLOAT,
            CST_UNKNOWN, CST_GPS, CST_GLONASS, CST_GALILEO,
            CST_BEIDOU, CST_QZSS, CST_NAVIC, CST_MULTI
        )
    except ImportError:
        # Для прямого запуска скрипта из его папки
        from nmea0183_parser import (
            FIX_AUTONOMOUS, FIX_DGPS, FIX_ESTIMATED, FIX_NOT_VALID,
            FIX_RTK_FIXED, FIX_RTK_FLOAT,
            CST_UNKNOWN, CST_GPS, CST_GLONASS, CST_GALILEO,
            CST_BEIDOU, CST_QZSS, CST_NAVIC, CST_MULTI
        )

# === Platform detection ===
if hasattr(time, 'ticks_ms'):
    # MicroPython
    def _now_ms() -> int:
        return time.ticks_ms()

    def _diff_ms(start: int, end: int) -> int:
        return time.ticks_diff(end, start)
else:
    # CPython
    def _now_ms() -> float:
        return 1000.0 * time.perf_counter()

    def _diff_ms(start: float, end: float) -> float:
        return end - start


_IS_MPY: bool = hasattr(gc, 'mem_free')
_DELIM: str = "=" * 60

# === Human-readable names (используем импортированные константы) ===
_FIX_MODE_NAMES = {
    FIX_AUTONOMOUS: "Autonomous",
    FIX_DGPS: "DGPS",
    FIX_ESTIMATED: "Estimated",
    FIX_NOT_VALID: "Not Valid",
    FIX_RTK_FIXED: "RTK Fixed",
    FIX_RTK_FLOAT: "RTK Float",
}

_CONSTELLATION_NAMES = {
    CST_UNKNOWN: "Unknown",
    CST_GPS: "GPS",
    CST_GLONASS: "GLONASS",
    CST_GALILEO: "Galileo",
    CST_BEIDOU: "BeiDou",
    CST_QZSS: "QZSS",
    CST_NAVIC: "NAVIC",
    CST_MULTI: "Multi-GNSS",
}


class GPSStats:
    """
    Сборщик статистики работы NMEA-183 парсера.
    Совместим с CPython и MicroPython.
    """

    @staticmethod
    def print_reject_stats(parser) -> None:
        """Печатает статистику причин отклонения пакетов."""
        print("\n=== ПРИЧИНЫ ОТКЛОНЕНИЯ ===")

        # Собираю данные через getattr (безопасно, если счётчики отсутствуют)
        reasons = (
            ("CRC error", getattr(parser, 'reject_crc', 0)),
            ("Unknown constellation", getattr(parser, 'reject_unknown_cst', 0)),
            ("Filtered constellation", getattr(parser, 'reject_filtered_cst', 0)),
            ("Unknown message", getattr(parser, 'reject_unknown_msg', 0)),
            ("Too short", getattr(parser, 'reject_too_short', 0)),
        )

        total_rejected = 0
        for reason, count in reasons:
            if count > 0:
                print(f"  {reason:25s}: {count:6d}")
                total_rejected += count

        if total_rejected == 0:
            print("  (нет отклонённых пакетов)")
        else:
            print(f"  {'ИТОГО':25s}: {total_rejected:6d}")


    def __init__(self) -> None:
        self.total: int = 0
        self.recognized: int = 0
        self.valid_fix: int = 0
        self.no_fix: int = 0
        self.rejected: int = 0

        # Статистика по созвездиям (индекс = значение константы CST_*)
        # 8 элементов: индексы 1-7 для всех возможных созвездий, 0 для неизвестного созвездия
        self.cst_counts = array("l", [0] * 8)

        self._start_ms = 0
        self._elapsed_ms = 0
        self._memory_before_kb: float = 0.0
        self._memory_after_kb: float = 0.0

    def reset(self) -> None:
        """Сброс всех счётчиков."""
        self.total = 0
        self.recognized = 0
        self.valid_fix = 0
        self.no_fix = 0
        self.rejected = 0

        # Сброс статистики по созвездиям
        for i in range(len(self.cst_counts)):
            self.cst_counts[i] = 0

        self._start_ms = 0
        self._elapsed_ms = 0
        self._memory_before_kb = 0.0
        self._memory_after_kb = 0.0

    def start(self) -> None:
        """Запуск таймера и замера памяти."""
        self._start_ms = _now_ms()
        self._memory_before_kb = self.get_memory_usage(force_gc=True)

    def stop(self) -> None:
        """Остановка таймера и замера памяти."""
        if self._start_ms > 0:
            self._elapsed_ms = _diff_ms(self._start_ms, _now_ms())
        self._memory_after_kb = self.get_memory_usage(force_gc=True)

    def update(self, recognized: bool, valid: bool, constellation: int = CST_UNKNOWN) -> None:
        self.total += 1

        if recognized:
            self.recognized += 1
            # Считаем созвездие ТОЛЬКО для распознанных пакетов
            if 0 <= constellation < len(self.cst_counts):
                self.cst_counts[constellation] += 1  # только для распознанных
            if valid:
                self.valid_fix += 1
            else:
                self.no_fix += 1
        else:
            self.rejected += 1

    @property
    def packets_per_sec(self) -> float:
        """Скорость обработки (пакетов в секунду)."""
        if self._elapsed_ms <= 0:
            return 0.0
        return self.total * 1000.0 / self._elapsed_ms

    @property
    def memory_delta_kb(self) -> float:
        """Дельта памяти за время теста (КБ)."""
        return self._memory_after_kb - self._memory_before_kb

    @staticmethod
    def get_memory_usage(force_gc: bool = False) -> float:
        """Возвращает объём используемой памяти в Килобайтах."""
        if _IS_MPY:
            if force_gc:
                gc.collect()
            return float(gc.mem_alloc() / 1024)

        if sys.platform == 'linux':
            try:
                with open('/proc/self/status', 'r') as f:
                    for line in f:
                        if line.startswith('VmRSS:'):
                            parts = line.split()
                            return float(parts[1])
            except (OSError, ValueError, IndexError):
                return -1.0

        elif sys.platform == 'darwin':
            try:
                import resource
                usage = resource.getrusage(resource.RUSAGE_SELF)
                return float(usage.ru_maxrss / 1024)
            except (ImportError, AttributeError):
                return -1.0

        elif sys.platform == 'win32':
            try:
                import ctypes
                import ctypes.wintypes

                class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                    _fields_ = [
                        ("cb", ctypes.wintypes.DWORD),
                        ("PageFaultCount", ctypes.wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t),
                    ]

                pmc = PROCESS_MEMORY_COUNTERS()
                pmc.cb = ctypes.sizeof(pmc)
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                ctypes.windll.psapi.GetProcessMemoryInfo(
                    handle, ctypes.byref(pmc), pmc.cb
                )
                return float(pmc.WorkingSetSize / 1024)
            except (OSError, AttributeError):
                return -1.0

        return -1.0

    def _pct(self, count: int) -> str:
        """Вспомогательный метод для вывода процентов."""
        if self.total == 0:
            return "0.0%"
        return f"{count * 100.0 / self.total:.1f}%"

    def report(self, aborted: int = 0) -> None:
        """Печатает итоговый отчёт в консоль."""
        self.stop()

        print("\n" + _DELIM)
        print("=== ИТОГОВАЯ СТАТИСТИКА ===")
        print(f"Всего пакетов:       {self.total}")
        print(f"Распознано:          {self.recognized} ({self._pct(self.recognized)})")
        print(f"  С фиксом:          {self.valid_fix} ({self._pct(self.valid_fix)})")
        print(f"  Без фикса:        {self.no_fix} ({self._pct(self.no_fix)})")
        print(f"Отклонено:           {self.rejected} ({self._pct(self.rejected)})")
        if aborted > 0:
            print(f"Оборвано (UART):     {aborted}")

        # Вывод статистики по созвездиям
        print("\n--- Статистика по созвездиям ---")
        has_any_cst = False
        for cst_idx in range(len(self.cst_counts)):
            count = self.cst_counts[cst_idx]
            if count > 0:
                has_any_cst = True
                cst_name = _CONSTELLATION_NAMES.get(cst_idx, f"CST_{cst_idx}")
                print(f"  {cst_name:12s}: {count:6d} ({self._pct(count)})")
        if not has_any_cst:
            print("  (нет данных)")
        print("----------------------------------")

        print(_DELIM)
        print(f"Время выполнения:    {self._elapsed_ms:.1f} мс")
        print(f"Скорость обработки:  {self.packets_per_sec:.0f} пакетов/сек")
        print(_DELIM)
        print(f"Память до теста:     {self._memory_before_kb:.1f} КБ")
        print(f"Память после теста:  {self._memory_after_kb:.1f} КБ")
        print(f"Дельта памяти:       {self.memory_delta_kb:+.1f} КБ")
        print(_DELIM)

    @staticmethod
    def print_state(gps) -> None:
        """Печатает финальное состояние парсера."""
        print("\n=== ФИНАЛЬНОЕ СОСТОЯНИЕ ПАРСЕРА ===")
        print(f"valid:         {gps.valid}")
        print(f"constellation: {_CONSTELLATION_NAMES.get(gps.constellation, 'Unknown')}")
        print(f"fix_mode:      {_FIX_MODE_NAMES.get(gps.fix_mode, 'Unknown')}")

        if gps.has_coordinates():
            print(f"latitude:      {gps.latitude:.6f}")
            print(f"longitude:     {gps.longitude:.6f}")
        else:
            print("latitude:      N/A")
            print("longitude:     N/A")

        if gps.has_navigation():
            print(f"speed:         {gps.speed:.1f} км/ч")
            print(f"course:        {gps.course:.1f}°")
        else:
            print("speed:         N/A")
            print("course:        N/A")

        if gps.has_3d_fix():
            print(f"altitude:      {gps.altitude:.1f} м")
        else:
            print("altitude:      N/A")

        print(f"satellites:    {gps.satellites}")
        if hasattr(gps, 'hdop') and gps.hdop is not None:
            print(f"hdop:          {gps.hdop:.1f}")
        else:
            print("hdop:          N/A")

        print(f"date:          {gps.date.decode() if gps.date else ''}")
        print(f"time:          {gps.time.decode() if gps.time else ''}")
        print(_DELIM)

