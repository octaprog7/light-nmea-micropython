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

# Настройка const для MicroPython / CPython
try:
    # MicroPython
    from micropython import const
except ImportError:
    # CPython
    def const(x):
        return x

try:
    # MicroPython
    from micropython import native
except ImportError:
    # CPython
    def native(func):
        return func

# Для кроссплатформенной работы с интервалами времени
try:
    # MicroPython
    from time import ticks_ms, ticks_diff
except ImportError:
    # CPython
    import time as _time

    def ticks_ms():
        """Аналог ticks_ms для CPython (возвращает мс с момента старта)."""
        return int(1_000 * _time.monotonic())


    def ticks_diff(t1, t2):
        """Аналог ticks_diff для CPython (monotonic не переполняется)."""
        return t1 - t2


# Типы NMEA сообщений
# для анти-спам фильтра
_MSG_UNKNOWN = 0
_MSG_GGA = 1
_MSG_RMC = 2

# Постоянные для определения типа сообщения
_GGA_SUB = b"GGA"
_RMC_SUB = b"RMC"

_MAX_CHUNK = const(512)
_LINE_BUFFER_SIZE = const(256)
_DOLLAR = const(36)
_CR = const(13)
_LF = const(10)
_MIN_PACKET_LEN = const(8)

@native
def _get_msg_type(buf: bytes, start, end) -> int:
    """Определяет тип сообщения по фиксированной позиции в NMEA пакете.
    Returns:
        int: _MSG_GGA, _MSG_RMC или _MSG_UNKNOWN"""
    if end - start < 7:
        return _MSG_UNKNOWN

    stop = start + 6
    # Ищу только в первых 7 символах (позиции 3-5)
    if buf.find(_GGA_SUB, start, stop) == start + 3:
        return _MSG_GGA

    if buf.find(_RMC_SUB, start, stop) == start + 3:
        return _MSG_RMC

    return _MSG_UNKNOWN

from light_nmea.gnss_parser_base import IGNSSParser

class NMEAStreamReader:
    """Автоматический считыватель потоковых пакетов NMEA-0183 на MicroPython."""

    def __init__(self, uart_instance):
        """Первичная настройка читателя.
        :param uart_instance: Настроенный(!) объект machine.UART
        """
        self._uart = uart_instance
        # Буфер для пакетов
        self._line_buffer = bytearray(_LINE_BUFFER_SIZE)
        # курсор
        self._pos = 0

        # Static read buffer (Zero-Allocation)
        self._read_buffer = bytearray(_MAX_CHUNK)

        # Счетчик неполных пакетов (для диагностики помех UART)
        self.packets_aborted = 0
        # Общее кол-во обработанных пакетов
        self.packets_processed = 0

        # настройки анти-спам фильтра пакетов
        # Это защита от слишком частого прихода пакетов GGA и RMC от GNSS приемника
        self._anti_spam_min_ms = 0  # 0 = отключено (передавать все)
        self._anti_spam_last_gga = 0  # Время последнего GGA
        self._anti_spam_last_rmc = 0  # Время последнего RMC
        # Статистика
        # Сколько пакетов отфильтровано Анти-спам фильтром
        self.anti_spam_dropped = 0  # Сколько пакетов отфильтровано

    def _should_filter(self, msg_type: int) -> bool:
        """Проверить, нужно ли отбросить пакет из-за анти-спам фильтра."""
        if self._anti_spam_min_ms == 0:
            return False

        now = ticks_ms()

        if msg_type == _MSG_GGA:
            if ticks_diff(now, self._anti_spam_last_gga) < self._anti_spam_min_ms:
                return True
            self._anti_spam_last_gga = now

        elif msg_type == _MSG_RMC:
            if ticks_diff(now, self._anti_spam_last_rmc) < self._anti_spam_min_ms:
                return True
            self._anti_spam_last_rmc = now

        return False

    def set_anti_spam_interval(self, interval: int):
        """Устанавливает минимальный интервал (в мс) между пакетами одного типа.
        Пакеты, пришедшие раньше этого интервала, будут отброшены как спам.
        :param interval: Интервал в миллисекундах (0-1000).
                         0 или None = отключить фильтр (принимать все пакеты).
        :raises ValueError: Если interval < 0 или > 1000."""
        if interval is None or interval == 0:
            self._anti_spam_min_ms = 0
            return
        if 0 < interval < 1_000:
            self._anti_spam_min_ms = interval
            return
        raise ValueError(f"Неверное значение Анти-спам интервала!")


    def reset(self):
        """Сброс состояния курсора буфера и счетчиков.
        Вызывается при изменении скорости, сбоях UART или потере питания GPS."""
        self._pos = 0
        self.packets_aborted = 0
        self.packets_processed = 0
        # Сброс анти-спам фильтра
        self.anti_spam_dropped = 0
        self._anti_spam_last_gga = 0
        self._anti_spam_last_rmc = 0

    def read_available(self, parser: IGNSSParser, callback = None) -> int:
        """
        Считывает все доступные байты из UART, формирует пакеты и отправляет их парсеру.

        :param parser: Объект с методом parse_line(line_bytes: bytes) -> bool
        :param callback: Функция, вызываемая для каждого пакета: callback(recognized, valid, constellation)
        :return: Количество успешно обработанных строк в этом вызове
        """
        waiting = self._uart.any()
        if not waiting:
            return 0

        to_read = min(waiting, _MAX_CHUNK)
        num_bytes = self._uart.readinto(self._read_buffer, to_read)
        if num_bytes is None or num_bytes == 0:
            return 0

        packets_processed = 0
        packets_aborted = self.packets_aborted
        pos = self._pos
        l_buf = self._line_buffer
        buf_size = _LINE_BUFFER_SIZE

        for i in range(num_bytes):
            byte = self._read_buffer[i]

            if byte == _DOLLAR:
                if pos > 0:
                    packets_aborted += 1
                pos = 0
                l_buf[pos] = byte
                pos += 1
            elif pos > 0:
                if pos < buf_size:
                    l_buf[pos] = byte
                    pos += 1
                else:
                    packets_aborted += 1
                    pos = 0
                    continue

                if byte == _LF and l_buf[pos - 2] == _CR:
                    if pos >= _MIN_PACKET_LEN:
                        # Анти-спам фильтр
                        msg_type = _get_msg_type(l_buf, 0, pos)
                        if msg_type != _MSG_UNKNOWN and self._should_filter(msg_type):
                            self.anti_spam_dropped += 1
                            pos = 0
                            continue
                        # передача пакета парсеру
                        recognized = parser.parse_line(l_buf, 0, pos)
                        # Вызов обработчика для статистики
                        if callback is not None:
                            callback(recognized, parser.is_valid(), parser.get_constellation())

                        packets_processed += 1
                    pos = 0

        self._pos = pos
        self.packets_processed += packets_processed
        self.packets_aborted = packets_aborted
        return packets_processed

    def get_stats(self):
        """Возвращает кортеж, содержащий счетчики обработанных и отброшенных пакетов."""
        return self.packets_processed, self.packets_aborted