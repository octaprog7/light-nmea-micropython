"""Инструменты для gnss_dashboard.py"""

# Кол-во запятых в потоке данных типа CSV.
# 12 полей распарсенных MicroPython-кодом, выполняющимся на плате с RP2040, ESP32 и т. п.
_COMMA_COUNT_CSV = 11
# типы потоков данных для парсинга
DATA_STREAM_UNKNOWN = 0
DATA_STREAM_CSV = 1
DATA_STREAM_NMEA_0183 = 2

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
