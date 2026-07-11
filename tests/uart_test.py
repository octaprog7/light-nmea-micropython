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

# uart_test.py - Тест UART с автоопределением скорости и частоты
import time
try:
    from micropython import const
    from machine import UART, Pin
except ImportError:
    import sys
    print("Work ONLY under MicroPython! Work aborted!")
    sys.exit(-1)

# Конфигурация UART
UART_ID = const(0)
UART_RX_PIN = const(1)
UART_TX_PIN = const(0)
UART_BUFFER_SIZE = const(4096)
UART_TIMEOUT_MS = const(100)

# Скорости для автоопределения
_PROBE_BAUDRATES = 9600, 19200, 38400, 57600, 115200, 230400
_DEFAULT_BAUDRATE = const(9600)

# Частоты обновления
_DEFAULT_RATE_HZ = const(1)
_STANDARD_RATES = 1, 2, 4, 5, 10, 20, 25

# Параметры определения частоты
_RATE_DETECT_DURATION_MS = const(3000)
_RATE_DETECT_DURATION_SEC = const(3)
_MIN_SLEEP_MS = const(50)
_MAX_SLEEP_MS = const(2000)

# Параметры теста
_TEST_ITERATIONS = const(10)
_COLLECT_SLEEP_MS = const(10)
_PROBE_WAIT_MS = const(200)
_READ_WAIT_MS = const(1000)
_BAUD_PROBE_DELAY_MS = const(100)

# NMEA префиксы
_NMEA_PREFIXES = b'$GN', b'$GP', b'$GL', b'$GA', b'$GB', b'$GQ'

# Повторяющиеся байтовые последовательности
_CRLF = b'\r\n'
_RMC_KEYWORD = b'RMC'
_MS_PER_SEC = const(1000)
_WIDTH = 60

def _has_nmea(data):
    """Проверяет наличие NMEA-предложений в данных."""
    if not data:
        return False
    for prefix in _NMEA_PREFIXES:
        if prefix in data:
            return True
    return False


def _count_rmc_sentences(data):
    """Подсчитывает количество RMC-предложений в данных.
    Возвращает количество найденных RMC-предложений.
    """
    count = 0
    pos = 0

    while True:
        idx = data.find(_RMC_KEYWORD, pos)
        if idx == -1:
            break

        # Проверяю, что это начало предложения ($GxRMC)
        # Нужно 3 байта перед RMC: $GN, $GP, $GL и т.д.
        if idx >= 3:
            prefix = data[idx - 3:idx]
            if prefix in _NMEA_PREFIXES:
                count += 1

        pos = idx + len(_RMC_KEYWORD)

    return count


def _detect_rate(uart_obj):
    """Определяет частоту обновления путём подсчёта RMC-предложений за время.

    Работает даже без фикса (пустые RMC-предложения).
    Возвращает частоту в Гц (1, 2, 4, 5, 10, 20 и т.д.)
    """
    print("\nОПРЕДЕЛЕНИЕ ЧАСТОТЫ ОБНОВЛЕНИЯ\n")
    print(f"  Сбор данных в течение {_RATE_DETECT_DURATION_MS} мс...")

    buffer = bytearray()
    start = time.ticks_ms()

    while time.ticks_diff(time.ticks_ms(), start) < _RATE_DETECT_DURATION_MS:
        if uart_obj.any():
            chunk = uart_obj.read(uart_obj.any())
            if chunk:
                buffer.extend(chunk)
        time.sleep_ms(_COLLECT_SLEEP_MS)

    # Подсчитываю RMC-предложения (даже пустые)
    rmc_count = _count_rmc_sentences(bytes(buffer))

    if rmc_count == 0:
        print(f"[Внимание] RMC-предложения не найдены")
        print(f"[Внимание] Используется частота по умолчанию: {_DEFAULT_RATE_HZ} Гц")
        return _DEFAULT_RATE_HZ

    # Рассчитываю частоту
    rate_hz = rmc_count / _RATE_DETECT_DURATION_SEC

    # Округляю до ближайшей стандартной частоты
    detected_rate = min(_STANDARD_RATES, key=lambda r: abs(r - rate_hz))

    print(f"RMC-предложений: {rmc_count} за {_RATE_DETECT_DURATION_SEC} сек")
    print(f"Рассчитанная частота: {rate_hz:.2f} Гц")
    print(f"Определена частота: {detected_rate} Гц")

    return detected_rate


def _open_uart(baudrate: int):
    """Открывает UART на указанной скорости."""
    return UART(
        UART_ID,
        baudrate=baudrate,
        rx=Pin(UART_RX_PIN),
        tx=Pin(UART_TX_PIN),
        rxbuf=UART_BUFFER_SIZE,
        timeout=UART_TIMEOUT_MS
    )


def _detect_baudrate()->int:
    """Автоопределение скорости модуля путём перебора стандартных скоростей.
    Возвращает определённую скорость или _DEFAULT_BAUDRATE по умолчанию."""
    print("\nАВТООПРЕДЕЛЕНИЕ СКОРОСТИ\n")

    for baud in _PROBE_BAUDRATES:
        print(f"  Проверка {baud} бод...")

        uart = _open_uart(baud)

        # Ожидаю поступления данных
        time.sleep_ms(_PROBE_WAIT_MS)

        # Чтение накопленных данных
        while uart.any():
            uart.read(uart.any())

        # Читаю свежие данные (ждём достаточно для хотя бы 1 пакета на 1 Гц)
        time.sleep_ms(_READ_WAIT_MS)
        data = uart.read()

        uart.deinit()

        if _has_nmea(data):
            print(f"NMEA-данные обнаружены на скорости {baud} бод")
            print(f"Пример: {data[:80]}")
            return baud

        print(f"[Ошибка] NMEA-данные НЕ получены!")
        time.sleep_ms(_BAUD_PROBE_DELAY_MS)

    print(f"\n[Внимание] Не удалось определить скорость, используется {_DEFAULT_BAUDRATE}")
    return _DEFAULT_BAUDRATE


def _test_uart(uart_obj, rate_hz: int):
    """Тестирует приём данных UART с изменяемым sleep.

        uart_obj: объект UART
        rate_hz: определённая частота обновления в Гц"""
    # Расчет времени sleep на основе частоты
    # Для 1 Гц: 1000 мс, для 10 Гц: 100 мс, для 20 Гц: 50 мс
    sleep_ms = _MS_PER_SEC // rate_hz
    sleep_ms = max(_MIN_SLEEP_MS, min(_MAX_SLEEP_MS, sleep_ms))

    print(f"\nТЕСТ UART (изменяемый sleep: {sleep_ms} мс для {rate_hz} Гц)\n")

    for i in range(_TEST_ITERATIONS):
        data = uart_obj.read()
        if data:
            print(f"[{i}] Получено {len(data)} байт:")
            print(data[:100])
        else:
            print(f"[{i}] Пусто")
        time.sleep_ms(sleep_ms)


def run():
    """Основная функция: автоопределение скорости и частоты, затем тест UART."""
    print("=" * _WIDTH)
    print("ТЕСТ UART GPS С АВТООПРЕДЕЛЕНИЕМ")
    print("=" * _WIDTH)
    print(f"UART: ID={UART_ID}, RX={UART_RX_PIN}, TX={UART_TX_PIN}")

    # Автоопределение скорости
    detected_baud = _detect_baudrate()
    print(f"\nОпределена скорость: {detected_baud}")

    # Открываю UART на определённой скорости
    uart = _open_uart(detected_baud)
    print(f"\nUART открыт на скорости {detected_baud} бод")

    try:
        # Определение частоты обновления
        detected_rate = _detect_rate(uart)

        # Тестирую приём данных с изменяемым sleep
        _test_uart(uart, detected_rate)

        print("\n" + "=" * _WIDTH)
        print("Тест завершён!")
        print(f"Скорость: {detected_baud}")
        print(f"Частота: {detected_rate} Гц")
        print("=" * _WIDTH)

    finally:
        uart.deinit()


if __name__ == '__main__':
    run()