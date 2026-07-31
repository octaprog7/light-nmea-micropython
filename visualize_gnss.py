#!/usr/bin/env python3
"""
GNSS Track Visualization Script for LightNMEA.
Generates an interactive HTML map from a CSV log file with an adaptive metric grid.
Dependencies: pandas, folium, argparse
"""

import argparse
import math
import os
import sys
import webbrowser
import folium
import pandas as pd

# CSV file field names constants
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

# Default configuration constants
DEFAULT_CSV_FILE = "gnss_log.csv"
DEFAULT_OUTPUT_HTML = "gnss_track.html"
VALID_FIX_VALUE = 1

# Map styling constants
MAP_TILES_URL = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
MAP_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
GRID_LINE_COLOR = "#d1d5db"
GRID_LINE_WEIGHT = 1
GRID_LINE_OPACITY = 0.5
TRACK_LINE_COLOR = "#2563eb"
TRACK_LINE_WEIGHT = 4
TRACK_LINE_OPACITY = 0.85

# WGS-84 Ellipsoid constants
WGS84_A = 6378137.0
WGS84_B = 6356752.3142


def calculate_grid_steps(center_lat):
    """Calculates latitude and longitude step increments in degrees for 1 meter."""
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


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates the great-circle distance between two points in meters."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calculate_optimal_grid_step(bbox_width_m, bbox_height_m):
    """Calculates optimal grid step based on bounding box size."""
    min_dimension = min(bbox_width_m, bbox_height_m)
    target_steps = 6  # Aim for ~6 grid lines across the smallest dimension

    raw_step = min_dimension / target_steps

    # Round to "nice" numbers
    if raw_step < 10:
        return 5
    elif raw_step < 20:
        return 10
    elif raw_step < 50:
        return 20
    elif raw_step < 100:
        return 50
    elif raw_step < 200:
        return 100
    elif raw_step < 500:
        return 200
    else:
        return 500


def draw_grid_line(gnss_map, start_point, end_point):
    """Draws a single grid line on the map."""
    folium.PolyLine(
        locations=[start_point, end_point],
        color=GRID_LINE_COLOR,
        weight=GRID_LINE_WEIGHT,
        opacity=GRID_LINE_OPACITY
    ).add_to(gnss_map)


def generate_adaptive_grid(gnss_map, min_lat, max_lat, min_lon, max_lon):
    """Generates an adaptive grid with optimal step size."""
    center_lat = (min_lat + max_lat) / 2
    deg_per_m_lat, deg_per_m_lon = calculate_grid_steps(center_lat)

    # Calculate bounding box size in meters
    bbox_height_m = (max_lat - min_lat) / deg_per_m_lat
    bbox_width_m = (max_lon - min_lon) / deg_per_m_lon

    # Get optimal step in meters, then convert back to degrees
    optimal_step_m = calculate_optimal_grid_step(bbox_width_m, bbox_height_m)
    step_lat = optimal_step_m * deg_per_m_lat
    step_lon = optimal_step_m * deg_per_m_lon

    # Align grid to clean multiples
    start_lat = math.floor(min_lat / step_lat) * step_lat
    end_lat = math.ceil(max_lat / step_lat) * step_lat
    start_lon = math.floor(min_lon / step_lon) * step_lon
    end_lon = math.ceil(max_lon / step_lon) * step_lon

    # Draw horizontal lines
    current_lat = start_lat
    while current_lat <= end_lat:
        draw_grid_line(gnss_map, [current_lat, start_lon], [current_lat, end_lon])
        current_lat += step_lat

    # Draw vertical lines
    current_lon = start_lon
    while current_lon <= end_lon:
        draw_grid_line(gnss_map, [start_lat, current_lon], [end_lat, current_lon])
        current_lon += step_lon

    print(f"  Grid generated: step={optimal_step_m}m")


def get_marker_timestamp(df, index):
    """Formats and returns a timestamp string from a specific row index."""
    return f"{df.iloc[index][FIELD_DATE]} {df.iloc[index][FIELD_TIME]}"


def add_top_center_header(gnss_map, points_count, total_distance_km, grid_step, no_bg=False,
                          bg_color="rgba(255, 255, 255, 0.95)"):
    """Adds a fixed, styled top-center HTML header card with map metadata."""

    # Conditional styling based on arguments
    if no_bg:
        bg_style = "background-color: transparent; border: none; box-shadow: none;"
    else:
        bg_style = f"background-color: {bg_color}; border: 2px solid #999999; border-radius: 6px; box-shadow: 0px 2px 5px rgba(0,0,0,0.2);"

    # Font size increased from 14px to 28px (2x), padding adjusted proportionally
    header_html = f"""
    <div style="
        position: fixed; 
        top: 20px; 
        left: 50%; 
        transform: translateX(-50%);
        {bg_style}
        font-family: 'Courier New', Courier, monospace;
        font-weight: bold;
        font-size: 28px;
        color: #333333;
        padding: 16px 32px; 
        z-index: 9999;
        text-align: center;
        white-space: nowrap;
    ">
        Points: {points_count} | Distance: {total_distance_km:.2f} km | Grid: {grid_step} m
    </div>
    """
    gnss_map.get_root().html.add_child(folium.Element(header_html))


def main():
    # 1. Setup command-line argument parsing
    parser = argparse.ArgumentParser(description="GNSS Track Visualization Script")
    parser.add_argument("-i", "--input", default=DEFAULT_CSV_FILE, help=f"Input CSV file (default: {DEFAULT_CSV_FILE})")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT_HTML,
                        help=f"Output HTML file (default: {DEFAULT_OUTPUT_HTML})")
    parser.add_argument("--no-header-bg", action="store_true", help="Remove header background, border, and shadow")
    parser.add_argument("--header-bg", default="rgba(255, 255, 255, 0.95)",
                        help="Header background color (default: rgba(255, 255, 255, 0.95))")

    args = parser.parse_args()

    print(f"Reading GNSS data from {args.input}...")

    if not os.path.exists(args.input):
        print(f"Error: file '{args.input}' not found!")
        print("Please run this script in the directory containing the log file, or specify path with -i.")
        sys.exit(1)

    try:
        df = pd.read_csv(args.input, on_bad_lines='skip')
    except Exception as e:
        print(f"Read error: {e}")
        sys.exit(1)

    required_columns = [FIELD_DATE, FIELD_TIME, FIELD_VALID, FIELD_LATITUDE, FIELD_LONGITUDE]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print(f"Error: missing required columns: {', '.join(missing_columns)}")
        sys.exit(1)

    # Clean and convert data
    df[FIELD_VALID] = pd.to_numeric(df[FIELD_VALID], errors='coerce').fillna(0).astype(int)
    df[FIELD_LATITUDE] = pd.to_numeric(df[FIELD_LATITUDE], errors='coerce')
    df[FIELD_LONGITUDE] = pd.to_numeric(df[FIELD_LONGITUDE], errors='coerce')

    # Filter valid fixes
    df_valid = df[df[FIELD_VALID] == VALID_FIX_VALUE].copy()
    df_valid = df_valid.dropna(subset=[FIELD_LATITUDE, FIELD_LONGITUDE])
    df_valid = df_valid[(df_valid[FIELD_LATITUDE] != 0) & (df_valid[FIELD_LONGITUDE] != 0)]

    if df_valid.empty:
        print("Error: no valid coordinates found in the log file!")
        sys.exit(1)

    # Safe chronological sorting
    df_valid['datetime'] = pd.to_datetime(
        df_valid[FIELD_DATE] + ' ' + df_valid[FIELD_TIME],
        dayfirst=True,
        errors='coerce'
    )
    df_valid = df_valid.sort_values('datetime').reset_index(drop=True)

    points_count = len(df_valid)
    print(f"Total rows parsed: {len(df)}. Found {points_count} valid data points.")

    # Calculate total track distance
    total_distance_m = 0.0
    for i in range(1, points_count):
        total_distance_m += haversine_distance(
            df_valid.iloc[i - 1][FIELD_LATITUDE], df_valid.iloc[i - 1][FIELD_LONGITUDE],
            df_valid.iloc[i][FIELD_LATITUDE], df_valid.iloc[i][FIELD_LONGITUDE]
        )
    total_distance_km = 0.001 * total_distance_m

    # Calculate bounding box
    min_lat = df_valid[FIELD_LATITUDE].min()
    max_lat = df_valid[FIELD_LATITUDE].max()
    min_lon = df_valid[FIELD_LONGITUDE].min()
    max_lon = df_valid[FIELD_LONGITUDE].max()
    center_lat = 0.5 * (min_lat + max_lat)
    center_lon = 0.5 * (min_lon + max_lon)

    print("Generating map layers...")
    gnss_map = folium.Map(
        location=[center_lat, center_lon],
        tiles=MAP_TILES_URL,
        attr=MAP_ATTRIBUTION,
        zoom_start=15
    )

    # 1. Adaptive grid
    generate_adaptive_grid(gnss_map, min_lat, max_lat, min_lon, max_lon)

    # 2. Track line
    track_coords = df_valid[[FIELD_LATITUDE, FIELD_LONGITUDE]].values.tolist()
    folium.PolyLine(
        locations=track_coords,
        color=TRACK_LINE_COLOR,
        weight=TRACK_LINE_WEIGHT,
        opacity=TRACK_LINE_OPACITY,
        tooltip=f"GNSS Track ({total_distance_km:.2f} km)"
    ).add_to(gnss_map)

    # 3. Start and End markers
    folium.Marker(
        location=track_coords[0],
        popup=f"<b>START</b><br>Time: {get_marker_timestamp(df_valid, 0)}",
        icon=folium.Icon(color="green", icon="play-circle", prefix="fa")
    ).add_to(gnss_map)

    folium.Marker(
        location=track_coords[-1],
        popup=f"<b>END</b><br>Time: {get_marker_timestamp(df_valid, -1)}",
        icon=folium.Icon(color="red", icon="stop-circle", prefix="fa")
    ).add_to(gnss_map)

    # Determine the actual grid step used for the header
    optimal_step_m = calculate_optimal_grid_step(
        (max_lon - min_lon) / calculate_grid_steps(center_lat)[1],
        (max_lat - min_lat) / calculate_grid_steps(center_lat)[0]
    )

    # 4. Header and fit bounds
    add_top_center_header(
        gnss_map,
        points_count,
        total_distance_km,
        optimal_step_m,
        no_bg=args.no_header_bg,
        bg_color=args.header_bg
    )
    gnss_map.fit_bounds(gnss_map.get_bounds())

    # 5. Save and open
    gnss_map.save(args.output)
    print(f"Success! Map rendering saved to: {args.output}")
    print("Opening the map in your web browser...")
    webbrowser.open('file://' + os.path.realpath(args.output))


if __name__ == "__main__":
    main()