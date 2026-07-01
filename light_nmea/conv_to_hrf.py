# conv_to_hrf.py
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

"""Функции преобразования данных парсера в различные форматы.
Human Readable Format (HRF): TXT, CSV, JSON."""


# Константы для TXT/Compact (без кавычек)
_SATS = "satellites"
_LAT = "latitude"
_LONG = "longitude"
_SPEED = "speed"
_COURSE = "course"
_ALTITUDE = "altitude"
_TIME = "time"
_DATE = "date"

# Константы для JSON (с кавычками)
_JSON_SATS = f'"{_SATS}"'
_JSON_LAT = f'"{_LAT}"'
_JSON_LONG = f'"{_LONG}"'
_JSON_SPEED = f'"{_SPEED}"'
_JSON_COURSE = f'"{_COURSE}"'
_JSON_ALTITUDE = f'"{_ALTITUDE}"'
_JSON_TIME = f'"{_TIME}"'
_JSON_DATE = f'"{_DATE}"'


def to_txt(parser) -> str:
    """Преобразует данные парсера в человекочитаемый формат.

    Args:
        parser: Экземпляр парсера NMEA
    Returns:
        Многострочная строка с навигационными данными"""

    lines = [f"Fix: {'Yes' if parser.valid else 'No'}", f"{_SATS}: {parser.satellites}"]

    # Координаты
    if parser.has_coordinates():
        lines.append(f"{_LAT}: {parser.latitude:.6f}°")
        lines.append(f"{_LONG}: {parser.longitude:.6f}°")

    # 2D навигация
    if parser.has_navigation():
        lines.append(f"{_SPEED}: {parser.speed:.1f} km/h")
        lines.append(f"{_COURSE}: {parser.course:.1f}°")

    # 3D фикс
    if parser.has_3d_fix():
        lines.append(f"{_ALTITUDE}: {parser.altitude:.1f} m")

    # Время и дата
    if parser.time:
        lines.append(f"{_TIME}: {parser.time.decode('ascii')} UTC")
    if parser.date:
        lines.append(f"{_DATE}: {parser.date.decode('ascii')}")

    return '\n'.join(lines)


def to_csv(parser) -> str:
    """Преобразует данные парсера в CSV-строку.

    Формат: valid,sat,lat,lon,speed,course,alt,time,date

    Args:
        parser: Экземпляр парсера NMEA

    Returns:
        CSV-строка
    """
    return (
        f"{int(parser.valid)},"
        f"{parser.satellites},"
        f"{parser.latitude if parser.latitude is not None else ''},"
        f"{parser.longitude if parser.longitude is not None else ''},"
        f"{parser.speed if parser.speed is not None else ''},"
        f"{parser.course if parser.course is not None else ''},"
        f"{parser.altitude if parser.altitude is not None else ''},"
        f"{parser.time.decode('ascii') if parser.time else ''},"
        f"{parser.date.decode('ascii') if parser.date else ''}"
    )


def to_json(parser) -> str:
    """Преобразует данные парсера в JSON-строку.

    Работает без ujson/json модулей.

    Args:
        parser: Экземпляр парсера NMEA

    Returns:
        JSON-строка с навигационными данными
    """
    parts = [f'"valid":{str(parser.valid).lower()}', f'{_JSON_SATS}:{parser.satellites}']

    # Координаты
    if parser.has_coordinates():
        parts.append(f'{_JSON_LAT}:{parser.latitude}')
        parts.append(f'{_JSON_LONG}:{parser.longitude}')

    # 2D навигация
    if parser.has_navigation():
        parts.append(f'{_JSON_SPEED}:{parser.speed}')
        parts.append(f'{_JSON_COURSE}:{parser.course}')

    # 3D фикс
    if parser.has_3d_fix():
        parts.append(f'{_JSON_ALTITUDE}:{parser.altitude}')

    # Время и дата
    if parser.time:
        parts.append(f'{_JSON_TIME}:"{parser.time.decode("ascii")}"')
    if parser.date:
        parts.append(f'{_JSON_DATE}:"{parser.date.decode("ascii")}"')

    return '{' + ','.join(parts) + '}'


def to_compact(parser) -> str:
    """Компактный однострочный формат для логирования.

    Args:
        parser: Экземпляр парсера NMEA

    Returns:
        Однострочная строка с основными данными
    """
    if not parser.has_coordinates():
        return f"NO_FIX sat={parser.satellites}"

    coords = f"{parser.latitude:.6f},{parser.longitude:.6f}"

    parts = [f"FIX {_SATS}={parser.satellites} {coords}"]

    if parser.has_navigation():
        parts.append(f"{_SPEED}={parser.speed:.1f} {_COURSE}={parser.course:.1f}")

    if parser.has_3d_fix():
        parts.append(f"{_ALTITUDE}={parser.altitude:.1f}")

    if parser.time:
        parts.append(f"{_TIME}={parser.time.decode('ascii')}")

    return ' '.join(parts)