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

"""Базовый интерфейс для GNSS-парсеров NMEA-0183.
Определяет интерфейс, который обязан реализовать любой парсер, чтобы работать с NMEAStreamReader."""

try:
    from micropython import const, native
except ImportError:
    def const(val):
        return val
    def native(func):
        return func


class IGNSSParser:
    """Базовый интерфейс для всех GNSS-парсеров NMEA-0183.

    Внимание: далее под словами 'поставщик данных' подразумевается: поставщиком 'предложений' или 'sentences' в стандарте NMEA-183!
    Пример минимальной реализации:

        class MyParser(IGNSSParser):
            def is_valid(self) -> bool:
                return self._valid

            def get_constellation(self) -> int:
                return self._constellation

            def parse_line(self, line_bytes: bytes, start: int, end: int) -> bool:
                # парсинг NMEA-строки
                return True

            def reset(self) -> None:
                self._valid = False
                self._constellation = 0
    """
    INTERFACE_VERSION = 0b0001_0001

    def is_valid(self) -> bool:
        """
        Возвращает флаг валидности текущего состояния парсера.

        True  — парсер имеет валидные данные (фикс, координаты и т.п.).
        False — данные отсутствуют или невалидны.

        Используется поставщиком данных в callback-функции для статистики.

        Returns:
            bool: True если данные валидны, иначе False.

        Raises:
            NotImplementedError: Если метод не переопределён в наследнике.
        """
        raise NotImplementedError(
            "Метод is_valid() должен быть реализован в классе-наследнике IGNSSParser"
        )

    def get_constellation(self) -> int:
        """
        Возвращает числовой идентификатор текущего созвездия GNSS.

        Значения идентификаторов (стандартные константы CST_*):
            0 — неизвестное созвездие (CST_UNKNOWN)
            1 — GPS
            2 — GLONASS
            3 — Galileo
            4 — BeiDou
            5 — QZSS
            6 — NavIC (IRNSS)
            7 — Multi-GNSS (смешанное решение)

        Если созвездие не определено, метод должен вернуть 0 (CST_UNKNOWN).

        Returns:
            int: Идентификатор созвездия (0..7).

        Raises:
            NotImplementedError: Если метод не переопределён в наследнике.
        """
        raise NotImplementedError(
            "Метод get_constellation() должен быть реализован в классе-наследнике IGNSSParser"
        )

    def parse_line(self, line_bytes: bytes, start: int, end: int) -> bool:
        """
        Парсит одну NMEA-строку из байтового буфера.

        Главный метод парсера. Вызывается поставщиком данных для каждого
        завершённого пакета (от '$' до CR+LF включительно).

        Аргументы:
            line_bytes (bytes|bytearray): Буфер, содержащий NMEA-строку.
                Парсер НЕ должен модифицировать буфер и НЕ должен сохранять
                ссылку на него после возврата из метода.
            start (int): Индекс первого байта строки (включительно).
                Обычно указывает на символ '$'.
            end (int): Индекс конца строки (не включительно).
                Обычно указывает на байт сразу после '\\n'.

        Возвращает:
            bool: True  — пакет распознан и успешно обработан.
                  False — пакет не распознан (неизвестный тип) или отклонён
                          (ошибка CRC, слишком короткий и т.п.).

        Raises:
            NotImplementedError: Если метод не переопределён в наследнике.
        """
        raise NotImplementedError(
            "Метод parse_line(line_bytes, start, end) должен быть реализован "
            "в классе-наследнике IGNSSParser"
        )

    def reset(self) -> None:
        """
        Сбрасывает внутреннее состояние парсера к значениям по умолчанию.

        Вызывается при:
            - изменении скорости UART,
            - обнаружении сбоев UART (переполнение буфера, потеря синхронизации),
            - потере питания GNSS-модуля,
            - явном запросе пользователя.

        После вызова reset() парсер должен находиться в состоянии,
        эквивалентном только что созданному экземпляру:
            - is_valid() возвращает False,
            - get_constellation() возвращает 0,
            - все внутренние счётчики и буферы очищены.

        Raises:
            NotImplementedError: Если метод не переопределён в наследнике.
        """
        raise NotImplementedError(
            "Метод reset() должен быть реализован в классе-наследнике IGNSSParser"
        )


# Псевдоним типа для использования в аннотациях NMEAStreamReader.
# В MicroPython аннотации типов не проверяются runtime, но помогают IDE.
GNSSParser = IGNSSParser