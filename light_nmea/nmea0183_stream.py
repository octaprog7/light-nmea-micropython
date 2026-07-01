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
# === Module constants ===

from micropython import const

_MAX_CHUNK = const(512)
_LINE_BUFFER_SIZE = const(256)
_DOLLAR = const(36)
_CR = const(13)
_LF = const(10)
_MIN_PACKET_LEN = const(8)


class NMEAStreamReader:
    """Автоматический считыватель потоковых пакетов NMEA-0183 на MicroPython."""

    def __init__(self, uart_instance):
        """Первичная настройка читателя.
        :param uart_instance: Настроенный(!) объект machine.UART
        """
        self._uart = uart_instance
        # Буфер для пакетов
        self._line_buffer = bytearray(_LINE_BUFFER_SIZE)
        # ссылка на self._line_buffer без копирования байт и без выделения памяти
        # self._line_view = memoryview(self._line_buffer)
        # курсор
        self._pos = 0

        # Static read buffer (Zero-Allocation)
        self._read_buffer = bytearray(_MAX_CHUNK)

        # Aborted packets counter (for UART interference diagnostics)
        # Counts NMEA packets that were not completed correctly (no \r\n).
        self.packets_aborted = 0
        # Processed packets counter
        self.packets_processed = 0

    def reset(self):
        """Сброс состояния курсора буфера и счетчиков.
        Вызывается при изменении скорости, сбоях UART или потере питания GPS."""
        self._pos = 0
        self.packets_aborted = 0
        self.packets_processed = 0

    def read_available(self, parser, callback = None) -> int:
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
        # line_view = self._line_view
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
                        # Из-за того, что memoryview не имеет метода find, в парсере приходится лишнее копирование в буфер.
                        # memoryview оказался перегружен разными Strides, cast("X"), reshape((X, Y)).
                        # Из-за этого простейший find оказался 'лишним'! И теперь приходится выделять абсолютно лишний буфер в ОЗУ, которого у микроконтроллеров 'кот наплакал'.
                        recognized = parser.parse_line(l_buf, 0, pos)
                        # Вызов обработчика для статистики
                        if callback is not None:
                            callback(recognized, parser.valid, parser.constellation)

                        packets_processed += 1
                    pos = 0

        self._pos = pos
        self.packets_processed += packets_processed
        self.packets_aborted = packets_aborted
        return packets_processed

    def get_stats(self):
        """Возвращает кортеж, содержащий счетчики обработанных и отброшенных пакетов."""
        return self.packets_processed, self.packets_aborted