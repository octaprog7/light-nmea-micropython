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

# соответствует константам CST_* в nmea0183_parser.py
_CST_NAMES = ("Unknown", "GPS", "GLONASS", "Galileo", "BeiDou", "QZSS", "NavIC", "Multi-GNSS")
# соответствует константам FIX_* в nmea0183_parser.py
_FIX_NAMES = ("Autonomous", "DGPS", "Estimated", "Not Valid", "RTK Fixed", "RTK Float")


# === Вспомогательные функции форматирования ===
@native
def _fmt_dt(value, is_time: bool = True) -> str:
    """Форматирует время или дату из NMEA в человекочитаемый вид."""
    if not value:
        return ""

    val = value
    if isinstance(value, (bytes, bytearray)):
        val = value.decode('ascii')

    six = 6
    if is_time:
        if len(val) < six:
            return val
        return f"{val[0:2]}:{val[2:4]}:{val[4:]}"

    if len(val) != six:
        return val
    return f"{val[0:2]}.{val[2:4]}.20{val[4:six]}"


def _to_txt(parser) -> str:
    """Преобразует данные парсера в человекочитаемый формат."""
    valid_str = 'Yes' if parser.valid else 'No'
    sat_str = str(parser.satellites) if parser.satellites is not None else '0'
    lines = [f"Fix: {valid_str}", f"{_SATS}: {sat_str}"]

    if parser.has_coordinates():
        lines.append(f"{_LAT}: {parser.latitude:.6f}°")
        lines.append(f"{_LONG}: {parser.longitude:.6f}°")

    if parser.has_navigation():
        lines.append(f"{_SPEED}: {parser.speed:.1f} km/h")
        lines.append(f"{_COURSE}: {parser.course:.1f}°")

    if parser.has_3d_fix():
        lines.append(f"{_ALTITUDE}: {parser.altitude:.1f} m")

    if parser.time:
        lines.append(f"{_TIME}: {_fmt_dt(parser.time)} UTC")
    if parser.date:
        lines.append(f"{_DATE}: {_fmt_dt(value=parser.date, is_time=False)}")

    return '\n'.join(lines)


def _to_csv(parser) -> str:
    """Преобразует данные парсера в CSV-строку."""
    # получаю имя созвездия
    cst = parser.constellation
    if cst is None:
        cst_name = 'Unknown'
    elif cst < len(_CST_NAMES):
        cst_name = str(_CST_NAMES[cst])
    else:
        cst_name = f"U{cst}"

    # получаю имя режима фикса
    fm = parser.fix_mode
    if fm is None:
        fix_name = 'Unknown'
    elif fm < len(_FIX_NAMES):
        fix_name = str(_FIX_NAMES[fm])
    else:
        fix_name = f"U{fm}"

    # Привожу к строкам с защитой от None
    valid = str(int(parser.valid)) if parser.valid is not None else '0'
    sat = str(parser.satellites) if parser.satellites is not None else '0'

    lat = str(parser.latitude) if parser.latitude is not None else ''
    lon = str(parser.longitude) if parser.longitude is not None else ''
    spd = str(parser.speed) if parser.speed is not None else ''
    crs = str(parser.course) if parser.course is not None else ''
    alt = str(parser.altitude) if parser.altitude is not None else ''
    hdop = str(parser.hdop) if parser.hdop is not None else ''

    time_str = str(_fmt_dt(parser.time)) if parser.time else ''
    date_str = str(_fmt_dt(parser.date, is_time=False)) if parser.date else ''

    return ",".join([
        valid, sat, lat, lon, spd, crs, alt,
        time_str, date_str, cst_name, fix_name, hdop
    ])


def _to_json(parser) -> str:
    """Преобразует данные парсера в JSON-строку."""
    valid_str = 'true' if parser.valid else 'false'
    sat_str = str(parser.satellites) if parser.satellites is not None else '0'
    parts = [f'"valid":{valid_str}', f'{_JSON_SATS}:{sat_str}']

    if parser.has_coordinates():
        lat_str = str(parser.latitude) if parser.latitude is not None else '0'
        lon_str = str(parser.longitude) if parser.longitude is not None else '0'
        parts.append(f'{_JSON_LAT}:{lat_str}')
        parts.append(f'{_JSON_LONG}:{lon_str}')

    if parser.has_navigation():
        spd_str = str(parser.speed) if parser.speed is not None else '0'
        crs_str = str(parser.course) if parser.course is not None else '0'
        parts.append(f'{_JSON_SPEED}:{spd_str}')
        parts.append(f'{_JSON_COURSE}:{crs_str}')

    if parser.has_3d_fix():
        alt_str = str(parser.altitude) if parser.altitude is not None else '0'
        parts.append(f'{_JSON_ALTITUDE}:{alt_str}')

    if parser.time:
        parts.append(f'{_JSON_TIME}:"{_fmt_dt(parser.time)}"')
    if parser.date:
        parts.append(f'{_JSON_DATE}:"{_fmt_dt(value=parser.date, is_time=False)}"')

    return '{' + ','.join(parts) + '}'


def _to_compact(parser) -> str:
    """Компактный однострочный формат для логирования."""
    sat_str = str(parser.satellites) if parser.satellites is not None else '0'

    if not parser.has_coordinates():
        return f"NO_FIX sat={sat_str}"

    coords = f"{parser.latitude:.6f},{parser.longitude:.6f}"
    parts = [f"FIX {_SATS}={sat_str} {coords}"]

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