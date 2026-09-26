"""Инструменты для gnss_dashboard.py"""

from time import monotonic
from datetime import datetime
from typing import Optional, IO

# Кол-во запятых в потоке данных типа CSV.
# 12 полей распарсенных MicroPython-кодом, выполняющимся на плате с RP2040, ESP32 и т. п.
_COMMA_COUNT_CSV = 11
_PLACE_HOLDER = "---"
_TO_KM_H = 1.0
# типы потоков данных для парсинга
DATA_STREAM_UNKNOWN = 0
DATA_STREAM_CSV = 1
DATA_STREAM_NMEA_0183 = 2


def now() -> float:
    """Возвращает текущее время в секундах (monotonic)."""
    return monotonic()


def log_msg(message: str, destination: IO[str]) -> None:
    """Выводит сообщение в destination с временной меткой в формате журнала."""
    timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    print(f"[{timestamp}] {message}", file=destination)


def get_port_type(port: str) -> str:
    """Определяет тип порта по имени устройства."""
    return "USB-UART" if "ttyACM" in port or "ttyUSB" in port else "Serial"


def format_speed(speed: Optional[float]) -> str:
    """Форматирует скорость в км/ч."""
    if speed is None:
        return f"{_PLACE_HOLDER} km/h"
    return f"{speed * _TO_KM_H:.1f} km/h"


def detect_format(line: str, nmea_sentences: tuple = ('RMC', 'GGA', 'VTG', 'GLL')) -> int:
    """
    Определяет тип поступающего потока:
    Возвращает:
        0 — неизвестный тип потока,
        1 — CSV поток,
        2 — NMEA-0183 поток.
    nmea_sentences: кортеж имен поддерживаемых типов сентенций.
    """
    if not line:
        return DATA_STREAM_UNKNOWN

    # NMEA: $XXYYY,...
    if line[0] == '$' and len(line) >= 7:
        if line[3:6] in nmea_sentences:
            return DATA_STREAM_NMEA_0183

    # CSV: ровно 11 запятых (с префиксом [HH:MM:SS] или без)
    if line[0] != '$' and line.count(',') == _COMMA_COUNT_CSV:
        return DATA_STREAM_CSV

    return DATA_STREAM_UNKNOWN


def format_nmea_datetime(value: bytes | bytearray, is_time: bool = True) -> str:
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