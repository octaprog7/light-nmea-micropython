# Copyright 2026 Roman Shevchik. See LICENSE for details.

# Импортирую ядро парсера и ВСЕ его публичные постоянные
from .nmea0183_parser import (
    LightNMEA,
    # Маски созвездий для фильтрации
    CST_MASK_ALL,
    CST_MASK_GPS,
    CST_MASK_GLONASS,
    CST_MASK_GALILEO,
    CST_MASK_BEIDOU,
    CST_MASK_QZSS,
    CST_MASK_NAVIC,
    # Идентификаторы созвездий (Talker ID)
    CST_UNKNOWN,
    CST_GPS,
    CST_GLONASS,
    CST_GALILEO,
    CST_BEIDOU,
    CST_QZSS,
    CST_NAVIC,
    CST_MULTI,
    # Статусы качества фикса (Fix Quality)
    FIX_NOT_VALID,
    FIX_AUTONOMOUS,
    FIX_DGPS,
    FIX_RTK_FIXED,
    FIX_RTK_FLOAT,
    FIX_ESTIMATED,
    # Константы режимов сброса состояния (RESET)
    RESET_ALL,
    RESET_GGA,
    RESET_RMC
)

# Импортирую стрим-ридер с правильным именем класса
from .nmea0183_stream import NMEAStreamReader

# Импортирую функции конвертации
from .conv_to_hrf import to_format

# Публичный API пакета через __all__
__all__ = [
    # Основные классы и функции
    'LightNMEA',
    'NMEAStreamReader',
    'to_format',

    # Константы созвездий
    'CST_UNKNOWN', 'CST_GPS', 'CST_GLONASS', 'CST_GALILEO',
    'CST_BEIDOU', 'CST_QZSS', 'CST_NAVIC', 'CST_MULTI',

    # Маски для фильтра
    'CST_MASK_ALL', 'CST_MASK_GPS', 'CST_MASK_GLONASS',
    'CST_MASK_GALILEO', 'CST_MASK_BEIDOU', 'CST_MASK_QZSS', 'CST_MASK_NAVIC',

    # Статусы навигации
    'FIX_NOT_VALID', 'FIX_AUTONOMOUS', 'FIX_DGPS',
    'FIX_RTK_FIXED', 'FIX_RTK_FLOAT', 'FIX_ESTIMATED',

    # Режимы сброса
    'RESET_ALL', 'RESET_GGA', 'RESET_RMC'
]
