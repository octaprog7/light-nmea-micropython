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

# analyze_accuracy.py
import csv
import math

# постоянные
LOG_FILENAME = 'gnss_log.csv'
FIELD_LAT = 'latitude'
FIELD_LON = 'longitude'
FIELD_FIX = 'fix_mode'
FIELD_HDOP = 'hdop'
FILE_ENCODING = 'utf-8'
EMPTY_STR = ''

# Постоянные геодезии и математики
M_PER_DEG_LAT = 111_320.0
RTK_FIXED_STR = 'RTK Fixed'
MIN_POINTS_FOR_STD = 2

# Шаблоны для вывода в консоль
MSG_HEADER = 'Анализ точности GNSS.'
MSG_POINTS = 'Всего точек: {0}.'
MSG_RTK = 'RTK Fixed: {0} ({1:.1f}%).'
MSG_HDOP = 'Среднее значение HDOP: {0:.2f}.'
MSG_COORD = '{0}: {1:.6f} +/- {2:.6f} [{3:.6f} .. {4:.6f}].'
MSG_ERROR_R = 'Радиус ошибки (1 sigma): ~{0:.2f} м.'
MSG_SPAN = 'Дрейф: ~{0:.2f} м.'

MSG_ERR_NOT_ENOUGH = 'Ошибка: Нет данных для анализа!'
MSG_ERR_FILE_NOT_FOUND = "Ошибка: файл '{0}' не найден!"
MSG_ERR_ENCODING = "Ошибка: Файл '{0}' с проблемной кодировкой!"
MSG_ERR_NO_DATA = 'Ошибка: Не найдено правильных точек данных!'


def analyze_log(filename: str = LOG_FILENAME):
    """Анализ точности журнала данных GNSS."""
    n = 0
    mean_lat = 0.0
    mean_lon = 0.0
    m2_lat = 0.0
    m2_lon = 0.0

    # отслеживание min/max
    min_lat = max_lat = min_lon = max_lon = None

    # счетчики для статистики
    rtk_count = 0
    hdop_sum = 0.0
    hdop_count = 0

    # Чтение и обработка потока
    try:
        with open(filename, 'r', encoding=FILE_ENCODING) as f:
            reader = csv.DictReader(f)

            for row in reader:
                lat_str = row.get(FIELD_LAT, EMPTY_STR)
                lon_str = row.get(FIELD_LON, EMPTY_STR)

                if not lat_str or not lon_str:
                    continue

                try:
                    lat = float(lat_str)
                    lon = float(lon_str)
                except ValueError:
                    continue

                n += 1

                # Среднее значение и дисперсия
                delta_lat = lat - mean_lat
                delta_lon = lon - mean_lon
                mean_lat += delta_lat / n
                mean_lon += delta_lon / n
                delta2_lat = lat - mean_lat
                delta2_lon = lon - mean_lon
                m2_lat += delta_lat * delta2_lat
                m2_lon += delta_lon * delta2_lon

                # min/max
                if min_lat is None:
                    min_lat = max_lat = lat
                    min_lon = max_lon = lon
                else:
                    if lat < min_lat: min_lat = lat
                    if lat > max_lat: max_lat = lat
                    if lon < min_lon: min_lon = lon
                    if lon > max_lon: max_lon = lon

                # Счетчики RTK,  HDOP
                if row.get(FIELD_FIX) == RTK_FIXED_STR:
                    rtk_count += 1

                hdop_str = row.get(FIELD_HDOP, EMPTY_STR)
                if hdop_str:
                    try:
                        hdop_sum += float(hdop_str)
                        hdop_count += 1
                    except ValueError:
                        pass

    except FileNotFoundError:
        print(MSG_ERR_FILE_NOT_FOUND.format(filename))
        return
    except UnicodeDecodeError:
        print(MSG_ERR_ENCODING.format(filename))
        return

    if n < MIN_POINTS_FOR_STD:
        print(MSG_ERR_NOT_ENOUGH)
        return

    # Вычисление итоговых показателей
    var_lat = m2_lat / (n - 1)
    var_lon = m2_lon / (n - 1)
    std_lat = math.sqrt(var_lat)
    std_lon = math.sqrt(var_lon)

    lat_rad = math.radians(mean_lat)
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(lat_rad)

    err_lat_m = std_lat * M_PER_DEG_LAT
    err_lon_m = std_lon * m_per_deg_lon
    avg_err_m = (err_lat_m + err_lon_m) / 2.0

    span_lat_m = (max_lat - min_lat) * M_PER_DEG_LAT
    span_lon_m = (max_lon - min_lon) * m_per_deg_lon
    max_span_m = max(span_lat_m, span_lon_m)

    rtk_pct = 100.0 * rtk_count / n
    avg_hdop = hdop_sum / hdop_count if hdop_count > 0 else 0.0

    # Вывод в консоль
    print(MSG_HEADER)
    print(MSG_POINTS.format(n))
    print(MSG_RTK.format(rtk_count, rtk_pct))
    print(MSG_HDOP.format(avg_hdop))
    print('')
    print(MSG_COORD.format('Latitude', mean_lat, std_lat, min_lat, max_lat))
    print(MSG_COORD.format('Longitude', mean_lon, std_lon, min_lon, max_lon))
    print('')
    print(MSG_ERROR_R.format(avg_err_m))
    print(MSG_SPAN.format(max_span_m))


if __name__ == '__main__':
    analyze_log()