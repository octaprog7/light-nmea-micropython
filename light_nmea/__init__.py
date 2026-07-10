# Copyright 2026 Roman Shevchik. See LICENSE for details.
"""LightNMEA - Fast NMEA-0183 parser.
Usage:
    from light_nmea.nmea0183_parser import LightNMEA
    from light_nmea.nmea0183_stream import NMEAStreamReader
    from light_nmea.conv_to_hrf import to_format
"""
__version__ = "2.0.0"
__author__ = "Roman Shevchik"
__license__ = "GPL-3.0"

# Экспорт компонент для удобного доступа
from light_nmea.nmea0183_parser import LightNMEA
from light_nmea.nmea0183_stream import NMEAStreamReader
from light_nmea.conv_to_hrf import to_format