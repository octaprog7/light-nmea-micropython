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

# mpy_main.py
import gc
import time
from micropython import const
from machine import UART, Pin, RTC
from light_nmea.nmea0183_parser import LightNMEA
from light_nmea.nmea0183_stats import GPSStats
from light_nmea.nmea0183_stream import NMEAStreamReader
from light_nmea.conv_to_hrf import to_format

# === Конфигурация ===
UART_ID = const(0)
UART_RX_PIN = const(1)
UART_TX_PIN = const(0)
UART_BAUDRATE = const(38400)
UART_BUFFER_SIZE = const(512)

# Примечание: реальные пакеты (GSV, PUBX, PQTM) могут быть длиннее, до 200+ байт
_MAX_NMEA_LENGTH = const(82)  # Стандарт NMEA-0183: макс. длина пакета
_MAX_NMEA_LENGTH_EXTENDED = const(256)  # Для GSV, PUBX, PQTM
GC_CALL_LIMIT = const(100)
STATS_PRINT_LIMIT = const(150)

# Вывод данных пакета в консоль при наличии фикса
print_packet_info: bool = True

# === Инициализация ===
parser = LightNMEA(trust_gga_fix=True, enable_diagnostics=True)
stats = GPSStats()
rtc = RTC()
rtc_synced = False

_DATE_LENGTH = const(6)  # DDMMYY
_MONTHS_30_DAYS = 4, 6, 9, 11  # На уровне модуля


def _is_date_valid(date_bytes: bytes) -> bool:
    """
    Проверяет правильность даты GPS.
    Отсекает значения по умолчанию при `холодном` старте.
    """
    if not date_bytes or len(date_bytes) < _DATE_LENGTH:
        return False
    if date_bytes == b"000000":
        return False
    try:
        day = int(date_bytes[0:2])
        month = int(date_bytes[2:4])
        year = int(date_bytes[4:6])

        # Базовая проверка диапазонов
        if not (1 <= day <= 31 and 1 <= month <= 12 and 0 <= year <= 99):
            return False

        # Дополнительная защита: отсечь "подозрительные" даты
        # Например, 31 февраля не существует
        if 2 == month and day > 29:
            return False
        if month in _MONTHS_30_DAYS and day > 30:
            return False

        return True
    except ValueError:
        return False


def _print_packet_data(my_parser) -> None:
    """Выводит данные пакета в консоль (только при наличии фикса)."""
    print("--- Пакет с фиксом ---")
    print(to_format(my_parser))
    print("--------------------")


def calc_uart_timeout(baudrate: int, max_length: int = _MAX_NMEA_LENGTH, safety_factor: float = 3.0) -> int:
    """Рассчитывает таймаут UART в миллисекундах.

    Args:
        baudrate: Скорость UART (9600, 115200, и т.д.)
        max_length: Максимальная длина NMEA-строки (стандарт = 82 байта)
        safety_factor: Коэффициент запаса (рекомендуется 2.0-5.0)

    Returns:
        Таймаут в миллисекундах (округлённый вверх)"""
    # Время передачи 1 байта в мс (10 бит: 1 старт + 8 данных + 1 стоп)
    t_byte_ms = 10_000 / baudrate  # 10 бит × 1000 мс
    # Время передачи максимальной строки
    t_string_ms = max_length * t_byte_ms
    # Таймаут с запасом
    time_out_ms = int(t_string_ms * safety_factor) + 1  # +1 для округления вверх
    return time_out_ms


timeout_ms = calc_uart_timeout(UART_BAUDRATE, max_length=_MAX_NMEA_LENGTH_EXTENDED, safety_factor=3.0)
timeout_char_ms = timeout_ms // 10  # Таймаут между символами

uart = UART(
    UART_ID,
    baudrate=UART_BAUDRATE,
    rx=Pin(UART_RX_PIN),
    tx=Pin(UART_TX_PIN),
    rxbuf=UART_BUFFER_SIZE,
    timeout=timeout_ms,
    timeout_char=timeout_char_ms
)


# callback для статистики
def stats_callback(recognized, valid, constellation):
    stats.update(recognized, valid, constellation)


reader = NMEAStreamReader(uart)
reader.set_anti_spam_interval(100)


# === Главный цикл ===
stats.start()
print(f"Свободно ОЗУ [КБ]: {stats.get_memory_usage()}")
gc_counter = 0
_RTC_SYNC_MAX_ATTEMPTS = const(5)
rtc_sync_attempts = 0

try:
    last_time_from_gnss = b""
    while True:
        # чтение через NMEAStreamReader
        processed = reader.read_available(parser, stats_callback)

        if processed > 0:
            # Обработка координат
            if parser.has_coordinates():
                # Синхронизация RTC при первом фиксе
                par_time = parser.time
                if not rtc_synced and par_time and _is_date_valid(parser.date):
                    try:
                        parser.sync_hardware_rtc(rtc)
                        rtc_synced = True
                        print(f"RTC синхронизирован: {parser.date} {par_time}")
                    except Exception as e:
                        rtc_sync_attempts += 1
                        print(f"Ошибка синхронизации RTC ({rtc_sync_attempts}/{_RTC_SYNC_MAX_ATTEMPTS}): {e}")
                        if rtc_sync_attempts >= _RTC_SYNC_MAX_ATTEMPTS:
                            rtc_synced = True  # Сдаюсь после _RTC_SYNC_MAX_ATTEMPTS попыток
                            print(f"RTC недоступен после {_RTC_SYNC_MAX_ATTEMPTS} попыток, синхронизация отключена!")

                if par_time != last_time_from_gnss:
                    # Вывод данных пакета при наличии фикса
                    if print_packet_info:
                        _print_packet_data(parser)
                last_time_from_gnss = par_time

            # Вывод статистики
            if stats.total % STATS_PRINT_LIMIT == 0:
                print(f"Пакетов: {stats.total}, "
                      f"Фикс: {stats.valid_fix}, "
                      f"Поиск: {stats.no_fix}, "
                      f"Отклонено: {stats.rejected}, "
                      f"Анти-спам: {reader.anti_spam_dropped},")

            # Принудительный GC
            gc_counter += processed
            if gc_counter >= GC_CALL_LIMIT:
                gc.collect()
                gc_counter = 0

        # Пауза только если нет данных
        if processed == 0:
            time.sleep_ms(10)

except KeyboardInterrupt:
    print("\nОстановка...")
    stats.report()
    GPSStats.print_reject_stats(parser)
    GPSStats.print_state(parser)
    print(f"Оборвано пакетов: {reader.packets_aborted}")
    if 'uart' in locals():
        uart.deinit()

print(f"Свободно ОЗУ [КБ]: {stats.get_memory_usage()}")
