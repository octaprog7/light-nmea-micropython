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


try:
    from micropython import native
except ImportError:
    def native(func): return func


FMT_TXT = 0
FMT_CSV = 1
FMT_JSON = 2
FMT_COMPACT = 3

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

_CST_NAMES = ("GPS", "SBAS", "GLONASS", "BeiDou", "QZSS", "Galileo", "NavIC", "Multi-GNSS")
_FIX_NAMES = ("No Fix", "2D", "3D", "RTK Fixed", "RTK Float", "DR", "GNSS+DR")


# === Вспомогательные функции форматирования ===
@native
def _fmt_dt(value, is_time: bool = True) -> str:
    """Форматирует время или дату из NMEA в человекочитаемый вид.

    Args:
        value: bytes или str с временем (HHMMSS.SS) или датой (DDMMYY)
        is_time: True для времени, False для даты

    Returns:
        Отформатированная строка:
        - Время: HH:MM:SS.SS
        - Дата: DD.MM.YYYY
    """
    if not value:
        return ""

    val = value
    # Преобразую bytes/bytearray в str
    if isinstance(value, (bytes, bytearray)):
        val = value.decode('ascii')

    six = 6
    if is_time:
        # Форматирование времени: HHMMSS.SS -> HH:MM:SS.SS
        if len(val) < six:
            return val
        return f"{val[0:2]}:{val[2:4]}:{val[4:]}"

    # Форматирование даты: DDMMYY -> DD.MM.YYYY
    if len(val) != six:
        return val
    return f"{val[0:2]}.{val[2:4]}.20{val[4:six]}"


def _to_txt(parser) -> str:
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
        lines.append(f"{_TIME}: {_fmt_dt(parser.time)} UTC")
    if parser.date:
        lines.append(f"{_DATE}: {_fmt_dt(value=parser.date, is_time=False)}")

    return '\n'.join(lines)


def _to_csv(parser) -> str:
    """Преобразует данные парсера в CSV-строку.
    Формат: valid,sat,lat,lon,speed,course,alt,time,date,constellation,fix_mode,hdop"""
    # Безопасное получение имени созвездия
    cst = parser.constellation
    cst_name = _CST_NAMES[cst] if cst < len(_CST_NAMES) else f"U{cst}"

    # Безопасное получение имени режима фикса
    fm = parser.fix_mode
    fix_name = _FIX_NAMES[fm] if fm < len(_FIX_NAMES) else f"U{fm}"

    return (
        f"{int(parser.valid)},"
        f"{parser.satellites},"
        f"{parser.latitude if parser.latitude is not None else ''},"
        f"{parser.longitude if parser.longitude is not None else ''},"
        f"{parser.speed if parser.speed is not None else ''},"
        f"{parser.course if parser.course is not None else ''},"
        f"{parser.altitude if parser.altitude is not None else ''},"
        f"{_fmt_dt(parser.time) if parser.time else ''},"
        f"{_fmt_dt(value=parser.date, is_time=False) if parser.date else ''},"
        f"{cst_name},"
        f"{fix_name},"
        f"{parser.hdop if parser.hdop is not None else ''}"
    )


def _to_json(parser) -> str:
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
        parts.append(f'{_JSON_TIME}:"{_fmt_dt(parser.time)}"')
    if parser.date:
        parts.append(f'{_JSON_DATE}:"{_fmt_dt(value=parser.date, is_time=False)}"')

    return '{' + ','.join(parts) + '}'


def _to_compact(parser) -> str:
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
        parts.append(f"{_TIME}={_fmt_dt(parser.time)}")

    if parser.date:
        parts.append(f"{_DATE}={_fmt_dt(parser.date, is_time=False)}")

    return ' '.join(parts)


_FMT_FUNC = _to_txt, _to_csv, _to_json, _to_compact

@native
def to_format(parser, id_format: int = FMT_TXT) -> str:
    return _FMT_FUNC[id_format](parser)