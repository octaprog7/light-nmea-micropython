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

# ======================================================================
# Мост GNSS-модуль (UART) <-> USB-CDC (консоль ПК)
#
# Читает поток NMEA-0183 с GNSS-приёмника по UART, разбирает его
# и выводит в stdout (USB-CDC) в CSV-формате или в расширенном виде.
# Запускается ТОЛЬКО под MicroPython!
#
# Примечание: пробуждение USB-CDC теперь целиком на стороне ПК
# (0x03 -> 0x04), здесь это не требуется.
# ======================================================================

import gc
import time

try:
    from micropython import const
except ImportError:
    print("Error: Code run under MicroPython ONLY!")
    raise

from machine import Pin, RTC, UART

from gnss_module_utils import (
    detect_gnss_module_type,
    gnss_module_id_to_str,
    send_gnss_reset,
)
from light_nmea.conv_to_hrf import FMT_CSV, to_format
from light_nmea.nmea0183_parser import CST_MASK_ALL, LightNMEA
from light_nmea.nmea0183_stats import GNSSStats
from light_nmea.nmea0183_stream import NMEAStreamReader

# === Конфигурация ===
UART_ID = const(0)
UART_RX_PIN = const(1)
UART_TX_PIN = const(0)
UART_BAUDRATE = const(38400)
UART_BUFFER_SIZE = const(512)

# True - выводить только CSV-строки (контракт с дашбордом);
# False - расширенная диагностика в консоль
ONLY_GNSS: bool = True
# Выводить данные пакета в консоль при наличии фикса
PRINT_PACKET_INFO: bool = True

# Реальные пакеты (GSV, PUBX, PQTM) могут быть длиннее стандарта NMEA-0183
_MAX_NMEA_LENGTH = const(82)             # Стандарт NMEA-0183: макс. длина пакета
_MAX_NMEA_LENGTH_EXTENDED = const(256)   # Для GSV, PUBX, PQTM
_UART_TIMEOUT_SAFETY_FACTOR = 3.0        # Коэффициент запаса таймаута UART
_UART_CHAR_TIMEOUT_DIVISOR = const(10)   # Таймаут между символами: timeout // 10

_ANTI_SPAM_INTERVAL_MS = const(100)      # Анти-спам фильтр одинаковых пакетов
_GC_CALL_LIMIT = const(100)              # Принудительный GC каждые N пакетов
_STATS_PRINT_LIMIT = const(150)          # Печать статистики каждые N пакетов

# 90 секунд без валидного фикса от GNSS-модуля приводят к попытке
# программного сброса GNSS-приёмника!
_WATCHDOG_TIMEOUT_MS = const(90_000)
_MODULE_INFO_INTERVAL_MS = const(45_000)  # Напоминание ПК о типе модуля
_RTC_SYNC_MAX_ATTEMPTS = const(5)         # Попыток для синхронизации RTC платы

_RESET_PAUSE_MS = const(2200)  # Пауза после программного сброса GNSS-модуля
_IDLE_PAUSE_MS = const(10)     # Пауза в ожидании данных (разгрузка CPU)
_ERROR_PAUSE_MS = const(50)    # Пауза после ошибки в главном цикле

_DATE_LENGTH = const(6)  # DDMMYY
_MONTHS_30_DAYS = 4, 6, 9, 11

# ID типов системных сообщений для хоста (ПК).
# Синхронизированы с dash_utils.MCU_MSG_*!
MSG_TYPE_MODULE_DETECTED = const(1)
MSG_TYPE_SOFTWARE_RESET = const(2)
MSG_TYPE_WATCHDOG_TRIGGERED = const(3)


def _is_date_valid(date_bytes: bytes) -> bool:
    """Проверяет корректность GPS-даты (отсекает значения «холодного» старта)."""
    if not date_bytes or len(date_bytes) < _DATE_LENGTH:
        return False
    if date_bytes == b"000000":
        return False

    try:
        day = int(date_bytes[0:2])
        month = int(date_bytes[2:4])
        year = int(date_bytes[4:6])
    except ValueError:
        return False

    # Базовая проверка диапазонов
    if not (1 <= day <= 31 and 1 <= month <= 12 and 0 <= year <= 99):
        return False

    # Отсечь несуществующие даты (например, 31 февраля)
    if month == 2 and day > 29:
        return False
    if month in _MONTHS_30_DAYS and day > 30:
        return False

    return True


def _print_packet_data(my_parser: LightNMEA, gnss_only: bool) -> None:
    """Выводит данные пакета в консоль (только при наличии фикса)."""
    if not gnss_only:
        print("--- Packet with fix ---")
    print(to_format(my_parser, FMT_CSV))
    if not gnss_only:
        print("--------------------")


def _calc_uart_timeout(
    baud_rate: int,
    max_length: int = _MAX_NMEA_LENGTH,
    safety_factor: float = _UART_TIMEOUT_SAFETY_FACTOR,
) -> int:
    """Рассчитывает таймаут UART в миллисекундах.

    Args:
        baud_rate: Скорость UART (9600, 115200, ...).
        max_length: Максимальная длина NMEA-строки (стандарт = 82 байта).
        safety_factor: Коэффициент запаса (рекомендуется 2.0-5.0).

    Returns:
        Таймаут в миллисекундах (округлённый вверх).
    """
    # Время передачи 1 байта, мс (10 бит: 1 старт + 8 данных + 1 стоп)
    t_byte_ms = 10_000 / baud_rate
    # Время передачи максимальной строки + запас (+1 для округления вверх)
    return int(max_length * t_byte_ms * safety_factor) + 1


def send_to_host(msg_type_id: int, msg: str) -> None:
    """Отправляет хосту (ПК) системное сообщение.

    Формат: SYS_MSG:<type_id>:<message>
    """
    print(f"SYS_MSG:{msg_type_id}:{msg}")


# === Главный цикл ===
def gnss_mod_to_usb_bridge(
    stats: GNSSStats,
    interface: UART,
    my_parser: LightNMEA,
    module_id: int,
    module_name: str,
) -> None:
    """Пробрасывает поток NMEA из GNSS-модуля в USB-CDC (stdout ПК)."""

    def stats_callback(recognized, valid, constellation):
        """Обработчик статистики для NMEAStreamReader."""
        stats.update(recognized, valid, constellation)

    rtc = RTC()
    reader = NMEAStreamReader(interface)
    reader.set_anti_spam_interval(_ANTI_SPAM_INTERVAL_MS)

    stats.start()
    if not ONLY_GNSS:
        print(f"Free RAM [KB]: {stats.get_memory_usage()}")

    gc_counter = 0
    rtc_sync_attempts = 0
    rtc_synced = False
    last_data_time_ms = time.ticks_ms()
    last_module_info_time = time.ticks_ms()
    last_time_from_gnss = b""

    try:
        while True:
            try:
                # Чтение и разбор всех доступных байтов из UART
                processed = reader.read_available(my_parser, stats_callback)

                if processed > 0:
                    # Watchdog сбрасывается ТОЛЬКО при валидном фиксе
                    # (а не просто при наличии данных)
                    if my_parser.valid:
                        last_data_time_ms = time.ticks_ms()

                    if my_parser.has_coordinates():
                        # Однократная синхронизация аппаратных часов платы
                        if not rtc_synced and my_parser.time and _is_date_valid(my_parser.date):
                            try:
                                my_parser.sync_hardware_rtc(rtc)
                                rtc_synced = True
                                if not ONLY_GNSS:
                                    print(f"RTC is synchronized: {my_parser.date} {my_parser.time}")
                            except Exception as e:
                                rtc_sync_attempts += 1
                                if rtc_sync_attempts >= _RTC_SYNC_MAX_ATTEMPTS:
                                    # Сдаюсь после N попыток
                                    rtc_synced = True
                                    if not ONLY_GNSS:
                                        print(
                                            f"RTC synchronization disabled after "
                                            f"{_RTC_SYNC_MAX_ATTEMPTS} attempts"
                                        )
                                elif not ONLY_GNSS:
                                    print(
                                        f"RTC synchronization error "
                                        f"({rtc_sync_attempts}/{_RTC_SYNC_MAX_ATTEMPTS}): {e}"
                                    )

                        # Вывод нового пакета при наличии фикса
                        if my_parser.time != last_time_from_gnss and my_parser.hdop is not None:
                            if PRINT_PACKET_INFO:
                                _print_packet_data(my_parser, ONLY_GNSS)
                            last_time_from_gnss = my_parser.time

                    # Периодическая печать статистики
                    if not ONLY_GNSS and stats.total % _STATS_PRINT_LIMIT == 0:
                        print(
                            f"Packets: {stats.total}, Fix: {stats.valid_fix}, "
                            f"No fix: {stats.no_fix}, Rejected: {stats.rejected}, "
                            f"Anti-spam: {reader.anti_spam_dropped}"
                        )

                    # Принудительная периодическая сборка мусора
                    gc_counter += processed
                    if gc_counter >= _GC_CALL_LIMIT:
                        gc.collect()
                        gc_counter = 0

                else:
                    # === Сторожевой таймер: данных от GNSS-модуля нет ===
                    elapsed = time.ticks_diff(time.ticks_ms(), last_data_time_ms)
                    if elapsed > _WATCHDOG_TIMEOUT_MS:
                        if not ONLY_GNSS:
                            print(
                                f"!!! WATCHDOG: No data incoming {elapsed} ms. "
                                f"Software module reset !"
                            )
                        # Сообщаю хосту о программном сбросе
                        send_to_host(MSG_TYPE_SOFTWARE_RESET, "software reset started")
                        send_gnss_reset(interface, module_id, not ONLY_GNSS)
                        time.sleep_ms(_RESET_PAUSE_MS)
                        last_data_time_ms = time.ticks_ms()
                        # Очистка входного буфера UART после сброса модуля
                        while interface.any():
                            interface.read(interface.any())
                    else:
                        # Короткая пауза, чтобы не грузить CPU, если данных нет
                        time.sleep_ms(_IDLE_PAUSE_MS)

                # Напоминание ПК о типе модуля
                if time.ticks_diff(time.ticks_ms(), last_module_info_time) > _MODULE_INFO_INTERVAL_MS:
                    send_to_host(MSG_TYPE_MODULE_DETECTED, module_name)
                    last_module_info_time = time.ticks_ms()

            except KeyboardInterrupt:
                raise
            except Exception as e:
                # Защита от тихого 'падения' моста: ошибка чтения UART не должна
                # остановить главный цикл. В режиме ONLY_GNSS вывод в stdout
                # нарушит CSV формат с дашбордой.
                if not ONLY_GNSS:
                    print(f"Bridge loop error: {type(e).__name__}: {e}")
                time.sleep_ms(_ERROR_PAUSE_MS)

    except KeyboardInterrupt:
        if not ONLY_GNSS:
            print("\nStop...")
            stats.report()
            GNSSStats.print_reject_stats(my_parser)
            GNSSStats.print_state(my_parser)
            print(f"Number of packets broken: {reader.packets_aborted}")

    if not ONLY_GNSS:
        print(f"Free RAM [KB]: {stats.get_memory_usage()}")


def main() -> None:
    """Точка входа: настройка UART и запуск моста GNSS -> USB-CDC."""
    # Таймауты UART считаются под самые длинные пакеты (GSV, PUBX, PQTM)
    timeout_ms = _calc_uart_timeout(
        UART_BAUDRATE,
        max_length=_MAX_NMEA_LENGTH_EXTENDED,
        safety_factor=_UART_TIMEOUT_SAFETY_FACTOR,
    )
    timeout_char_ms = timeout_ms // _UART_CHAR_TIMEOUT_DIVISOR

    uart = UART(
        UART_ID,
        baudrate=UART_BAUDRATE,
        rx=Pin(UART_RX_PIN),
        tx=Pin(UART_TX_PIN),
        rxbuf=UART_BUFFER_SIZE,
        timeout=timeout_ms,
        timeout_char=timeout_char_ms,
    )
    try:
        # === Инициализация ===
        # Определение производителя GNSS-модуля по ответу на запрос версии
        module_id = detect_gnss_module_type(uart)
        module_name = gnss_module_id_to_str(module_id)
        if not ONLY_GNSS:
            print(f"Detected GNSS module: {module_name}")

        # Сообщаю ПК тип модуля
        send_to_host(MSG_TYPE_MODULE_DETECTED, module_name)
        uart.flush()

        parser = LightNMEA(trust_gga_fix=True, enable_diagnostics=True)
        parser.set_cst_filter(CST_MASK_ALL)

        stats = GNSSStats()
        gnss_mod_to_usb_bridge(stats, uart, parser, module_id, module_name)
    finally:
        uart.deinit()


if __name__ == "__main__":
    main()
