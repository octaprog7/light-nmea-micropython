#!/usr/bin/env python3
"""
GNSS Track Visualization Script for LightNMEA.
Generates an interactive HTML map from a CSV log file with an adaptive metric grid.
Dependencies: pandas, folium
"""

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

# Configuration constants
CSV_FILE = "gnss_log.csv"
OUTPUT_HTML = "gnss_track.html"
VALID_FIX_VALUE = 1

# Map styling constants
MAP_TILES_URL = "https://{s}://{z}/{x}/{y}.png"
MAP_ATTRIBUTION = "&copy; OpenStreetMap contributors &copy; CARTO"
GRID_LINE_COLOR = "gray"
GRID_LINE_WEIGHT = 0.5
GRID_LINE_OPACITY = 0.4
TRACK_LINE_COLOR = "blue"
TRACK_LINE_WEIGHT = 4
TRACK_LINE_OPACITY = 0.8

# WGS-84 Ellipsoid constants for dynamic distance calculations
WGS84_A = 6378137.0  # Semi-major axis in meters
WGS84_B = 6356752.3142  # Semi-minor axis in meters

# Grid layout constants
GRID_STEP_METERS = 10.0
GRID_RADIUS_STEPS = 25  # Increased span to cover full drifted area tightly


def calculate_grid_steps(center_lat):
    """Calculates latitude and longitude step increments using cached math results."""
    lat_rad = math.radians(center_lat)
    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)

    # Eccentricity formulas for precise ellipsoid distance calculation
    a_sq = WGS84_A ** 2
    b_sq = WGS84_B ** 2
    e_sq = (a_sq - b_sq) / a_sq
    radius_factor = 1.0 - e_sq * (sin_lat ** 2)

    meters_per_lat = (math.pi * WGS84_A * (1.0 - e_sq)) / (180.0 * (radius_factor ** 1.5))
    meters_per_lon = (math.pi * WGS84_A * cos_lat) / (180.0 * math.sqrt(radius_factor))

    step_lat = GRID_STEP_METERS / meters_per_lat
    step_lon = GRID_STEP_METERS / meters_per_lon
    return step_lat, step_lon


def draw_grid_line(gps_map, start_point, end_point):
    """Draws a single thin gray line on the map layout using cached folium link."""
    folium.PolyLine(
        locations=[start_point, end_point],
        color=GRID_LINE_COLOR,
        weight=GRID_LINE_WEIGHT,
        opacity=GRID_LINE_OPACITY
    ).add_to(gps_map)


def generate_metric_grid(gps_map, center_lat, center_lon):
    """Generates an adaptive bounding grid overlay on the map with cached step logic."""
    step_lat, step_lon = calculate_grid_steps(center_lat)

    start_lat = center_lat - (GRID_RADIUS_STEPS * step_lat)
    end_lat = center_lat + (GRID_RADIUS_STEPS * step_lat)
    start_lon = center_lon - (GRID_RADIUS_STEPS * step_lon)
    end_lon = center_lon + (GRID_RADIUS_STEPS * step_lon)

    # Cache grid line renderer link for fast iteration loop execution
    _add_line = draw_grid_line

    # Draw horizontal grid lines (Latitude lanes)
    current_lat = start_lat
    while current_lat <= end_lat:
        _add_line(gps_map, [current_lat, start_lon], [current_lat, end_lon])
        current_lat += step_lat

    # Draw vertical grid lines (Longitude lanes)
    current_lon = start_lon
    while current_lon <= end_lon:
        _add_line(gps_map, [start_lat, current_lon], [end_lat, current_lon])
        current_lon += step_lon


def get_marker_timestamp(df, index):
    """Formats and returns a timestamp string from a specific row index."""
    return "{} {}".format(df.iloc[index][FIELD_DATE], df.iloc[index][FIELD_TIME])


def add_top_center_header(gps_map, points_count, grid_step):
    """Adds a fixed, styled top-center HTML header card with map metadata."""
    header_html = f"""
    <div style="
        position: fixed; 
        top: 20px; 
        left: 50%; 
        transform: translateX(-50%);
        background-color: rgba(255, 255, 255, 0.9); 
        font-family: 'Courier New', Courier, monospace;
        font-weight: bold;
        font-size: 14px;
        color: #333333;
        border: 2px solid #999999; 
        border-radius: 6px;
        padding: 10px 20px; 
        z-index: 9999;
        box-shadow: 0px 2px 5px rgba(0,0,0,0.2);
        text-align: center;
        white-space: nowrap;
    ">
        Grid step: {grid_step:.1f} m | Total points: {points_count}
    </div>
    """
    gps_map.get_root().html.add_child(folium.Element(header_html))


def main():
    print(f"Reading GNSS data from {CSV_FILE}...")

    if not os.path.exists(CSV_FILE):
        print(f"Error: file {CSV_FILE} not found!")
        print("Please run this script in the directory containing the log file.")
        sys.exit(1)

    df = None
    try:
        df = pd.read_csv(CSV_FILE, on_bad_lines='skip')
    except Exception as e:
        print(f"Read error: {e}")
        sys.exit(1)

    # Verify that required columns exist in the CSV file
    required_columns = [FIELD_DATE, FIELD_TIME, FIELD_VALID, FIELD_LATITUDE, FIELD_LONGITUDE]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print(f"Error: missing required columns: {', '.join(missing_columns)}")
        sys.exit(1)

    # Convert coordinates and validity flag to numeric, handling potential NaN/corrupted chunks
    df[FIELD_VALID] = pd.to_numeric(df[FIELD_VALID], errors='coerce').fillna(0).astype(int)
    df[FIELD_LATITUDE] = pd.to_numeric(df[FIELD_LATITUDE], errors='coerce')
    df[FIELD_LONGITUDE] = pd.to_numeric(df[FIELD_LONGITUDE], errors='coerce')

    # Filter out invalid values and zeros (GPS modules without a fixed reference lock)
    df_valid = df[df[FIELD_VALID] == VALID_FIX_VALUE].copy()
    df_valid = df_valid.dropna(subset=[FIELD_LATITUDE, FIELD_LONGITUDE])
    df_valid = df_valid[(df_valid[FIELD_LATITUDE] != 0) & (df_valid[FIELD_LONGITUDE] != 0)]

    if df_valid.empty:
        print("Error: no valid coordinates found in the log file!")
        sys.exit(1)

    # Sort data by date and time to ensure accurate sequential tracking path order
    df_valid = df_valid.sort_values([FIELD_DATE, FIELD_TIME]).reset_index(drop=True)
    points_count = len(df_valid)
    print(f"Total rows parsed: {len(df)}. Found {points_count} valid data points.")

    # Calculate map center location based on average tracking metrics
    center_lat = float(df_valid[FIELD_LATITUDE].mean())
    center_lon = float(df_valid[FIELD_LONGITUDE].mean())

    print("Generating map layers...")
    gps_map = folium.Map(
        location=[center_lat, center_lon],
        tiles=MAP_TILES_URL,
        attr=MAP_ATTRIBUTION
    )

    # Append adaptive metric system grid lines layer
    generate_metric_grid(gps_map, center_lat, center_lon)

    # Extract clean coordinate list structure for path rendering
    track_coords = df_valid[[FIELD_LATITUDE, FIELD_LONGITUDE]].values.tolist()

    # Overlay primary track line
    folium.PolyLine(
        locations=track_coords,
        color=TRACK_LINE_COLOR,
        weight=TRACK_LINE_WEIGHT,
        opacity=TRACK_LINE_OPACITY,
        tooltip="GPS Track"
    ).add_to(gps_map)

    # Render starting milestone flag (Green) - FIXED index slice bug here
    folium.Marker(
        location=track_coords[0],
        popup="Start<br>Time: {}".format(get_marker_timestamp(df_valid, 0)),
        icon=folium.Icon(color="green", icon="play-circle", prefix="fa")
    ).add_to(gps_map)

    # Render trailing terminus milestone flag (Red)
    folium.Marker(
        location=track_coords[-1],
        popup="End<br>Time: {}".format(get_marker_timestamp(df_valid, -1)),
        icon=folium.Icon(color="red", icon="stop-circle", prefix="fa")
    ).add_to(gps_map)

    # Add floating top-center header card with metrics metadata
    add_top_center_header(gps_map, points_count, GRID_STEP_METERS)

    # Automatically fit map view margins boundaries around the tracking path metrics
    gps_map.fit_bounds(gps_map.get_bounds())

    # Save target interactive HTML layer
    gps_map.save(OUTPUT_HTML)
    print(f"Success! Map rendering saved to: {OUTPUT_HTML}")

    # Automatically open the generated HTML file in the default web browser
    print("Opening the map in your web browser...")
    webbrowser.open('file://' + os.path.realpath(OUTPUT_HTML))


if __name__ == "__main__":
    main()
