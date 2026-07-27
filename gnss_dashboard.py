#!/usr/bin/env python3

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

"""
Оптимизированный GNSS-дашборд для SBC и Desktop PC.
Python 3.9+, рамки и ASCII-текст.
Поддержка USB-UART с настраиваемым baudrate и авто-реконнектом.
"""

import os
import sys

# Проверка мин. версии Python
if sys.version_info < (3, 9):
    print(
        f"Error: The dashboard requires Python 3.9 or later.\n"
        f"Your Python version: {sys.version.split()[0]}",
        file=sys.stderr
    )
    sys.exit(1)

import time
import math
import serial
import curses
from typing import Optional, Tuple, List
import serial.tools.list_ports

# Serial / USB
DEFAULT_BAUDRATE = 115200
SERIAL_TIMEOUT_S = 0.05
RECONNECT_DELAY_S = 2.0

# UI / Curses
UI_TIMEOUT_MS = 50
CURSOR_VISIBLE = 0
VK_ESCAPE = 27
DIVIDER_LENGTH = 20
FRAME_MARGIN = 2
TITLE_OFFSET_X = 2
LABEL_X_DEFAULT = 2  # Отступ метки по умолчанию (используется, если не переопределен)
CONTENT_START_Y = 2

# Цвета
COLOR_ERROR = 1
COLOR_OK = 2

# Компас
FULL_CIRCLE_DEG = 360.0
COMPASS_DIVISIONS = 8
COMPASS_OFFSET_DEG = 22.5
COMPASS_SECTOR_DEG = 45.0

# CSV
CSV_FIELDS_COUNT = 12

# Разделение экрана
SPLIT_HORIZONTAL = 2
SPLIT_VERTICAL = 2

# Анализ точности
STATIONARY_SPEED_KMH = 2.0
STATIONARY_TIME_S = 60.0
M_PER_DEG_LAT = 111_320.0
MIN_POINTS_FOR_ACCURACY = 2

# Для пересчета
_TO_KMH = 1.0

# Логирование
LOG_FILENAME = 'gnss_log.csv'
LOG_ENCODING = 'utf-8'
LOG_TIMESTAMP_FMT = "%H:%M:%S"
LOG_CSV_HEADER = "timestamp,valid,satellites,latitude,longitude,speed,course,altitude,time,date,constellation,fix_mode,hdop\n"

# Проверка окружения
def ensure_terminal() -> None:
    """Нужно убедиться, что переменная окружения TERM установлена для curses."""
    term = os.environ.get("TERM")
    if not term or term == "unknown":
        if sys.stdout.isatty():
            os.environ["TERM"] = "xterm-256color"
        else:
            print(
                "Ошибка: скрипт требует интерактивный терминал.\n"
                "Запустите из терминала (не из IDE) или установите переменную окружения TERM:\n"
                "  export TERM=xterm-256color\n"
                "  python3 gnss_dashboard.py",
                file=sys.stderr
            )
            sys.exit(1)


ensure_terminal()


# Модель данных
class GNSSData:
    """Одна строка данных от GNSS-приёмника."""
    __slots__ = (
        'valid', 'satellites', 'latitude', 'longitude',
        'speed', 'course', 'altitude', 'time', 'date',
        'constellation', 'fix_mode', 'hdop'
    )

    EXPECTED_FIELDS = CSV_FIELDS_COUNT

    def __init__(self):
        self.valid = ""
        self.satellites: Optional[int] = None
        self.latitude: Optional[float] = None
        self.longitude: Optional[float] = None
        self.speed: Optional[float] = None
        self.course: Optional[float] = None
        self.altitude: Optional[float] = None
        self.time = ""
        self.date = ""
        self.constellation = ""
        self.fix_mode = ""
        self.hdop: Optional[float] = None

    @classmethod
    def from_csv(cls, line: str) -> 'GNSSData':
        """Парсит CSV-строку. Выбрасывает ValueError при несовпадении числа полей."""
        parts = line.split(',')
        if len(parts) != cls.EXPECTED_FIELDS:
            raise ValueError(f"Ожидается {cls.EXPECTED_FIELDS} полей, получено {len(parts)}")

        obj = cls()
        obj.valid = parts[0]
        obj.satellites = int(parts[1]) if parts[1] else None
        obj.latitude = float(parts[2]) if parts[2] else None
        obj.longitude = float(parts[3]) if parts[3] else None
        obj.speed = float(parts[4]) if parts[4] else None
        obj.course = float(parts[5]) if parts[5] else None
        obj.altitude = float(parts[6]) if parts[6] else None
        obj.time = parts[7]
        obj.date = parts[8]
        obj.constellation = parts[9]
        obj.fix_mode = parts[10]
        obj.hdop = float(parts[11]) if parts[11] else None
        return obj

    @staticmethod
    def compass_letter(course: float) -> str:
        """Преобразует курс (угол в градусах) в строковое обозначение стороны света."""
        dirs = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
        idx = int((course % FULL_CIRCLE_DEG + COMPASS_OFFSET_DEG) / COMPASS_SECTOR_DEG) % COMPASS_DIVISIONS
        return dirs[idx]


class DashboardStats:
    """Статистика и текущее состояние дашборда."""
    __slots__ = (
        'port', 'baudrate', 'success', 'errors',
        'disconnected', 'reconnects', 'is_stationary',
        'stationary_timer', 'accuracy_tracker', 'log_writer'
    )

    def __init__(self, port: str, baudrate: int):
        self.port = port
        self.baudrate = baudrate
        self.success = 0
        self.errors = 0
        self.disconnected = False
        self.reconnects = 0
        self.is_stationary = False
        self.stationary_timer = 0.0
        self.accuracy_tracker = AccuracyTracker()
        self.log_writer: Optional['LogWriter'] = None


class LogWriter:
    """Запись строки GNSS-данных от платы в CSV-файл с timestamp."""
    __slots__ = ('_file', '_filename', '_packet_count', '_is_writing')

    def __init__(self, filename: str = LOG_FILENAME):
        self._filename = filename
        self._file = None
        self._packet_count = 0
        self._is_writing = False
        self._open()

    def _open(self) -> None:
        try:
            self._file = open(self._filename, 'a', encoding=LOG_ENCODING)
            if self._file.tell() == 0:
                self._file.write(LOG_CSV_HEADER)
                self._file.flush()
            self._is_writing = True
        except OSError as ex:
            print(f"Error opening log {self._filename}: {ex}", file=sys.stderr)
            self._file = None
            self._is_writing = False

    @property
    def is_open(self) -> bool:
        return self._file is not None and not self._file.closed

    @property
    def is_writing(self) -> bool:
        return self._is_writing and self.is_open

    @property
    def lines_written(self) -> int:
        return self._packet_count

    def reset_count(self) -> None:
        self._packet_count = 0

    def write(self, raw_line: str) -> None:
        if self._file is None or self._file.closed:
            self._is_writing = False
            return
        try:
            timestamp = time.strftime(LOG_TIMESTAMP_FMT)
            self._file.write(f"{timestamp},{raw_line}\n")
            self._file.flush()
            self._packet_count += 1
            self._is_writing = True
        except OSError as ex:
            print(f"Error writing to log: {ex}", file=sys.stderr)
            self._is_writing = False

    def close(self) -> None:
        self._is_writing = False
        if self._file is not None and not self._file.closed:
            try:
                self._file.close()
            except OSError:
                pass


class AccuracyTracker:
    """Расчёт точности GNSS по алгоритму Уэлфорда."""
    __slots__ = (
        'n', 'mean_lat', 'mean_lon', 'm2_lat', 'm2_lon',
        'min_lat', 'max_lat', 'min_lon', 'max_lon',
        'first_lat', 'first_lon', 'last_lat', 'last_lon',
        'valid_fix_count', 'hdop_sum', 'hdop_count'
    )

    def __init__(self):
        self.n = 0
        self.mean_lat = 0.0
        self.mean_lon = 0.0
        self.m2_lat = 0.0
        self.m2_lon = 0.0
        self.min_lat: Optional[float] = None
        self.max_lat: Optional[float] = None
        self.min_lon: Optional[float] = None
        self.max_lon: Optional[float] = None
        self.first_lat: Optional[float] = None
        self.first_lon: Optional[float] = None
        self.last_lat: Optional[float] = None
        self.last_lon: Optional[float] = None
        self.valid_fix_count = 0
        self.hdop_sum = 0.0
        self.hdop_count = 0

    def reset(self) -> None:
        self.n = 0
        self.mean_lat = 0.0
        self.mean_lon = 0.0
        self.m2_lat = 0.0
        self.m2_lon = 0.0
        self.min_lat = None
        self.max_lat = None
        self.min_lon = None
        self.max_lon = None
        self.first_lat = None
        self.first_lon = None
        self.last_lat = None
        self.last_lon = None
        self.valid_fix_count = 0
        self.hdop_sum = 0.0
        self.hdop_count = 0

    def add_point(self, data: GNSSData) -> None:
        if data.latitude is None or data.longitude is None:
            return

        lat, lon = data.latitude, data.longitude
        self.n += 1

        if self.n == 1:
            self.first_lat = self.last_lat = lat
            self.first_lon = self.last_lon = lon
            self.min_lat = self.max_lat = lat
            self.min_lon = self.max_lon = lon
        else:
            self.last_lat = lat
            self.last_lon = lon
            if lat < self.min_lat: self.min_lat = lat
            if lat > self.max_lat: self.max_lat = lat
            if lon < self.min_lon: self.min_lon = lon
            if lon > self.max_lon: self.max_lon = lon

        delta_lat = lat - self.mean_lat
        delta_lon = lon - self.mean_lon
        self.mean_lat += delta_lat / self.n
        self.mean_lon += delta_lon / self.n
        delta2_lat = lat - self.mean_lat
        delta2_lon = lon - self.mean_lon
        self.m2_lat += delta_lat * delta2_lat
        self.m2_lon += delta_lon * delta2_lon

        if data.fix_mode and data.fix_mode != "Not Valid":
            self.valid_fix_count += 1
        if data.hdop is not None:
            self.hdop_sum += data.hdop
            self.hdop_count += 1

    def get_metrics(self) -> Optional[dict]:
        if self.n < MIN_POINTS_FOR_ACCURACY:
            return None

        var_lat = self.m2_lat / (self.n - 1)
        var_lon = self.m2_lon / (self.n - 1)
        std_lat = math.sqrt(var_lat)
        std_lon = math.sqrt(var_lon)

        lat_rad = math.radians(self.mean_lat)
        m_per_deg_lon = M_PER_DEG_LAT * math.cos(lat_rad)

        err_lat_m = std_lat * M_PER_DEG_LAT
        err_lon_m = std_lon * m_per_deg_lon
        err_2d_m = math.sqrt(err_lat_m ** 2 + err_lon_m ** 2)

        drift_m = 0.0
        if self.first_lat is not None and self.last_lat is not None:
            delta_lat_m = (self.last_lat - self.first_lat) * M_PER_DEG_LAT
            delta_lon_m = (self.last_lon - self.first_lon) * m_per_deg_lon
            drift_m = math.sqrt(delta_lat_m ** 2 + delta_lon_m ** 2)

        valid_pct = 100.0 * self.valid_fix_count / self.n if self.n > 0 else 0.0
        avg_hdop = self.hdop_sum / self.hdop_count if self.hdop_count > 0 else 0.0

        return {
            'n': self.n,
            'valid_pct': valid_pct,
            'avg_hdop': avg_hdop,
            'err_2d_m': err_2d_m,
            'drift_m': drift_m,
            'std_lat': std_lat,
            'std_lon': std_lon,
            'min_lat': self.min_lat,
            'max_lat': self.max_lat,
            'min_lon': self.min_lon,
            'max_lon': self.max_lon,
        }


# ==============================================================================
# ПАРСЕР ПОСЛЕДОВАТЕЛЬНОГО ПОРТА
# ==============================================================================
class SerialParser:
    """Объединяет работу с serial-портом и bytearray-буфером."""

    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE, timeout: float = SERIAL_TIMEOUT_S):
        self.port = port
        self.baudrate = baudrate
        self._timeout = timeout
        self._ser: Optional[serial.Serial] = None
        self._buffer = bytearray()
        self._read = None
        self._open()

    def _open(self) -> bool:
        try:
            self._ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=self._timeout)
            self._read = self._ser.read
            return True
        except serial.SerialException:
            self._ser = None
            self._read = None
            return False

    def reconnect(self) -> bool:
        self.close()
        return self._open()

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def close(self) -> None:
        if self._ser is not None:
            if self._ser.is_open:
                try:
                    self._ser.close()
                except (serial.SerialException, OSError):
                    pass
            self._ser = None
            self._read = None

    def poll(self) -> Tuple[Optional[GNSSData], bool, Optional[str]]:
        if not self.is_open:
            return None, False, None

        in_waiting = self._ser.in_waiting
        if in_waiting:
            self._buffer.extend(self._read(in_waiting))

        newline_idx = self._buffer.find(b'\n')
        if newline_idx == -1:
            return None, False, None

        line_bytes = self._buffer[:newline_idx]
        del self._buffer[:newline_idx + 1]

        line_str = line_bytes.decode('utf-8', errors='ignore').strip()
        if not line_str:
            return None, False, None

        try:
            return GNSSData.from_csv(line_str), False, line_str
        except ValueError:
            return None, True, line_str


# Базовый класс окна дашборда
class BaseWindow:
    TITLE = "Window"
    BOX_TL, BOX_TR, BOX_BL, BOX_BR = "┌", "┐", "└", "┘"
    BOX_H, BOX_V = "─", "│"

    def __init__(self, win: 'curses.window', label_x: int = LABEL_X_DEFAULT, value_x: int = 14):
        self.win = win
        self._label_x = label_x
        self._value_x = value_x
        self._addstr = win.addnstr
        self._erase = win.erase
        self._noutrefresh = win.noutrefresh
        self._getmaxyx = win.getmaxyx
        self._cursor_y = CONTENT_START_Y

    def _reset_cursor(self) -> None:
        self._cursor_y = CONTENT_START_Y

    def _draw_line(self, text: str, attr: int = 0, x: int = None) -> None:
        draw_x = x if x is not None else self._label_x
        self._safe_addstr(self._cursor_y, draw_x, text, attr)
        self._cursor_y += 1

    def _draw_labeled(self, label: str, value: str, value_x: int = None, label_attr: int = curses.A_BOLD,
                      value_attr: int = 0) -> None:
        vx = value_x if value_x is not None else self._value_x
        self._safe_addstr(self._cursor_y, self._label_x, label, label_attr)
        self._safe_addstr(self._cursor_y, vx, value, value_attr)
        self._cursor_y += 1

    def _draw_box(self) -> None:
        self._erase()
        max_y, max_x = self._getmaxyx()
        top = self.BOX_TL + self.BOX_H * (max_x - FRAME_MARGIN) + self.BOX_TR
        bottom = self.BOX_BL + self.BOX_H * (max_x - FRAME_MARGIN) + self.BOX_BR

        try:
            self._addstr(0, 0, top, max_x)
            self._addstr(max_y - 1, 0, bottom, max_x)
        except curses.error:
            pass

        for y in range(1, max_y - 1):
            try:
                self._addstr(y, 0, self.BOX_V, 1)
                self._addstr(y, max_x - 1, self.BOX_V, 1)
            except curses.error:
                pass

        title_str = f" {self.TITLE} "
        try:
            self._addstr(0, TITLE_OFFSET_X, title_str, len(title_str), curses.A_BOLD)
        except curses.error:
            pass

    def _safe_addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        try:
            max_y, max_x = self._getmaxyx()
            if 0 <= y < max_y and 0 <= x < max_x:
                self._addstr(y, x, text, max_x - x, attr)
        except curses.error:
            pass

    @staticmethod
    def _fmt(value, fmt: str = "") -> str:
        if value is None or value == "":
            return "---"
        return f"{value:{fmt}}" if fmt else str(value)

    def draw(self, data: GNSSData, stats: DashboardStats) -> None:
        self._draw_box()
        self._reset_cursor()
        self._draw_content(data, stats)

    def _draw_content(self, data: GNSSData, stats: DashboardStats) -> None:
        raise NotImplementedError

    def noutrefresh(self) -> None:
        self._noutrefresh()


class PositionWindow(BaseWindow):
    """Окно широты и долготы"""
    TITLE = "Positioning"

    def _draw_content(self, data: GNSSData, stats: DashboardStats) -> None:
        self._draw_labeled("Latitude: ", self._fmt(data.latitude, ".6f"))
        self._draw_labeled("Longitude:", self._fmt(data.longitude, ".6f"))
        self._draw_labeled("Altitude: ", f"{data.altitude:.1f} m" if data.altitude is not None else "--- m")
        self._draw_labeled("UTC Time: ", self._fmt(data.time))
        self._draw_labeled("UTC Date: ", self._fmt(data.date))


# Окно
class GNSSWindow(BaseWindow):
    """Окно параметров GNSS"""
    TITLE = "GNSS Parameters"

    def _draw_content(self, data: GNSSData, stats: DashboardStats) -> None:
        self._draw_labeled("Constellation:", self._fmt(data.constellation))
        self._draw_labeled("Satellites:   ", self._fmt(data.satellites))
        self._draw_labeled("HDOP:         ", f"{data.hdop:.1f}" if data.hdop is not None else "---")
        fix = data.fix_mode or "---"
        attr = curses.A_REVERSE | curses.color_pair(COLOR_ERROR) if fix == "Not Valid" else 0
        self._draw_labeled("Fix Mode:     ", fix, value_attr=attr)


class MotionWindow(BaseWindow):
    def _draw_content(self, data: GNSSData, stats: DashboardStats) -> None:
        if stats.is_stationary:
            self._draw_accuracy(stats.accuracy_tracker)
        else:
            self._draw_motion(data, stats)

    def _draw_motion(self, data: GNSSData, stats: DashboardStats) -> None:
        title_str = " Motion Dynamics "
        try:
            self._addstr(0, TITLE_OFFSET_X, title_str, len(title_str), curses.A_BOLD)
        except curses.error:
            pass

        speed_kmh = data.speed * _TO_KMH if data.speed is not None else 0.0
        speed_str = f"{speed_kmh:.1f} km/h" if data.speed is not None else "--- km/h"
        self._draw_labeled("Speed:", speed_str)

        if data.course is not None:
            letter = GNSSData.compass_letter(data.course)
            course_str = f"{data.course:.1f}° ({letter})"
        else:
            if data.speed is None or speed_kmh < STATIONARY_SPEED_KMH:
                course_str = "--- (too slow)"
            elif data.fix_mode == "Not Valid":
                course_str = "--- (no fix)"
            else:
                course_str = "---"
        self._draw_labeled("Course:", course_str)

        if stats.stationary_timer > 0.0:
            remaining = STATIONARY_TIME_S - (time.monotonic() - stats.stationary_timer)
            if 0 < remaining < STATIONARY_TIME_S:
                self._draw_line(f"Accuracy mode in: {int(remaining)}s", curses.A_DIM)

    def _draw_accuracy(self, tracker: AccuracyTracker) -> None:
        title_str = " Accuracy Analysis "
        try:
            self._addstr(0, TITLE_OFFSET_X, title_str, len(title_str), curses.A_BOLD | curses.color_pair(COLOR_OK))
        except curses.error:
            pass

        metrics = tracker.get_metrics()
        if not metrics:
            self._draw_line(f"Collecting data: {tracker.n}/{MIN_POINTS_FOR_ACCURACY} points")
            return

        self._draw_labeled("Points:       ", str(metrics['n']))
        self._draw_labeled("Valid Fix:    ", f"{metrics['valid_pct']:.1f}%")
        self._draw_labeled("Avg HDOP:     ", f"{metrics['avg_hdop']:.2f}")
        self._draw_line("-" * DIVIDER_LENGTH, curses.A_DIM)
        self._draw_labeled("2D Error(1\u03C3): ", f"+/-{metrics['err_2d_m']:.2f} m",
                           value_attr=curses.A_BOLD | curses.color_pair(COLOR_ERROR))
        self._draw_labeled("Drift:        ", f"~{metrics['drift_m']:.2f} m")


class StatusWindow(BaseWindow):
    """Окно состояния соединения с платой-поставщиком данных GNSS"""
    TITLE = "Connection Status"

    def _draw_content(self, data: GNSSData, stats: DashboardStats) -> None:
        port_type = "USB-UART" if "ttyACM" in stats.port or "ttyUSB" in stats.port else "Serial"
        self._draw_line(f"Port: {stats.port} ({port_type})")
        self._draw_line(f"Speed: {stats.baudrate} (USB max)")

        if stats.disconnected:
            attr = curses.A_BOLD | curses.color_pair(COLOR_ERROR)
            self._draw_line("Status: DISCONNECTED (reconnecting...)", attr)
        else:
            self._draw_line("Status: CONNECTED", curses.A_BOLD | curses.color_pair(COLOR_OK))

        self._draw_line(f"Valid lines: {stats.success}")
        self._draw_line(f"Errors: {stats.errors}")
        self._draw_line(f"Reconnects: {stats.reconnects}")
        self._draw_line("-" * DIVIDER_LENGTH, curses.A_DIM)

        if stats.log_writer:
            lw = stats.log_writer
            if lw.is_writing:
                self._draw_line("Logging: ACTIVE", curses.A_BOLD | curses.color_pair(COLOR_OK))
            else:
                self._draw_line("Logging: INACTIVE", curses.A_DIM)
            self._draw_line(f"Lines written: {lw.lines_written}")


class Dashboard:
    """Координирует расположение окон, парсер и цикл отрисовки."""
    WINDOWS = (PositionWindow, GNSSWindow, MotionWindow, StatusWindow)
    RECONNECT_DELAY = RECONNECT_DELAY_S

    def __init__(self, stdscr: 'curses.window', parser: SerialParser):
        self.stdscr = stdscr
        self.parser = parser
        self.data = GNSSData()
        self.stats = DashboardStats(parser.port, parser.baudrate)
        self.stats.disconnected = not parser.is_open
        self.log_writer = LogWriter()
        self.stats.log_writer = self.log_writer

        self._configure_curses()
        self._build_layout()

        self._getch = stdscr.getch
        self._doupdate = curses.doupdate
        self._last_reconnect_attempt = 0.0

    def _configure_curses(self) -> None:
        curses.curs_set(CURSOR_VISIBLE)
        self.stdscr.nodelay(True)
        self.stdscr.timeout(UI_TIMEOUT_MS)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(COLOR_ERROR, curses.COLOR_RED, -1)
        curses.init_pair(COLOR_OK, curses.COLOR_GREEN, -1)

    def _build_layout(self) -> None:
        """Рассчитывает размеры и создает окна, передавая им их внутренние координаты."""
        h, w = self.stdscr.getmaxyx()
        mid_h = h // SPLIT_HORIZONTAL
        mid_w = w // SPLIT_VERTICAL

        # Формат: (height, width, y, x, WindowClass, label_x, value_x)
        specs = (
            (mid_h, mid_w, 0, 0, PositionWindow, 2, 14),
            (mid_h, w - mid_w, 0, mid_w, GNSSWindow, 2, 18),
            (h - mid_h, mid_w, mid_h, 0, MotionWindow, 2, 20),  # 20 для "2D Error(1σ): "
            (h - mid_h, w - mid_w, mid_h, mid_w, StatusWindow, 2, 2),
        )

        self.panels: List[BaseWindow] = []
        for ph, pw, py, px, cls, lx, vx in specs:
            win = curses.newwin(ph, pw, py, px)
            self.panels.append(cls(win, label_x=lx, value_x=vx))

    def _handle_input(self) -> bool:
        key = self._getch()
        if key in (ord('q'), ord('Q'), VK_ESCAPE):
            return True
        if key == curses.KEY_RESIZE:
            self._build_layout()
        return False

    def _try_reconnect(self) -> None:
        now = time.monotonic()
        if now - self._last_reconnect_attempt < self.RECONNECT_DELAY:
            return
        self._last_reconnect_attempt = now

        if self.parser.reconnect():
            self.stats.disconnected = False
            self.stats.reconnects += 1
            self.stats.success = 0
            self.stats.errors = 0
            self.log_writer.reset_count()

    def _poll_serial(self) -> None:
        try:
            data, is_error, raw_line = self.parser.poll()

            if raw_line is not None:
                self.log_writer.write(raw_line)

            if data is not None:
                self.data = data
                self.stats.success += 1

                speed_kmh = data.speed * _TO_KMH if data.speed is not None else 0.0
                now = time.monotonic()

                if speed_kmh < STATIONARY_SPEED_KMH:
                    if not self.stats.is_stationary:
                        if self.stats.stationary_timer == 0.0:
                            self.stats.stationary_timer = now
                        elif now - self.stats.stationary_timer >= STATIONARY_TIME_S:
                            self.stats.is_stationary = True
                            self.stats.accuracy_tracker.reset()
                    if self.stats.is_stationary:
                        self.stats.accuracy_tracker.add_point(data)
                else:
                    self.stats.is_stationary = False
                    self.stats.stationary_timer = 0.0
                    self.stats.accuracy_tracker.reset()
            elif is_error:
                self.stats.errors += 1
        except (serial.SerialException, OSError):
            self.stats.disconnected = True
            self.parser.close()
            self._last_reconnect_attempt = 0

    def _render(self) -> None:
        for panel in self.panels:
            panel.draw(self.data, self.stats)
            panel.noutrefresh()
        self._doupdate()

    def run(self) -> None:
        handle_input = self._handle_input
        poll_serial = self._poll_serial
        render = self._render
        try_reconnect = self._try_reconnect

        try:
            while True:
                if handle_input():
                    break
                if self.stats.disconnected:
                    try_reconnect()
                else:
                    poll_serial()
                render()
        except serial.SerialException:
            pass


# Авто определение порта для связи с платой - поставщиком данных
def detect_port() -> str:
    ports = serial.tools.list_ports.comports()
    for port_info in ports:
        device = port_info.device
        if "ttyACM" in device or "ttyUSB" in device:
            return device

    if os.path.exists("/dev/ttyACM0"):
        return "/dev/ttyACM0"
    if os.path.exists("/dev/ttyUSB0"):
        return "/dev/ttyUSB0"

    raise RuntimeError("No available USB-UART ports (ttyACM* or ttyUSB*) were found.")


def parse_args() -> Tuple[str, int]:
    """Парсит аргументы командной строки"""
    port = detect_port()
    baudrate = DEFAULT_BAUDRATE

    if len(sys.argv) > 1:
        port = sys.argv[1]
    if len(sys.argv) > 2:
        try:
            baudrate = int(sys.argv[2])
        except ValueError:
            print(f"Invalid baudrate: {sys.argv[2]}", file=sys.stderr)
            sys.exit(1)

    return port, baudrate


def main(stdscr: 'curses.window') -> None:
    port, baudrate = parse_args()
    parser = SerialParser(port, baudrate=baudrate)
    dashboard = Dashboard(stdscr, parser)
    try:
        dashboard.run()  # ИСПРАВЛЕНО: был вызов конструктора второй раз
    finally:
        parser.close()
        dashboard.log_writer.close()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
    except curses.error as e:  # ИСПРАВЛЕНО: _curses.error -> curses.error
        print(f"curses error: {e}", file=sys.stderr)
        print("Make sure you run the script from an interactive terminal.", file=sys.stderr)
        sys.exit(1)