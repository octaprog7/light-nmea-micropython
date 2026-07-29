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
from light_nmea.conv_to_hrf import to_format, FMT_CSV
from gnss_module_utils import detect_gnss_module_type, send_gnss_reset, gnss_module_id_to_str

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
# Если истина, то выводит только данные в CSV
only_gnss : bool = True

# === Инициализация ===
parser = LightNMEA(trust_gga_fix=True, enable_diagnostics=True)
stats = GPSStats()
rtc = RTC()
# 15 секунд без приема данных от GNSS модуля приводят
# к ПОПЫТКЕ программного сброса модуля GNSS-приемника!
WATCHDOG_TIMEOUT_MS = const(15000)
MODULE_INFO_INTERVAL_MS = const(30_000)
# Кол-во попыток синхронизации ИС RTC на плате.
_RTC_SYNC_MAX_ATTEMPTS = const(5)


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


def _print_packet_data(my_parser, gnss_only: bool = True) -> None:
    """Выводит данные пакета в консоль (только при наличии фикса)."""
    if gnss_only:
        print(to_format(my_parser, FMT_CSV))
        return
    print("--- Packet with fix ---")
    print(to_format(my_parser, FMT_CSV))
    print("--------------------")


def calc_uart_timeout(baud_rate: int, max_length: int = _MAX_NMEA_LENGTH, safety_factor: float = 3.0) -> int:
    """Рассчитывает таймаут UART в миллисекундах.

    Args:
        baud_rate: Скорость UART (9600, 115200, и т.д.)
        max_length: Максимальная длина NMEA-строки (стандарт = 82 байта)
        safety_factor: Коэффициент запаса (рекомендуется 2.0-5.0)

    Returns:
        Таймаут в миллисекундах (округлённый вверх)"""
    # Время передачи 1 байта в мс (10 бит: 1 старт + 8 данных + 1 стоп)
    t_byte_ms = 10_000 / baud_rate  # 10 бит × 1000 мс
    # Время передачи максимальной строки
    t_string_ms = max_length * t_byte_ms
    # Таймаут с запасом
    time_out_ms = int(t_string_ms * safety_factor) + 1  # +1 для округления вверх
    return time_out_ms

# ID типов GNSS-модулей
MODULE_UNKNOWN = const(0)
MODULE_UBLOX = const(1)
MODULE_QUECTEL = const(2)
MODULE_MEDIATEK = const(3)

# ID типов системных сообщений для хоста (ПК)
MSG_TYPE_MODULE_DETECTED = const(1)
MSG_TYPE_SOFTWARE_RESET = const(2)
MSG_TYPE_WATCHDOG_TRIGGERED = const(3)

def send_to_host(msg_type_id: int, msg: str) -> None:
    """Отправляет форматированное системное сообщение хосту (ПК).
    Формат: SYS_MSG:<type_id>:<message>\\r\\n
    """
    print(f"SYS_MSG:{msg_type_id}:{msg}")

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

uart.flush()

# callback для статистики
def stats_callback(recognized, valid, constellation):
    stats.update(recognized, valid, constellation)


reader = NMEAStreamReader(uart)
reader.set_anti_spam_interval(100)

current_module_id = detect_gnss_module_type(uart)
module_name = gnss_module_id_to_str(current_module_id)
if not only_gnss:
    print(f"Detected GNSS module: {module_name}")
# Отправляю хосту информацию о производителе модуля GNSS, подключенного по UART к плате с MicroPython
send_to_host(MSG_TYPE_MODULE_DETECTED, module_name)

# === Главный цикл ===
def gnss_mod_to_usb_bridge() -> None:
    rtc_synced = False
    stats.start()
    if not only_gnss:
        print(f"Free RAM [KB]: {stats.get_memory_usage()}")
    gc_counter = 0
    rtc_sync_attempts = 0
    last_data_time_ms = time.ticks_ms()
    last_module_info_time = time.ticks_ms()

    try:
        last_time_from_gnss = b""
        while True:
            # чтение через NMEAStreamReader
            processed = reader.read_available(parser, stats_callback)

            if processed > 0:
                if parser.valid: # сброс таймера при принятии данных от модуля GNSS
                    last_data_time_ms = time.ticks_ms()
                # Обработка координат
                if parser.has_coordinates():
                    # Синхронизация RTC при первом фиксе
                    par_time = parser.time
                    if not rtc_synced and par_time and _is_date_valid(parser.date):
                        try:
                            parser.sync_hardware_rtc(rtc)
                            rtc_synced = True
                            if not only_gnss:
                                print(f"RTC is synchronized: {parser.date} {par_time}")
                        except Exception as e:
                            rtc_sync_attempts += 1
                            if not only_gnss:
                                print(f"RTC synchronization error ({rtc_sync_attempts}/{_RTC_SYNC_MAX_ATTEMPTS}): {e}")
                            if rtc_sync_attempts >= _RTC_SYNC_MAX_ATTEMPTS:
                                rtc_synced = True  # Сдаюсь после _RTC_SYNC_MAX_ATTEMPTS попыток
                                if not only_gnss:
                                    print(f"RTC not available after {_RTC_SYNC_MAX_ATTEMPTS} attempts, synchronization disabled!")

                    if par_time != last_time_from_gnss and parser.hdop is not None:
                        # Вывод данных пакета при наличии фикса
                        if print_packet_info:
                            _print_packet_data(parser)
                    last_time_from_gnss = par_time

                # Вывод статистики
                if not only_gnss:
                    if stats.total % STATS_PRINT_LIMIT == 0:
                        print(f"Пакетов: {stats.total}, Фикс: {stats.valid_fix}, Поиск: {stats.no_fix}, Отклонено: {stats.rejected}, Анти-спам: {reader.anti_spam_dropped}")

                # Принудительный GC
                gc_counter += processed
                if gc_counter >= GC_CALL_LIMIT:
                    gc.collect()
                    gc_counter = 0
            else:
                # WATCHDOG. Данные не приходят
                elapsed = time.ticks_diff(time.ticks_ms(), last_data_time_ms)
                if elapsed > WATCHDOG_TIMEOUT_MS:
                    if not only_gnss:
                        print(f"!!! WATCHDOG: No data incoming {elapsed} ms. Software module reset !")
                    # Уведомляю Host о программном сбросе!
                    send_to_host(MSG_TYPE_SOFTWARE_RESET, "software reset started")
                    send_gnss_reset(uart, current_module_id, not only_gnss)
                    time.sleep_ms(2200)
                    last_data_time_ms = time.ticks_ms()
                    while uart.any():
                        uart.read(uart.any())
                else:
                    # Короткая пауза, чтобы не грузить CPU, если данных нет
                    time.sleep_ms(10)

            # отправка имени производителя GNSS приемника
            # напоминаю ПК о типе модуля
            if time.ticks_diff(time.ticks_ms(), last_module_info_time) > MODULE_INFO_INTERVAL_MS:
                send_to_host(MSG_TYPE_MODULE_DETECTED, module_name)
                last_module_info_time = time.ticks_ms()

    except KeyboardInterrupt:
        if not only_gnss:
            print("\nStop...")
            stats.report()
            GPSStats.print_reject_stats(parser)
            GPSStats.print_state(parser)
            print(f"Number of packets broken: {reader.packets_aborted}")
            if 'uart' in locals():
                uart.deinit()

    if not only_gnss:
        print(f"Free RAM [KB]: {stats.get_memory_usage()}")

if __name__ == "__main__":
    gnss_mod_to_usb_bridge()