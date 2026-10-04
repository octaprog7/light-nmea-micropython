#!/usr/bin/env python3
"""
Скрипт визуализации трека GNSS в формат SVG.
Создает легковесный, масштабируемый векторный файл без внешних JS-библиотек.
Зависимости: только pandas (и стандартная библиотека Python).
"""

import argparse
import math
import os
import sys
import pandas as pd

# Константы полей CSV
FIELD_DATE = "date"
FIELD_TIME = "time"
FIELD_VALID = "valid"
FIELD_LATITUDE = "latitude"
FIELD_LONGITUDE = "longitude"

# Настройки по умолчанию
DEFAULT_CSV_FILE = "gnss_log.csv"
DEFAULT_OUTPUT_SVG = "gnss_track.svg"
VALID_FIX_VALUE = 1

# Настройки SVG
SVG_WIDTH = 1000
SVG_HEIGHT = 800
PADDING = 60
TRACK_COLOR = "#2563eb"
TRACK_WIDTH = 3
START_COLOR = "#22c55e"
END_COLOR = "#ef4444"
GRID_COLOR = "#e5e7eb"
GRID_WIDTH = 1
TEXT_COLOR = "#374151"


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расчет расстояния по большому кругу в метрах."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calculate_grid_steps(center_lat: float) -> tuple[float, float]:
    """Расчет шага сетки в градусах для 1 метра."""
    WGS84_A = 6378137.0
    WGS84_B = 6356752.3142

    lat_rad = math.radians(center_lat)
    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)

    a_sq = WGS84_A ** 2
    b_sq = WGS84_B ** 2
    e_sq = (a_sq - b_sq) / a_sq
    radius_factor = 1.0 - e_sq * (sin_lat ** 2)

    meters_per_lat = (math.pi * WGS84_A * (1.0 - e_sq)) / (180.0 * (radius_factor ** 1.5))
    meters_per_lon = (math.pi * WGS84_A * cos_lat) / (180.0 * math.sqrt(radius_factor))

    return 1.0 / meters_per_lat, 1.0 / meters_per_lon


def calculate_optimal_grid_step(bbox_width_m: float, bbox_height_m: float) -> int:
    """Расчет оптимального шага сетки в метрах."""
    min_dimension = min(bbox_width_m, bbox_height_m)
    target_steps = 6
    raw_step = min_dimension / target_steps

    for step in (5, 10, 20, 50, 100, 200):
        if raw_step < step:
            return step
    return 500


def latlon_to_svg(lat: float, lon: float, min_lat: float, max_lat: float,
                  min_lon: float, max_lon: float) -> tuple[float, float]:
    """Преобразование географических координат в координаты SVG.
    Важно: ось Y в SVG направлена вниз, поэтому инвертируем широту.
    """
    # Защита от деления на ноль, если трек состоит из одной точки
    lon_range = max_lon - min_lon if max_lon != min_lon else 1e-6
    lat_range = max_lat - min_lat if max_lat != min_lat else 1e-6

    x = PADDING + ((lon - min_lon) / lon_range) * (SVG_WIDTH - 2 * PADDING)
    y = (SVG_HEIGHT - PADDING) - ((lat - min_lat) / lat_range) * (SVG_HEIGHT - 2 * PADDING)
    return x, y


def main() -> None:
    parser = argparse.ArgumentParser(description="GNSS Track to SVG Visualization")
    parser.add_argument("-i", "--input", default=DEFAULT_CSV_FILE, help="Input CSV file")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT_SVG, help="Output SVG file")
    args = parser.parse_args()

    print(f"Чтение данных из {args.input}...")
    if not os.path.exists(args.input):
        print(f"Ошибка: файл '{args.input}' не найден!")
        sys.exit(1)

    try:
        df = pd.read_csv(args.input, on_bad_lines='skip')
    except Exception as e:
        print(f"Ошибка чтения: {e}")
        sys.exit(1)

    required_columns = [FIELD_DATE, FIELD_TIME, FIELD_VALID, FIELD_LATITUDE, FIELD_LONGITUDE]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print(f"Ошибка: отсутствуют обязательные столбцы: {', '.join(missing_columns)}")
        sys.exit(1)

    # Очистка и фильтрация данных
    df[FIELD_VALID] = pd.to_numeric(df[FIELD_VALID], errors='coerce').fillna(0).astype(int)
    df[FIELD_LATITUDE] = pd.to_numeric(df[FIELD_LATITUDE], errors='coerce')
    df[FIELD_LONGITUDE] = pd.to_numeric(df[FIELD_LONGITUDE], errors='coerce')

    df_valid = df[df[FIELD_VALID] == VALID_FIX_VALUE].copy()
    df_valid = df_valid.dropna(subset=[FIELD_LATITUDE, FIELD_LONGITUDE])
    df_valid = df_valid[(df_valid[FIELD_LATITUDE] != 0) & (df_valid[FIELD_LONGITUDE] != 0)]

    if df_valid.empty:
        print("Ошибка: в файле не найдено корректных координат!")
        sys.exit(1)

    # Сортировка по времени
    df_valid['datetime'] = pd.to_datetime(
        df_valid[FIELD_DATE] + ' ' + df_valid[FIELD_TIME],
        dayfirst=True, errors='coerce'
    )
    df_valid = df_valid.sort_values('datetime').reset_index(drop=True)
    points_count = len(df_valid)
    print(f"Всего строк: {len(df)}. Найдено валидных точек: {points_count}.")

    # Расчет общей дистанции
    total_distance_m = 0.0
    for i in range(1, points_count):
        total_distance_m += haversine_distance(
            df_valid.iloc[i - 1][FIELD_LATITUDE], df_valid.iloc[i - 1][FIELD_LONGITUDE],
            df_valid.iloc[i][FIELD_LATITUDE], df_valid.iloc[i][FIELD_LONGITUDE]
        )
    total_distance_km = total_distance_m / 1000.0

    # Границы трека
    min_lat, max_lat = df_valid[FIELD_LATITUDE].min(), df_valid[FIELD_LATITUDE].max()
    min_lon, max_lon = df_valid[FIELD_LONGITUDE].min(), df_valid[FIELD_LONGITUDE].max()
    center_lat = (min_lat + max_lat) / 2.0

    print("Генерация SVG...")

    # Расчет сетки
    deg_per_m_lat, deg_per_m_lon = calculate_grid_steps(center_lat)
    bbox_height_m = (max_lat - min_lat) / deg_per_m_lat
    bbox_width_m = (max_lon - min_lon) / deg_per_m_lon
    optimal_step_m = calculate_optimal_grid_step(bbox_width_m, bbox_height_m)
    step_lat = optimal_step_m * deg_per_m_lat
    step_lon = optimal_step_m * deg_per_m_lon

    start_lat_grid = math.floor(min_lat / step_lat) * step_lat
    end_lat_grid = math.ceil(max_lat / step_lat) * step_lat
    start_lon_grid = math.floor(min_lon / step_lon) * step_lon
    end_lon_grid = math.ceil(max_lon / step_lon) * step_lon

    # Формирование содержимого SVG
    svg_elements = [
        # Заголовок SVG
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}" width="100%" height="100%">',
        # Белый фон
        f'  <rect width="{SVG_WIDTH}" height="{SVG_HEIGHT}" fill="#ffffff"/>', '  <g id="grid">']

    # Сетка
    current_lat = start_lat_grid
    while current_lat <= end_lat_grid:
        x1, y1 = latlon_to_svg(current_lat, min_lon, min_lat, max_lat, min_lon, max_lon)
        x2, y2 = latlon_to_svg(current_lat, max_lon, min_lat, max_lat, min_lon, max_lon)
        svg_elements.append(
            f'    <line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{GRID_COLOR}" stroke-width="{GRID_WIDTH}"/>')
        # Подпись сетки
        svg_elements.append(
            f'    <text x="{x1 - 5}" y="{y1 + 4}" font-family="monospace" font-size="10" fill="{TEXT_COLOR}" text-anchor="end">{int(optimal_step_m)}m</text>')
        current_lat += step_lat

    current_lon = start_lon_grid
    while current_lon <= end_lon_grid:
        x1, y1 = latlon_to_svg(min_lat, current_lon, min_lat, max_lat, min_lon, max_lon)
        x2, y2 = latlon_to_svg(max_lat, current_lon, min_lat, max_lat, min_lon, max_lon)
        svg_elements.append(
            f'    <line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{GRID_COLOR}" stroke-width="{GRID_WIDTH}"/>')
        current_lon += step_lon
    svg_elements.append('  </g>')

    # Линия (Polyline)
    points_str = " ".join([
        f"{latlon_to_svg(row[FIELD_LATITUDE], row[FIELD_LONGITUDE], min_lat, max_lat, min_lon, max_lon)[0]:.2f},"
        f"{latlon_to_svg(row[FIELD_LATITUDE], row[FIELD_LONGITUDE], min_lat, max_lat, min_lon, max_lon)[1]:.2f}"
        for _, row in df_valid.iterrows()
    ])
    svg_elements.append(
        f'  <polyline points="{points_str}" fill="none" stroke="{TRACK_COLOR}" stroke-width="{TRACK_WIDTH}" stroke-linejoin="round" stroke-linecap="round"/>')

    # Маркеры:
    start_row = df_valid.iloc[0]
    end_row = df_valid.iloc[-1]

    sx, sy = latlon_to_svg(start_row[FIELD_LATITUDE], start_row[FIELD_LONGITUDE], min_lat, max_lat, min_lon, max_lon)
    ex, ey = latlon_to_svg(end_row[FIELD_LATITUDE], end_row[FIELD_LONGITUDE], min_lat, max_lat, min_lon, max_lon)
    radius = 8

    # Маркер старта
    svg_elements.append(
        f'  <circle cx="{sx:.2f}" cy="{sy:.2f}" r="{radius}" fill="{START_COLOR}" stroke="#ffffff" stroke-width="2"/>')
    svg_elements.append(
        f'  <text x="{sx:.2f}" y="{sy:.2f}" font-family="sans-serif" font-size="10" font-weight="bold" fill="#ffffff" text-anchor="middle" dominant-baseline="central">S</text>')

    # Маркер финиша
    svg_elements.append(
        f'  <circle cx="{ex:.2f}" cy="{ey:.2f}" r="{radius}" fill="{END_COLOR}" stroke="#ffffff" stroke-width="2"/>')
    svg_elements.append(
        f'  <text x="{ex:.2f}" y="{ey:.2f}" font-family="sans-serif" font-size="10" font-weight="bold" fill="#ffffff" text-anchor="middle" dominant-baseline="central">E</text>')

    # Информация - легенда
    legend_x, legend_y = PADDING, PADDING - 15
    svg_elements.append(
        f'  <rect x="{legend_x}" y="{legend_y}" width="280" height="30" fill="rgba(255,255,255,0.9)" stroke="#cccccc" rx="4"/>')
    svg_elements.append(
        f'  <text x="{legend_x + 10}" y="{legend_y + 20}" font-family="monospace" font-size="14" font-weight="bold" fill="{TEXT_COLOR}">')
    svg_elements.append(f'    Points: {points_count} | Dist: {total_distance_km:.2f} km | Grid: {optimal_step_m} m')
    svg_elements.append(f'  </text>')

    # Закрываю область SVG
    svg_elements.append('</svg>')

    # Пишу в файл
    svg_content = "\n".join(svg_elements)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(svg_content)

    print(f"Успешно! SVG сохранен в: {os.path.realpath(args.output)}")


if __name__ == "__main__":
    main()