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

# gnss_rec_usb_cdc.py

"""EN: Reads everything arriving via UART and forwards it to sys.stdout.
For those who do not have a GNSS receiver with a USB output to feed the NMEA stream into gnss_dashboard for parsing.

RU: Читает все, что приходит по UART и пересылает это в sys.stdout.
Для тех, у кого нет GNSS-приемника с USB выходом, чтобы передать NMEA-поток в gnss_dashboard для парсинга."""

# import gc
import sys
import time

try:
    # Пробуждение USB-CDC теперь целиком на стороне ПК (0x03 -> 0x04)!
    from micropython import const
except ImportError as ex:
    print("Error: Code run under MicroPython ONLY!")
    raise ex


from machine import UART, Pin

# === Конфигурация ===
UART_ID = const(0)
UART_RX_PIN = const(1)
UART_TX_PIN = const(0)
UART_BAUD_RATE = const(38400)
UART_BUFFER_SIZE = const(512)

# Примечание: реальные пакеты (GSV, PUBX, PQTM) могут быть длиннее, до 200+ байт
_MAX_NMEA_LENGTH = const(82)  # Стандарт NMEA-0183: макс. длина пакета
_MAX_NMEA_LENGTH_EXTENDED = const(256)  # Для GSV, PUBX, PQTM
GC_CALL_LIMIT = const(100)
STATS_PRINT_LIMIT = const(150)

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

timeout_ms = calc_uart_timeout(UART_BAUD_RATE, max_length=_MAX_NMEA_LENGTH_EXTENDED, safety_factor=3.0)
timeout_char_ms = timeout_ms // 10  # Таймаут между символами

uart = UART(
    UART_ID,
    baudrate=UART_BAUD_RATE,
    rx=Pin(UART_RX_PIN),
    tx=Pin(UART_TX_PIN),
    rxbuf=UART_BUFFER_SIZE,
    timeout=timeout_ms,
    timeout_char=timeout_char_ms
)

# размер буфера для чтения
BUF_CHUNK_SIZE = const(256)
MAX_BYTES_READ = BUF_CHUNK_SIZE // 2
# для снижения загрузки MCU
NO_LOAD_MS = const(20)

# === Главный цикл ===
def gnss_rec_to_usb_bridge(buf: bytearray, interface: UART, destination: "typing.BinaryIO") -> None:
    """Читает данные из interface кусками размером в buf и отправляет кусками в destination."""
    try:
        while True:
            try:
                # получаю кол-во байт, которое может быть вычитано
                waiting = interface.any()
                if waiting >= len(buf):
                    # читаю в буфер
                    ret_val = interface.readinto(buf, waiting)
                    if ret_val is None:
                        # Возвращаемое readinto значение: количество байтов, считанных и записанных в buf,
                        # или None, при истечении времени ожидания.
                        continue
                    # записываю в sys.stdout
                    destination.write(buf)
                    # Сброс буфера, если есть(!) такая возможность
                    if hasattr(destination, "flush"):
                        destination.flush()
                # Чтобы не грузить CPU/MCU. Для накопления данных.
                time.sleep_ms(NO_LOAD_MS)
            finally:
                pass
    except KeyboardInterrupt as Ex:
        raise Ex


if __name__ == "__main__":
    # выделяю буфер для чтения
    chunk = bytearray(BUF_CHUNK_SIZE)
    try:
        gnss_rec_to_usb_bridge(chunk, uart, sys.stdout.buffer)
    finally:
        uart.deinit()