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
"""Содержит функцию возврата навигационной информации в формате NMEA-183"""
from random import randrange

_NAV_PACKS = (
    #  1. Мюнхен RMC
    b"$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n",
    #  2. Мюнхен GGA
    b"$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n",
    #  3. Москва RMC
    b"$GNRMC,091530,A,5545.1234,N,03737.5678,E,015.0,120.5,220626,,,A*69\r\n",
    #  4. Москва GGA
    b"$GNGGA,091530.00,5545.1234,N,03737.5678,E,1,12,0.8,156.3,M,14.2,M,,*78\r\n",
    #  5. Сидней RMC
    b"$GNRMC,235959,A,3351.5432,S,15112.3456,E,045.7,270.0,311225,,,A*71\r\n",
    #  6. Сидней GGA
    b"$GNGGA,235959.99,3351.5432,S,15112.3456,E,2,10,1.1,58.0,M,0.0,M,,*67\r\n",
    #  7. Нью-Йорк RMC
    b"$GPRMC,180000,A,4042.8345,N,07400.2456,W,008.2,045.0,150725,,,A*6A\r\n",
    #  8. Нью-Йорк GGA
    b"$GPGGA,180000.50,4042.8345,N,07400.2456,W,1,09,1.0,10.5,M,-34.0,M,,*6A\r\n",
    #  9. Экватор RMC
    b"$GNRMC,000000,A,0000.0000,N,00000.0000,E,000.0,000.0,010126,,,A*6A\r\n",
    # 10. БИТЫЙ (статус V)
    b"$GNRMC,120000,V,4807.038,N,01131.000,E,000.0,000.0,220626,,,N*75\r\n",
    # 11. RTK Fixed (quality=4) - CRC уже правильный
    b"$GNGGA,120000.00,5545.1234,N,03737.5678,E,4,15,0.5,156.3,M,14.2,M,,*7A\r\n",
    # 12. RTK Float (quality=5) - ИСПРАВЛЕНО: *7B -> *7E
    b"$GNGGA,120000.00,5545.1234,N,03737.5678,E,5,12,0.7,156.3,M,14.2,M,,*7E\r\n",
    # 13. Нет фикса (quality=0) - ИСПРАВЛЕНО: *56 -> *7B
    b"$GNGGA,120000.00,,,,,0,00,99.99,,,,,,*7B\r\n",
    # 14. Очень высокий HDOP (плохая точность) - ИСПРАВЛЕНО: *4A -> *71
    b"$GPGGA,123519,4807.038,N,01131.000,E,1,03,15.0,545.4,M,46.9,M,,*71\r\n",
    # 15. Максимальная длина пакета (GSV с 12 спутниками) - ИСПРАВЛЕНО: *7A -> *7F
    b"$GPGSV,1,1,12,01,45,090,45,02,30,180,40,03,20,270,35,04,10,360,30*7F\r\n",
    # 16. BeiDou (новый формат BD)
    b"$BDRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*7B\r\n",
    # 17. QZSS (новый формат QZ)
    b"$QZRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*76\r\n",
    # 18. NavIC (новый формат IR)
    b"$IRRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*66\r\n",
    # 19. VTG - курс и скорость (Мюнхен)
    b"$GPVTG,084.4,T,081.3,M,022.4,N,041.5,K,A*25\r\n",
    # 20. VTG - высокая скорость (Москва)
    b"$GNVTG,120.5,T,117.4,M,015.0,N,027.8,K,A*31\r\n",
    # 21. VTG - без Mode Indicator (старый формат)
    b"$GPVTG,270.0,T,267.0,M,045.7,N,084.6,K*44\r\n",
    # 22. GLL - координаты (Мюнхен)
    b"$GPGLL,4807.038,N,01131.000,E,123519,A,A*48\r\n",
    # 23. GLL - координаты (Москва)
    b"$GNGLL,5545.1234,N,03737.5678,E,091530,A,A*5E\r\n",
    # 24. GLL - южное полушарие (Сидней)
    b"$GNGLL,3351.5432,S,15112.3456,E,235959,A,A*43\r\n",
)

def get_nav_packet() -> bytes:
    """Возвращает случайный пакет навигационных данных."""
    idx = randrange(len(_NAV_PACKS))
    return _NAV_PACKS[idx]