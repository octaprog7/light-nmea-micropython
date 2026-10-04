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
import serial
import curses
from typing import Optional, List
from dash_utils import (now, log_msg, format_speed, get_port_type, parse_args,
                        PLACEHOLDER, SYS_MSG_PREFIX, DEFAULT_MODULE_NAME,
                        MCU_MSG_MODULE_DETECTED, MCU_MSG_SOFTWARE_RESET,
                        MCU_MSG_WATCHDOG_TRIGGERED, RECONNECT_DELAY_S,
                        STATIONARY_SPEED_KMH, STATIONARY_TIME_S,
                        MIN_POINTS_FOR_ACCURACY, _TO_KMH,
                        GNSSData, LogWriter, AccuracyTracker, SerialParser,
                        SomeInfo, DATA_STREAM_NMEA_0183, code_to_mfr_string,
                        # DATA_STREAM_UNKNOWN, DATA_STREAM_CSV,
                        )

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _curses import _CursesWindow
else:
    from typing import Any
    _CursesWindow = Any

# Проверка мин. версии Python
if sys.version_info < (3, 9):
    log_msg(
        f"Error: The dashboard requires Python 3.9 or later.\n"
        f"Your Python version: {sys.version.split()[0]}",
    sys.stderr)
    sys.exit(1)

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

# Разделение экрана
SPLIT_HORIZONTAL = 2
SPLIT_VERTICAL = 2

# Активность логирования
LOG_ACTIVITY_TIMEOUT_S = 10.0  # Если данных нет 10 секунд - считаю неактивным

# Минимальная высота терминала
MIN_TERM_HEIGHT = 24
# Минимальная ширина терминала
MIN_TERM_WIDTH = 80

# Утилиты
def reset_stationary_state(stats: 'DashboardStats') -> None:
    """Сбрасывает состояние стационарности и трекер точности."""
    stats.is_stationary = False
    stats.stationary_timer = 0.0
    stats.accuracy_tracker.reset()


def draw_window_title(win: 'curses.window', title: str, attr: int = curses.A_BOLD) -> None:
    """Выводит заголовок окна."""
    title_str = f" {title} "
    try:
        win.addnstr(0, TITLE_OFFSET_X, title_str, len(title_str), attr)
    except curses.error:
        pass


# Цветовые атрибуты (инициализируются после запуска curses). Смотри _configure_curses.
ATTR_OK = 0
ATTR_ERROR = 0
ATTR_ERROR_REVERSE = 0
ATTR_DIM = 0


# Проверка окружения
def ensure_terminal() -> None:
    """Нужно убедиться, что переменная окружения TERM установлена для curses."""
    term = os.environ.get("TERM")
    if not term or term == "unknown":
        if sys.stdout.isatty():
            os.environ["TERM"] = "xterm-256color"
        else:
            log_msg(
                "Error: The script requires an interactive terminal..\n"
                "Run from terminal (not from IDE) or set TERM environment variable:\n"
                "  export TERM=xterm-256color\n"
                "  python3 gnss_dashboard.py",
                sys.stderr
            )
            sys.exit(1)


ensure_terminal()


class DashboardStats:
    """Статистика и текущее состояние дашборда."""
    __slots__ = (
        'port', 'baudrate', 'success', 'errors',
        'disconnected', 'reconnects', 'is_stationary',
        'stationary_timer', 'accuracy_tracker', 'log_writer', 'gnss_module_name', 'software_resets', 'last_data_time'
    )

    def __init__(self, port: str, baudrate: int):
        """Инициализирует статистику и текущее состояние дашборда.

        Args:
            port: Имя последовательного порта (например, ``/dev/ttyACM0``).
            baudrate: Скорость обмена с портом, бит/с.
        """
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
        self.gnss_module_name = DEFAULT_MODULE_NAME
        self.software_resets = 0
        self.last_data_time = 0.0


# Базовый класс окна дашборда
class BaseWindow:
    TITLE = "Window"
    BOX_TL, BOX_TR, BOX_BL, BOX_BR = "┌", "┐", "└", "┘"
    BOX_H, BOX_V = "─", "│"

    def __init__(self, win: 'curses.window', label_x: int = LABEL_X_DEFAULT, value_x: int = 14):
        """Сохраняет ссылку на curses-окно и настройки раскладки.

        Кэширует часто используемые методы окна для ускорения отрисовки.

        Args:
            win: Объект curses-окна, в котором рисуется панель.
            label_x: Колонка, с которой начинаются метки.
            value_x: Колонка, с которой выводятся значения.
        """
        self.win = win
        self._label_x = label_x
        self._value_x = value_x
        self._addstr = win.addnstr
        self._erase = win.erase
        self._noutrefresh = win.noutrefresh
        self._getmaxyx = win.getmaxyx
        self._cursor_y = CONTENT_START_Y

    def _reset_cursor(self) -> None:
        """Устанавливает внутренний курсор в начало контента окна."""
        self._cursor_y = CONTENT_START_Y

    def _draw_line(self, text: str, attr: int = 0, x: int = None) -> None:
        """Выводит строку текста и переводит внутренний курсор на строку ниже.

        Args:
            text: Текст строки.
            attr: Атрибуты curses для вывода.
            x: Колонка вывода; если None, используется ``label_x``.
        """
        draw_x = x if x is not None else self._label_x
        self._safe_addstr(self._cursor_y, draw_x, text, attr)
        self._cursor_y += 1

    def _draw_labeled(self, label: str, value: str, value_x: int = None, label_attr: int = curses.A_BOLD,
                      value_attr: int = 0) -> None:
        """Выводит строку вида «метка + значение» в одной строке окна.

        Args:
            label: Текст метки.
            value: Текст значения.
            value_x: Колонка вывода значения; если None, используется
                ``value_x`` экземпляра.
            label_attr: Атрибуты curses для метки.
            value_attr: Атрибуты curses для значения.
        """
        vx = value_x if value_x is not None else self._value_x
        self._safe_addstr(self._cursor_y, self._label_x, label, label_attr)
        self._safe_addstr(self._cursor_y, vx, value, value_attr)
        self._cursor_y += 1

    def _draw_box(self) -> None:
        """Рисует рамку окна и заголовок панели."""
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
        """Выводит текст с проверкой границ окна.

        Пропускает вывод, если координаты выходят за пределы окна,
        и игнорирует исключения curses.error.

        Args:
            y: Строка вывода.
            x: Колонка вывода.
            text: Текст для вывода.
            attr: Атрибуты curses.
        """
        try:
            max_y, max_x = self._getmaxyx()
            if 0 <= y < max_y and 0 <= x < max_x:
                self._addstr(y, x, text, max_x - x, attr)
        except curses.error:
            pass

    @staticmethod
    def _fmt(value, fmt: str = "") -> str:
        """Форматирует значение по заданному шаблону.

        Пустые значения (None или пустая строка) заменяются заполнителем
        ``PLACEHOLDER``.

        Args:
            value: Значение для форматирования.
            fmt: Строка формата Python (например, ``".2f"``).

        Returns:
            Отформатированная строка или заполнитель ``---``.
        """
        if value is None or value == "":
            return PLACEHOLDER
        return f"{value:{fmt}}" if fmt else str(value)

    def draw(self, data: GNSSData, stats: DashboardStats, info: SomeInfo) -> None:
        """Отрисовывает содержимое панели целиком.

        Рисует рамку, сбрасывает курсор и вызывает переопределяемый
        метод :meth:`_draw_content`.

        Args:
            data: Текущие данные GNSS.
            stats: Статистика и состояние дашборда.
            info: дополнительная информация
        """
        self._draw_box()
        self._reset_cursor()
        self._draw_content(data, stats, info)

    def _draw_content(self, data: GNSSData, stats: DashboardStats, info: SomeInfo) -> None:
        """Отрисовывает внутреннее содержимое панели; переопределяется подклассами.

        Args:
            data: Текущие данные GNSS.
            stats: Статистика и состояние дашборда.

        Raises:
            NotImplementedError: если подкласс не переопределил метод.
        """
        raise NotImplementedError

    def noutrefresh(self) -> None:
        """Помечает окно для отложенного обновления экрана (без doupdate)."""
        self._noutrefresh()

    def _draw_conditional(self, condition: bool, true_text: str, false_text: str,
                          true_attr: int = 0, false_attr: int = 0) -> None:
        """Выводит строку с разным текстом и атрибутами в зависимости от условия."""
        if condition:
            self._draw_line(true_text, true_attr)
        else:
            self._draw_line(false_text, false_attr)

    def _draw_labeled_conditional(self, label: str, value: str, condition: bool,
                                   true_attr: int = 0, false_attr: int = 0,
                                   value_x: int = None) -> None:
        """Выводит метку со значением, атрибут которого зависит от условия."""
        attr = true_attr if condition else false_attr
        self._draw_labeled(label, value, value_x=value_x, value_attr=attr)


class PositionWindow(BaseWindow):
    """Окно широты и долготы"""
    TITLE = "Positioning"

    def _draw_content(self, data: GNSSData, stats: DashboardStats, info: SomeInfo) -> None:
        """Выводит координаты, высоту и время UTC.

        Args:
            data: Текущие данные GNSS.
            stats: Статистика и состояние дашборда.
        """
        lat_str = f"{data.latitude:.6f}\u00B0" if data.latitude is not None else PLACEHOLDER
        lon_str = f"{data.longitude:.6f}\u00B0" if data.longitude is not None else PLACEHOLDER
        self._draw_labeled("Latitude: ", lat_str)
        self._draw_labeled("Longitude:", lon_str)
        self._draw_labeled("Altitude: ", f"{data.altitude:.1f} m" if data.altitude is not None else f"{PLACEHOLDER} m")
        self._draw_labeled("UTC Time: ", self._fmt(data.time))
        self._draw_labeled("UTC Date: ", self._fmt(data.date))


# Окно
class GNSSWindow(BaseWindow):
    """Окно параметров GNSS"""
    TITLE = "GNSS Parameters"

    def _draw_content(self, data: GNSSData, stats: DashboardStats, info: SomeInfo) -> None:
        """Выводит параметры созвездия, число спутников, HDOP и режим фикса.

        Args:
            data: Текущие данные GNSS.
            stats: Статистика и состояние дашборда.
        """
        self._draw_labeled("Constellation:", self._fmt(data.constellation))
        self._draw_labeled("Satellites:   ", self._fmt(data.satellites))
        hdop_str = f"{data.hdop:.1f}" if data.hdop is not None else PLACEHOLDER
        self._draw_labeled("HDOP:         ", hdop_str)
        # СТАЛО:
        fix = data.fix_mode or PLACEHOLDER
        self._draw_labeled_conditional(
            "Fix Mode:     ",
            fix,
            fix == "Not Valid",
            ATTR_ERROR_REVERSE,
            0
        )


class MotionWindow(BaseWindow):
    def _draw_content(self, data: GNSSData, stats: DashboardStats, info: SomeInfo) -> None:
        """Выбирает режим отображения: анализ точности или динамика движения.

        В стационарном режиме показывает метрики точности, иначе, скорость и курс.

        Args:
            data: Текущие данные GNSS.
            stats: Статистика и состояние дашборда.
        """
        if stats.is_stationary:
            self._draw_accuracy(stats.accuracy_tracker)
        else:
            self._draw_motion(data, stats)

    def _draw_motion(self, data: GNSSData, stats: DashboardStats) -> None:
        """Выводит скорость, курс и обратный отсчёт до режима точности.

        Args:
            data: Текущие данные GNSS.
            stats: Статистика и состояние дашборда.
        """
        draw_window_title(self.win, "Motion Dynamics")

        speed_kmh = data.speed * _TO_KMH if data.speed is not None else 0.0
        speed_str = format_speed(data.speed)
        self._draw_labeled("Speed:", speed_str)

        if data.course is not None:
            letter = GNSSData.compass_letter(data.course)
            course_str = f"{data.course:.1f}° ({letter})"
        else:
            if data.speed is None or speed_kmh < STATIONARY_SPEED_KMH:
                course_str = f"{PLACEHOLDER} (too slow)"
            elif data.fix_mode == "Not Valid":
                course_str = f"{PLACEHOLDER} (no fix)"
            else:
                course_str = PLACEHOLDER
        self._draw_labeled("Course:", course_str)

        if stats.stationary_timer > 0.0:
            remaining = STATIONARY_TIME_S - (now() - stats.stationary_timer)
            if 0 < remaining < STATIONARY_TIME_S:
                self._draw_line(f"Accuracy mode in: {int(remaining)}s", ATTR_DIM)

    def _draw_accuracy(self, tracker: AccuracyTracker) -> None:
        """Выводит метрики точности позиционирования.

        Показывает прогресс сбора точек, пока их меньше необходимого
        минимума, затем, рассчитанные метрики из
        :meth:`AccuracyTracker.get_metrics`.

        Args:
            tracker: Трекер точности с накопленной статистикой.
        """
        draw_window_title(self.win, "Accuracy Analysis", ATTR_OK)

        metrics = tracker.get_metrics()
        if not metrics:
            self._draw_line(f"Collecting data: {tracker.n}/{MIN_POINTS_FOR_ACCURACY} points")
            return

        self._draw_labeled("Points:       ", str(metrics['n']))
        self._draw_labeled("Valid Fix:    ", f"{metrics['valid_pct']:.1f}%")
        self._draw_labeled("Avg HDOP:     ", f"{metrics['avg_hdop']:.2f}")
        self._draw_line("-" * DIVIDER_LENGTH, ATTR_DIM)
        self._draw_labeled("2D Error(1\u03C3): ", f"+/-{metrics['err_2d_m']:.2f} m",
                           value_attr=ATTR_ERROR)
        self._draw_labeled("Drift:        ", f"~{metrics['drift_m']:.2f} m")

# человеко-читаемые строковые значения формата потока данных
_FMT_STREAM = "Unknwn", "CSV", "NMEA-0183"

class StatusWindow(BaseWindow):
    TITLE = "Connection Status"
    def _draw_content(self, data: GNSSData, stats: DashboardStats, info: SomeInfo) -> None:
        """Выводит состояние соединения, порт и статус логирования.

        Args:
            data: Текущие данные GNSS.
            stats: Статистика и состояние дашборда.
        """
        def _build_conn_str(nfo: SomeInfo) -> str:
            base = f"Status: CONNECTED ({_FMT_STREAM[nfo.stream_format]})"
            if 0 == nfo.mfr_code:
                return base
            return base + f" |{code_to_mfr_string(nfo.mfr_code)}"

        port_type = get_port_type(stats.port)
        self._draw_line(f"Port: {stats.port} ({port_type})")
        self._draw_line(f"Module: {stats.gnss_module_name}")
        self._draw_line(f"Speed: {stats.baudrate} (USB max)")

        # sf = info.stream_format
        self._draw_conditional(
            stats.disconnected,
            "Status: DISCONNECTED (reconnecting...)",
            _build_conn_str(info),
            ATTR_ERROR,
            ATTR_OK
        )

        self._draw_line(f"Valid lines: {stats.success}")
        self._draw_line(f"Errors: {stats.errors}")
        self._draw_line(f"Reconnects: {stats.reconnects}")
        self._draw_line(f"SW Resets: {stats.software_resets}")
        self._draw_line("-" * DIVIDER_LENGTH, ATTR_DIM)

        if stats.log_writer:
            lw = stats.log_writer
            # Проверяем реальную активность данных
            if lw.is_writing and stats.last_data_time > 0:
                time_since_data = now() - stats.last_data_time
                is_active = time_since_data < LOG_ACTIVITY_TIMEOUT_S
                self._draw_conditional(
                    is_active,
                    "Logging: ACTIVE",
                    "Logging: INACTIVE (no data)",
                    ATTR_OK,
                    ATTR_DIM
                )
            else:
                self._draw_line("Logging: INACTIVE", ATTR_DIM)
            self._draw_line(f"Lines written: {lw.lines_written}")


class Dashboard:
    """Координирует расположение окон, парсер и цикл отрисовки."""
    WINDOWS = (PositionWindow, GNSSWindow, MotionWindow, StatusWindow)
    RECONNECT_DELAY = RECONNECT_DELAY_S

    def __init__(self, stdscr: 'curses.window', parser: SerialParser):
        """Инициализирует дашборд: данные, статистику, окна и цикл отрисовки.

        Args:
            stdscr: Главное curses-окно терминала.
            parser: Парсер последовательного порта это источник данных.
        """
        self.stdscr = stdscr
        self.parser = parser
        self.data = GNSSData()
        self.some_info = SomeInfo()
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
        """Настраивает curses: скрытие курсора, неблокирующий ввод и цвета.

        Инициализирует цветовые пары и глобальные атрибуты ATTR_*.
        """
        curses.curs_set(CURSOR_VISIBLE)
        self.stdscr.nodelay(True)
        self.stdscr.timeout(UI_TIMEOUT_MS)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(COLOR_ERROR, curses.COLOR_RED, -1)
        curses.init_pair(COLOR_OK, curses.COLOR_GREEN, -1)
        # Инициализация цветовых атрибутов ПОСЛЕ curses.start_color()
        global ATTR_OK, ATTR_ERROR, ATTR_ERROR_REVERSE, ATTR_DIM
        ATTR_OK = curses.A_BOLD | curses.color_pair(COLOR_OK)
        ATTR_ERROR = curses.A_BOLD | curses.color_pair(COLOR_ERROR)
        ATTR_ERROR_REVERSE = curses.A_REVERSE | curses.color_pair(COLOR_ERROR)
        ATTR_DIM = curses.A_DIM

    def show_msg(self, y: int, x: int, msg: str, attr: int = 0) -> None:
        """Выводит текстовое сообщение в консоль (addstr: сначала строка y, потом колонка x)."""
        scr = self.stdscr
        try:
            scr.addstr(y, x, msg, attr)
        except curses.error:
            pass

    def _build_layout(self) -> None:
        """Рассчитывает размеры и создает окна, передавая им их внутренние координаты."""
        h, w = self.stdscr.getmaxyx()
        # Если окно слишком маленькое, то предупреждение
        if h < MIN_TERM_HEIGHT or w < MIN_TERM_WIDTH:
            self.stdscr.erase()
            msg_0 = f"Terminal too small! Minimum: {MIN_TERM_WIDTH}x{MIN_TERM_HEIGHT}. Press q, Q, ESCAPE to exit! Errors see in 'mcu_debug.log' file."
            try:
                self.show_msg(h // 2, max(0, (w - len(msg_0)) // 2), msg_0, curses.A_BOLD | curses.A_REVERSE)
            except curses.error:
                pass
            self.stdscr.noutrefresh()
            curses.doupdate()
            self.panels = []  # Очищаю панели, чтобы не рисовать их
            return

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
        """Обрабатывает нажатия клавиш пользователя.

        Returns:
            True, если пользователь запросил выход (q, Q, Escape),
            иначе False.
        """
        key = self._getch()
        if key in (ord('q'), ord('Q'), VK_ESCAPE):
            return True
        if key == curses.KEY_RESIZE:
            self._build_layout()
        return False

    def _handle_sys_message(self, raw_line: str) -> None:
        """Обрабатывает системные сообщения от микроконтроллера (MCU).

        Разбирает сообщение формата ``SYS_MSG:<тип>:<данные>`` и обновляет
        статистику: имя модуля, счётчики программных сбросов и ошибок.

        Args:
            raw_line: Строка с системным сообщением MCU.
        """
        start_idx = raw_line.find(SYS_MSG_PREFIX)
        if start_idx == -1:
            return

        msg_str = raw_line[start_idx:]
        parts = msg_str.split(":", 2)
        if len(parts) != 3:
            return

        try:
            msg_type = int(parts[1])
        except ValueError:
            return

        # Простая очистка: берём первое "слово" (отсекает \r\n и мусор)
        payload = parts[2].split()[0] if parts[2].split() else ""

        if msg_type == MCU_MSG_MODULE_DETECTED:
            self.stats.gnss_module_name = payload
        elif msg_type == MCU_MSG_SOFTWARE_RESET:
            log_msg(f"MCU: Software reset initiated ({payload})", sys.stderr)
            self.stats.success = 0
            self.stats.errors = 0
            # Инкремент счётчика программных сбросов
            self.stats.software_resets += 1
            self.log_writer.reset_count()
        elif msg_type == MCU_MSG_WATCHDOG_TRIGGERED:
            log_msg(f"MCU: Watchdog triggered ({payload})", sys.stderr)

    def _try_reconnect(self) -> None:
        """Пытается переподключиться к порту с учётом задержки между попытками.

        При успешном переподключении сбрасывает счётчики успехов, ошибок
        и записанных строк.
        """
        current_time = now()
        if current_time - self._last_reconnect_attempt < self.RECONNECT_DELAY:
            return
        self._last_reconnect_attempt = current_time

        if self.parser.reconnect():
            self.stats.disconnected = False
            self.stats.reconnects += 1
            self.stats.success = 0
            self.stats.errors = 0
            self.log_writer.reset_count()

    def _poll_serial(self) -> None:
        """Опрашивает последовательный порт и обновляет данные и статистику.

        Обрабатывает системные сообщения, логирует сырые строки, обновляет
        счётчики и управляет переходом в режим анализа точности при
        стационарном положении. При ошибках порта помечает соединение
        как разорванное.
        """
        try:
            data, is_error, raw_line = self.parser.poll()   # qqq_new
            # сохраняю формат потока данных
            si = self.some_info
            si.stream_format = self.parser.get_stream_format()
            # сохраняю строковое обозначение производителя GNSS приемника
            if DATA_STREAM_NMEA_0183 == si.mfr_code:
                si.mfr_code = self.parser.get_mfr_code()
            #
            if raw_line is not None:
                # Обработка системных сообщений или логирование строк (CSV-формат)
                if SYS_MSG_PREFIX in raw_line:
                    self._handle_sys_message(raw_line)
                else:
                    self.log_writer.write(raw_line, data)

            if data is not None:
                self.data = data
                self.stats.success += 1
                self.stats.last_data_time = now()

                speed_kmh = data.speed * _TO_KMH if data.speed is not None else 0.0
                current_time = now()

                if speed_kmh < STATIONARY_SPEED_KMH:
                    if not self.stats.is_stationary:
                        if self.stats.stationary_timer == 0.0:
                            self.stats.stationary_timer = current_time
                        elif current_time - self.stats.stationary_timer >= STATIONARY_TIME_S:
                            self.stats.is_stationary = True
                            self.stats.accuracy_tracker.reset()
                    if self.stats.is_stationary:
                        self.stats.accuracy_tracker.add_point(data)
                else:
                    reset_stationary_state(self.stats)
            elif is_error:
                self.stats.errors += 1
        except (serial.SerialException, OSError):
            self.stats.disconnected = True
            self.parser.close()
            self._last_reconnect_attempt = 0

    def _render(self) -> None:
        """Отрисовывает все панели и обновляет экран."""
        for panel in self.panels:
            panel.draw(self.data, self.stats, self.some_info)
            panel.noutrefresh()
        self._doupdate()

    def run(self) -> None:
        """Запускает главный цикл дашборда.

        Цикл обрабатывает ввод пользователя, опрос порта (или попытки
        переподключения при разрыве связи) и отрисовку до выхода
        по запросу пользователя.
        """
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


def main(stdscr: 'curses.window') -> None:
    """Точка входа дашборда, вызываемая внутри curses.wrapper.

    Перенаправляет stderr в файл ``mcu_debug.log``, создаёт парсер порта
    и дашборд, запускает главный цикл и корректно закрывает все ресурсы
    при выходе.

    Args:
        stdscr: Главное curses-окно терминала.
    """
    # Перенаправляю stderr в файл
    stderr_file = open('mcu_debug.log', 'a', encoding='utf-8')
    sys.stderr = stderr_file

    port, baud_rate = parse_args()
    parser = SerialParser(port, baudrate=baud_rate)
    dashboard = Dashboard(stdscr, parser)
    try:
        dashboard.run()
    finally:
        parser.close()
        dashboard.log_writer.close()
        stderr_file.close()  # Закрываем файл логов при выходе


if __name__ == "__main__":
    try:
        curses.wrapper(main)    # type: ignore[arg-type]
    except RuntimeError as e:
        log_msg(str(e), sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
    except curses.error as e:  # ИСПРАВЛЕНО: _curses.error -> curses.error
        log_msg(f"curses error: {e}", sys.stderr)
        log_msg("Make sure you run the script from an interactive terminal.", sys.stderr)
        sys.exit(1)