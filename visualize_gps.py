#!/usr/bin/env python3
"""Скрипт визуализации GPS-треков для LightNMEA.
Генерирует интерактивную HTML-карту из CSV-файла журнала.
Зависимости: pandas, folium"""

import os
import sys
import folium
import pandas as pd

# Имена полей CSV-файла
FIELD_DATE = "date"
FIELD_TIME = "time"
FIELD_VALID = "valid"
FIELD_LATITUDE = "latitude"
FIELD_LONGITUDE = "longitude"
FIELD_SPEED = "speed_kmh"
FIELD_COURSE = "course_deg"
FIELD_ALTITUDE = "altitude_m"
FIELD_SATELLITES = "satellites"
FIELD_CONSTELLATION = "constellation"
FIELD_FIX_MODE = "fix_mode"
FIELD_HDOP = "hdop"

# имя CSV-файла c GNSS данными по умолчанию
CSV_FILE = "gnss_log.csv"
OUTPUT_HTML = "gps_track.html"
VALID_FIX_VALUE = 1
MIN_ZOOM_LEVEL = 15


def main():
    print(f"Чтение GNSS данных из {CSV_FILE}...")

    if not os.path.exists(CSV_FILE):
        print(f"Ошибка: файл {CSV_FILE} не найден!")
        print("Пожалуйста, запустите этот скрипт в папке, содержащей log файл!")
        sys.exit(1)

    df = None
    try:
        df = pd.read_csv(CSV_FILE)
    except Exception as e:
        print(f"Ошибка чтения: {e}")
        sys.exit(1)

    # Проверка наличия нужных столбцов в CSV-файле
    required_columns = [FIELD_DATE, FIELD_TIME, FIELD_VALID, FIELD_LATITUDE, FIELD_LONGITUDE]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print(f"Ошибка: отсутствуют столбцы: {', '.join(missing_columns)}")
        sys.exit(1)

    # столбец 'valid' в целое число (обработка возможных значений NaN или не-числовых значений)
    df[FIELD_VALID] = pd.to_numeric(df[FIELD_VALID], errors='coerce').fillna(0).astype(int)
    # фильтрую только допустимые точки
    df_valid = df[df[FIELD_VALID] == VALID_FIX_VALUE].copy()
    # Удаляю строки с неверными координатами
    df_valid = df_valid.dropna(subset=[FIELD_LATITUDE, FIELD_LONGITUDE])
    # фильтрую координаты (0, 0) (GPS без фикса)
    df_valid = df_valid[
        (df_valid[FIELD_LATITUDE] != 0) &
        (df_valid[FIELD_LONGITUDE] != 0)
        ]

    if df_valid.empty:
        print("Ошибка: в файле не найдены допустимые координаты!")
        sys.exit(1)

    # Сортировка по дате и времени для обеспечения правильного порядка
    df_valid = df_valid.sort_values([FIELD_DATE, FIELD_TIME]).reset_index(drop=True)
    print(f"Из общего числа {len(df)} найдено {len(df_valid)} правильных точек.")
    # Вычисление центра карты
    center_lat = float(df_valid[FIELD_LATITUDE].mean())
    center_lon = float(df_valid[FIELD_LONGITUDE].mean())
    print("Создание карты...")
    # Создание обьекта карты (OpenStreetMap layer)
    gps_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=MIN_ZOOM_LEVEL,
        tiles="CartoDB positron"
    )

    # Подготовка координат для траектории
    track_coords = df_valid[[FIELD_LATITUDE, FIELD_LONGITUDE]].values.tolist()
    # Добавление линии трека
    folium.PolyLine(
        locations=track_coords,
        color="blue",
        weight=4,
        opacity=0.8,
        tooltip="GPS Track"
    ).add_to(gps_map)

    # Добавление начального маркера (зеленый)
    start_point = track_coords[0]
    start_time = "{} {}".format(
        df_valid.iloc[0][FIELD_DATE],
        df_valid.iloc[0][FIELD_TIME]
    )
    folium.Marker(
        location=start_point,
        popup="Start<br>Time: {}".format(start_time),
        icon=folium.Icon(color="green", icon="play-circle", prefix="fa")
    ).add_to(gps_map)

    # Добавление конечного маркера (красный)
    end_point = track_coords[-1]
    end_time = "{} {}".format(
        df_valid.iloc[-1][FIELD_DATE],
        df_valid.iloc[-1][FIELD_TIME]
    )
    folium.Marker(
        location=end_point,
        popup="End<br>Time: {}".format(end_time),
        icon=folium.Icon(color="red", icon="stop-circle", prefix="fa")
    ).add_to(gps_map)

    # сохраняю файл карты
    gps_map.save(OUTPUT_HTML)
    print(f"Все в порядке! Карта сохранена в: {OUTPUT_HTML}")
    print("Откройте этот файл в браузере..")


if __name__ == "__main__":
    main()