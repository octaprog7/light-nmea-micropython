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

# uart_test.py - минимальный тест UART
import time
from micropython import const
from machine import UART, Pin


# Конфиг
UART_ID = const(0)
UART_RX_PIN = const(1)
UART_TX_PIN = const(0)
UART_BAUDRATE = const(38400)

print("=== Тест UART GPS ===")
uart = UART(UART_ID, baudrate=UART_BAUDRATE, rx=Pin(UART_RX_PIN), tx=Pin(UART_TX_PIN), rxbuf=512, timeout=100)

print(f"UART_BAUDRATE: {UART_BAUDRATE}")

for i in range(10):
    data = uart.read()
    if data:
        print(f"[{i}] Получено {len(data)} байт:")
        print(data[:100])
    else:
        print(f"[{i}] Пусто")
    time.sleep_ms(1000)

uart.deinit()
print("=== Конец теста ===")