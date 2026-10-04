"""Общие утилиты, модели данных и serial-парсер для PC-инструментов GNSS.

Модуль не зависит от curses и используется дашбордом (gnss_dashboard.py),
логгером NMEA-потока (nmea_pc_logger.py) и другими инструментами.
"""

import os
import sys
import time
import math
import serial
import serial.tools.list_ports
from datetime import datetime
from time import monotonic
from typing import IO, Optional, Tuple

# парсер для разбора сырого потока NMEA-0183 от GNSS-приемников с USB выходом (поток по USB-CDC)
from light_nmea.nmea0183_parser import LightNMEA, CST_MASK_ALL
# единая точка преобразования индексов созвездий (CST_*) и режимов фикса (FIX_*) в имена
from light_nmea.conv_to_hrf import cst_index_to_name, fix_index_to_name, is_valid_fix_name

# ==============================================================================
# КОНСТАНТЫ
# ==============================================================================

# Типы потоков данных для парсинга
DATA_STREAM_UNKNOWN = 0
DATA_STREAM_CSV = 1
DATA_STREAM_NMEA_0183 = 2

# Кол-во запятых в потоке данных типа CSV.
# 12 полей распарсенных MicroPython-кодом, выполняющимся на плате с RP2040, ESP32 и т. п.
_COMMA_COUNT_CSV = 11

# Общие
PLACEHOLDER = "---"  # Заполнитель для отсутствующих значений
_TO_KMH = 1.0  # Коэффициент пересчёта скорости (м/с) в км/ч
CSV_FIELDS_COUNT = 12  # Кол-во полей в CSV-потоке данных

# Serial / USB
DEFAULT_BAUDRATE = 115200  # 38400
SERIAL_TIMEOUT_S = 0.05
RECONNECT_DELAY_S = 2.0
# Максимальный размер буфера строки от MCU (защита от разрастания при мусоре без '\n')
_MAX_BUFFER_SIZE = 4096

# Системные сообщения от MicroPython (MCU)
SYS_MSG_PREFIX = "SYS_MSG:"
MCU_MSG_MODULE_DETECTED = 1
MCU_MSG_SOFTWARE_RESET = 2
MCU_MSG_WATCHDOG_TRIGGERED = 3
#
DEFAULT_MODULE_NAME = "Unknown"

# Логирование
LOG_FILENAME = 'gnss_log.csv'
LOG_ENCODING = 'utf-8'
LOG_TIMESTAMP_FMT = "%H:%M:%S"
LOG_CSV_HEADER = "timestamp,valid,satellites,latitude,longitude,speed,course,altitude,time,date,constellation,fix_mode,hdop\n"

# Анализ точности
STATIONARY_SPEED_KMH = 2.0
STATIONARY_TIME_S = 33.3
M_PER_DEG_LAT = 111_320.0
MIN_POINTS_FOR_ACCURACY = 2

# Компас
FULL_CIRCLE_DEG = 360.0
COMPASS_DIVISIONS = 8
COMPASS_OFFSET_DEG = 22.5
COMPASS_SECTOR_DEG = 45.0

# ==============================================================================
# УТИЛИТЫ
# ==============================================================================


def now() -> float:
    """Возвращает текущее время в секундах (monotonic)."""
    return monotonic()


def log_msg(message: str, destination: IO[str]) -> None:
    """Выводит сообщение в destination с временной меткой в формате журнала."""
    timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    print(f"[{timestamp}] {message}", file=destination)


def get_port_type(port: str) -> str:
    """Определяет тип порта по имени устройства."""
    return "USB-UART" if "ttyACM" in port or "ttyUSB" in port else "Serial"


def format_speed(speed: Optional[float]) -> str:
    """Форматирует скорость в км/ч."""
    if speed is None:
        return f"{PLACEHOLDER} km/h"
    return f"{speed * _TO_KMH:.1f} km/h"


def _is_csv(line: str, csv_fields_count : int) -> bool:
    if not line:
        return False
    c0 = line[0]
    if c0 == '$' or c0 == '!':
        return False
    return line.count(',') == csv_fields_count - 1


def _is_nmea_0183(line: str) -> bool:
    n = len(line)
    if n < 5:
        return False

    c0 = line[0]
    if c0 != '$' and c0 != '!':
        return False

    # отбрасываю CRLF
    end = n
    if line[end - 1] == '\n':
        end -= 1
    if end > 1 and line[end - 1] == '\r':
        end -= 1

    body = line[1:end]
    if '\r' in body or '\n' in body:
        return False

    body_len = len(body)

    # контрольная сумма *HH
    star_pos = body.rfind('*')
    if star_pos >= 0:
        if star_pos + 2 >= body_len:
            return False
        h1 = body[star_pos + 1]
        h2 = body[star_pos + 2]
        if not (('0' <= h1 <= '9' or 'A' <= h1 <= 'F' or 'a' <= h1 <= 'f') and
                ('0' <= h2 <= '9' or 'A' <= h2 <= 'F' or 'a' <= h2 <= 'f')):
            return False
        if star_pos + 3 != body_len:
            return False
        data_end = star_pos
    else:
        data_end = body_len

    # идентификатор сентенции
    comma_pos = body[:data_end].find(',')
    id_end = comma_pos if comma_pos >= 0 else data_end

    if id_end < 4:
        return False

    for i in range(id_end):
        c = body[i]
        if not (('A' <= c <= 'Z') or ('a' <= c <= 'z') or ('0' <= c <= '9')):
            return False

    return True


def detect_format(line: str, csv_fields_count = CSV_FIELDS_COUNT) -> int:
    """Определяет фотмат данных в line.
        Возвращает DATA_STREAM_UNKNOWN если формат не распознан;
        Возвращает DATA_STREAM_CSV если формат CSV 12 полей данных;
        Возвращает DATA_STREAM_CSV если формат NMEA-0183;
    """
    if not line:
        return DATA_STREAM_UNKNOWN
    if _is_nmea_0183(line):
        return DATA_STREAM_NMEA_0183
    if _is_csv(line, csv_fields_count):
        return DATA_STREAM_CSV
    return DATA_STREAM_UNKNOWN


def format_nmea_datetime(value: bytes | bytearray, is_time: bool = True) -> str:
    """Форматирует время или дату из NMEA в человекочитаемый вид."""
    if not value:
        return ""

    val = value
    if isinstance(value, (bytes, bytearray)):
        val = value.decode('ascii')

    six = 6
    if is_time:
        if len(val) < six:
            return val
        return f"{val[0:2]}:{val[2:4]}:{val[4:]}"

    if len(val) != six:
        return val
    return f"{val[0:2]}.{val[2:4]}.20{val[4:six]}"


def get_mfr_code(sentence: str) -> int:
    """
    Возвращает 0 для стандартной сентенции NMEA-0183, без расширений производителей.
    Для проприетарной сентенции ($P...): 3 байта результата это ASCII-коды 3-буквенного
    кода производителя.
    Manufacturer (MFR) - это сокращение от Manufacturer (производитель).
    В индустрии, связанной с GNSS/NMEA так называют 3‑х буквенный код вендора: UBX, GRM, TNL и т.д.

    Пример: $PUBX,00 -> 0x554258 (UBX)
             $PGRMZ   -> 0x47524D (GRM)
             $PTNL    -> 0x544E4C (TNL)
    """
    n = len(sentence)
    if n < 5:
        return 0
    if sentence[0] != '$' or sentence[1] != 'P':
        return 0

    # позиция запятой или звёздочки - конец идентификатора
    comma_pos = sentence.find(',', 2)
    star_pos = sentence.find('*', 2)

    end = n
    if comma_pos != -1 and (star_pos == -1 or comma_pos < star_pos):
        end = comma_pos
    elif star_pos != -1:
        end = star_pos

    if end < 5:  # Нужно минимум $P + 3 для символа производителя
        return 0

    # Производитель это 3 символа начиная с позиции 2
    return (ord(sentence[2]) << 24) | (ord(sentence[3]) << 16) | (ord(sentence[4]) << 8)


def code_to_mfr_string(code: int) -> str:
    """Преобразует число, возвращенное get_mfr_code в строку краткого имени производителя расширения NMEA-0183:
    'UBX', 'GRM', 'TNL'."""
    if code == 0:
        return ""

    # Достаём три байта: старший, средний и младший
    b1 = (code >> 16) & 0xFF
    b2 = (code >> 8) & 0xFF
    b3 = code & 0xFF

    return chr(b1) + chr(b2) + chr(b3)


# Авто определение порта для связи с платой - поставщиком данных
def detect_port() -> str:
    """Автоматически определяет последовательный порт платы.

    Ищет устройства ttyACM* или ttyUSB* среди доступных COM-портов;
    при отсутствии проверяет стандартные пути устройств.

    Returns:
        Имя устройства последовательного порта.

    Raises:
        RuntimeError: если подходящий USB-UART порт не найден.
    """
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
            log_msg(f"Invalid baudrate: {sys.argv[2]}", sys.stderr)
            sys.exit(1)

    return port, baudrate


# ==============================================================================
# МОДЕЛЬ ДАННЫХ
# ==============================================================================
class GNSSData:
    """Одна строка данных от GNSS-приёмника."""
    __slots__ = (
        'valid', 'satellites', 'latitude', 'longitude',
        'speed', 'course', 'altitude', 'time', 'date',
        'constellation', 'fix_mode', 'hdop'
    )

    EXPECTED_FIELDS = CSV_FIELDS_COUNT

    def __init__(self):
        """Инициализирует пустой объект с данными GNSS.

        Все поля заполняются значениями по умолчанию (пустая строка или None),
        что соответствует отсутствию данных от приёмника.
        """
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
            raise ValueError(f"Expected {cls.EXPECTED_FIELDS} fields, got {len(parts)}")

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

    @classmethod
    def from_parser(cls, parser: LightNMEA) -> 'GNSSData':
        """Заполняет поля экземпляра класса информацией из полей экземпляра класса парсера"""
        obj = cls()
        obj.valid = parser.is_valid()
        obj.satellites = parser.satellites if parser.satellites else None
        obj.latitude = parser.latitude if parser.latitude else None
        obj.longitude = parser.longitude if parser.longitude else None
        obj.speed = parser.speed if parser.speed else None
        obj.course = parser.course if parser.course else None
        obj.altitude = parser.altitude if parser.altitude else None
        obj.time = format_nmea_datetime(value=parser.time, is_time=True)
        obj.date = format_nmea_datetime(value=parser.date, is_time=False)
        # Парсер хранит индекс созвездия (CST_*), приводим его к имени как в CSV-потоке
        obj.constellation = cst_index_to_name(parser.constellation)
        obj.fix_mode = fix_index_to_name(parser.fix_mode) if parser.fix_mode is not None else ""
        obj.hdop = parser.hdop if parser.hdop else None
        return obj

    def to_csv_line(self) -> str:
        """Сериализует поля объекта в CSV-строку (12 полей, без timestamp).

        Формат соответствует CSV-потоку платы (см. ``_to_csv`` в
        ``light_nmea/conv_to_hrf.py``): отсутствующие значения записываются
        пустой строкой, спутники ``'0'``, булев ``valid`` ``'1'``/``'0'``.
        Используется для записи распарсенного NMEA-0183 потока в CSV-лог.
        """
        def _fmt(value) -> str:
            if isinstance(value, bool):
                return "1" if value else "0"
            return "" if value is None else str(value)

        return ",".join((
            _fmt(self.valid),
            str(self.satellites) if self.satellites is not None else "0",
            _fmt(self.latitude),
            _fmt(self.longitude),
            _fmt(self.speed),
            _fmt(self.course),
            _fmt(self.altitude),
            self.time or "",
            self.date or "",
            self.constellation or "",
            self.fix_mode or "",
            _fmt(self.hdop),
        ))

    @staticmethod
    def compass_letter(course: float) -> str:
        """Преобразует курс (угол в градусах) в строковое обозначение стороны света."""
        dirs = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
        idx = int((course % FULL_CIRCLE_DEG + COMPASS_OFFSET_DEG) / COMPASS_SECTOR_DEG) % COMPASS_DIVISIONS
        return dirs[idx]


# ==============================================================================
# ЗАПИСЬ В CSV-ЛОГ
# ==============================================================================
class LogWriter:
    """Запись строки GNSS-данных от платы в CSV-файл с timestamp."""
    __slots__ = ('_file', '_filename', '_packet_count', '_is_writing')

    def __init__(self, filename: str = LOG_FILENAME):
        """Открывает CSV-файл лога и подготавливает счётчики.

        Args:
            filename: Имя файла лога (по умолчанию ``gnss_log.csv``).
        """
        self._filename = filename
        self._file = None
        self._packet_count = 0
        self._is_writing = False
        self._open()

    def _open(self) -> None:
        """Открывает файл лога в режиме дополнения.

        При создании пустого файла записывает в него заголовок CSV.
        При ошибке открытия выводит сообщение в stderr и переводит объект
        в состояние «не пишем».
        """
        try:
            # В append-режиме f.tell() не гарантирует корректную позицию,
            # поэтому размер файла проверяем ДО открытия.
            need_header = (not os.path.exists(self._filename)
                           or os.path.getsize(self._filename) == 0)
            self._file = open(self._filename, 'a', encoding=LOG_ENCODING)
            if need_header:
                self._file.write(LOG_CSV_HEADER)
                self._file.flush()
            self._is_writing = True
        except OSError as ex:
            log_msg(f"Error opening log {self._filename}: {ex}", sys.stderr)
            self._file = None
            self._is_writing = False

    @property
    def is_open(self) -> bool:
        """Возвращает True, если файл лога открыт и не закрыт."""
        return self._file is not None and not self._file.closed

    @property
    def is_writing(self) -> bool:
        """Возвращает True, если запись в лог активна.

        Запись считается активной, если файл открыт и не находится
        в состоянии ошибки.
        """
        return self._is_writing and self.is_open

    @property
    def lines_written(self) -> int:
        """Возвращает количество строк, записанных в лог.

        Returns:
            Число записанных строк с момента последнего сброса счётчика.
        """
        return self._packet_count

    def reset_count(self) -> None:
        """Сбрасывает счётчик записанных строк в ноль."""
        self._packet_count = 0

    def write(self, raw_line: str, data: Optional[GNSSData] = None) -> None:
        """Записывает строку данных GNSS в лог с UTC-временной меткой.

        Формат потока определяется через :func:`detect_format`:
        - CSV-поток пишется в лог напрямую;
        - NMEA-0183 пишется через объект :class:`GNSSData`, сериализуемый
          в CSV-строку методом ``to_csv_line``. Если данные отсутствуют
          (``data is None``), строка в лог не записывается, чтобы не
          нарушать CSV-формат лога.

        Args:
            raw_line: Строка данных (CSV или NMEA-0183) без завершающего
                перевода строки.
            data: Распарсенные данные GNSS, возвращённые
                :meth:`SerialParser.poll` (используются для NMEA-0183).

        При ошибке записи выводит сообщение в stderr и переводит объект
        в состояние «не пишем».
        """
        if self._file is None or self._file.closed:
            self._is_writing = False
            return
        try:
            # UTC time
            timestamp = time.strftime(LOG_TIMESTAMP_FMT, time.gmtime())
            # В лог пишем ТОЛЬКО строки в CSV-формате:
            #   * CSV-поток платы напрямую;
            #   * NMEA-0183 - через распарсенные данные (to_csv_line).
            # Сырые NMEA-предложения без полезных данных (GSV/GSA и пр.) и
            # нераспознанные строки (обрывки USB-потока, REPL-мусор) в лог
            # НЕ записываются, чтобы не нарушать CSV-контракт лог-файла.
            stream_format = detect_format(raw_line)
            if DATA_STREAM_CSV == stream_format:
                record = raw_line
            elif DATA_STREAM_NMEA_0183 == stream_format:
                if data is None:
                    # Сентенция NMEA распарсилась, но валидных данных нет
                    return
                record = data.to_csv_line()
            else:
                # Неизвестный формат, пропускаю
                return
            self._file.write(f"{timestamp},{record}\n")
            self._file.flush()
            self._packet_count += 1
            self._is_writing = True
        except OSError as ex:
            log_msg(f"Error writing to log: {ex}", sys.stderr)
            self._is_writing = False

    def close(self) -> None:
        """Закрывает файл лога, если он открыт."""
        self._is_writing = False
        if self._file is not None and not self._file.closed:
            try:
                self._file.close()
            except OSError:
                pass


# ==============================================================================
# АНАЛИЗ ТОЧНОСТИ
# ==============================================================================
class AccuracyTracker:
    """Расчёт точности GNSS по алгоритму Уэлфорда."""
    __slots__ = (
        'n', 'mean_lat', 'mean_lon', 'm2_lat', 'm2_lon',
        'min_lat', 'max_lat', 'min_lon', 'max_lon',
        'first_lat', 'first_lon', 'last_lat', 'last_lon',
        'valid_fix_count', 'hdop_sum', 'hdop_count'
    )

    def __init__(self):
        """Инициализирует трекер точности с нулевыми значениями статистики."""
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
        """Сбрасывает все накопленные данные трекера в начальное состояние."""
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
        """Добавляет точку с координатами в выборку и обновляет статистику.

        Точки без координат (latitude/longitude равны None) игнорируются.
        Обновляет скользящие средние по алгоритму Уэлфорда, минимумы/максимумы,
        а также счётчики валидных фиксов и значений HDOP.

        Args:
            data: Объект с данными GNSS-приёмника.
        """
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

        if is_valid_fix_name(data.fix_mode):
            self.valid_fix_count += 1
        if data.hdop is not None:
            self.hdop_sum += data.hdop
            self.hdop_count += 1

    def get_metrics(self) -> Optional[dict]:
        """Возвращает рассчитанные метрики точности позиционирования.

        Метрики рассчитываются только при наличии не менее
        ``MIN_POINTS_FOR_ACCURACY`` точек, иначе возвращается None.

        Returns:
            Словарь с метриками: количество точек (``n``), процент валидных
            фиксов (``valid_pct``), средний HDOP (``avg_hdop``), ошибка 2D
            (``err_2d_m``), дрейф (``drift_m``), СКО по широте и долготе
            (``std_lat``/``std_lon``) и границы координат (``min_lat``,
            ``max_lat``, ``min_lon``, ``max_lon``), либо None, если точек
            недостаточно.
        """
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
        """Инициализирует парсер последовательного порта.

        Открывает порт и создаёт внутренний парсер NMEA-0183 для разбора
        сырого потока от GNSS-приёмника.

        Args:
            port: Имя последовательного порта (например, ``/dev/ttyACM0``).
            baudrate: Скорость обмена с портом, бит/с.
            timeout: Таймаут чтения из порта, секунды.
        """
        self.port = port
        self.baudrate = baudrate
        self._timeout = timeout
        self._ser: Optional[serial.Serial] = None
        self._buffer = bytearray()
        self._read = None
        self._open()
        # тип потока данных
        self._stream_format = DATA_STREAM_UNKNOWN   # DATA_STREAM_CSV, DATA_STREAM_NMEA_0183
        # код производителя GNSS-приемника
        self._mfr_code = 0
        # создаю парсер для разбора сырого NMEA-0183 потока
        self._raw_parser = LightNMEA(trust_gga_fix=True, enable_diagnostics=True)
        self._raw_parser.set_cst_filter(CST_MASK_ALL)  # CST_MASK_MULTI

    def _open(self) -> bool:
        """Открывает последовательный порт и настраивает линии DTR/RTS.

        Переключение сигналов DTR/RTS используется для пробуждения
        интерфейса USB-CDC на контроллере RP2040. При ошибке открытия
        порта выводит сообщение в stderr.

        Returns:
            True, если порт успешно открыт, иначе False.
        """
        try:
            self._ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=self._timeout)
            self._read = self._ser.read
            #
            ser = self._ser
            ser.dtr = False
            ser.rts = False
            time.sleep(0.1)
            # для пробуждения USB-CDC на RP2040
            ser.dtr = True
            ser.rts = True
            #
            time.sleep(0.5)
            ser.reset_input_buffer()
            #
            return True
        except serial.SerialException as ex:
            log_msg(f"{ex}", sys.stderr)
            self._ser = None
            self._read = None
            return False

    def reconnect(self) -> bool:
        """Закрывает и заново открывает последовательный порт.

        Returns:
            True, если переподключение прошло успешно, иначе False.
        """
        self.close()
        return self._open()

    def get_stream_format(self) -> int:
        """Возвращает формат потока данных:
            * DATA_STREAM_UNKNOWN = 0
            * DATA_STREAM_CSV = 1
            * DATA_STREAM_NMEA_0183 = 2
        """
        return self._stream_format

    def get_mfr_code(self) -> int:
        """Возвращает код производителя GNSS приемника или 0 в случае
        если в потоке данных нет расширений формата сентенций."""
        return self._mfr_code

    @property
    def is_open(self) -> bool:
        """Возвращает True, если последовательный порт открыт."""
        return self._ser is not None and self._ser.is_open

    def close(self) -> None:
        """Закрывает последовательный порт и освобождает связанные ресурсы."""
        if self._ser is not None:
            if self._ser.is_open:
                try:
                    self._ser.close()
                except (serial.SerialException, OSError):
                    pass
            self._ser = None
            self._read = None

    def poll(self) -> Tuple[Optional[GNSSData], bool, Optional[str]]:
        """Читает данные из порта и возвращает распарсенную строку.

        Накапливает байты во внутреннем буфере до символа перевода строки,
        определяет формат данных (CSV или NMEA-0183) и преобразует их
        в объект :class:`GNSSData`. Системные сообщения MCU и нераспознанные
        строки возвращаются как ``raw_line`` без парсинга.

        Returns:
            Кортеж ``(data, is_error, raw_line)``:
            - ``data``: объект GNSSData при успешном разборе, иначе None;
            - ``is_error``: True при ошибке разбора строки (ValueError);
            - ``raw_line``: исходная строка для логирования, либо None.
        """
        if not self.is_open:
            return None, False, None

        in_waiting = self._ser.in_waiting
        if in_waiting:
            self._buffer.extend(self._read(in_waiting))

        newline_idx = self._buffer.find(b'\n')
        if newline_idx == -1:
            # Защита от разрастания буфера: нет '\n' в пределах лимита - это мусор, сбрасываем
            if len(self._buffer) > _MAX_BUFFER_SIZE:
                del self._buffer[:]
            return None, False, None

        line_bytes = self._buffer[:newline_idx]
        del self._buffer[:newline_idx + 1]

        line_str: str = line_bytes.decode('utf-8', errors='ignore').strip()

        if not line_str:
            return None, False, None

        try:
            if SYS_MSG_PREFIX in line_str:
                return None, False, line_str

            stream_format = detect_format(line_str)
            # запоминаю формат потока в поле класса
            self._stream_format = stream_format
            # запоминаю код производителя GNSS-приемника или 0
            self._mfr_code = get_mfr_code(line_str)

            if DATA_STREAM_UNKNOWN == stream_format:
                return None, False, line_str

            if DATA_STREAM_CSV == stream_format:
                return GNSSData.from_csv(line_str), False, line_str

            if DATA_STREAM_NMEA_0183 == stream_format:
                # разбор NMEA-0183 отдельным парсером
                raw_parser = self._raw_parser
                if raw_parser.parse_line(line_bytes): # разбор линии сырых данных
                    if raw_parser.has_coordinates() and raw_parser.hdop:
                        return GNSSData.from_parser(raw_parser), False, line_str
                # Если NMEA распарсился, но координат нет, то возвращаю None, но логирую строку
                return None, False, line_str

            # Страховка. Если формат не совпал ни с одним известным
            return None, False, line_str

        except ValueError:
            return None, True, line_str


class SomeInfo:
    """Дополнительная информация"""
    __slots__ = (
        'stream_format', 'mfr_code', 'reserved_0'
    )

    def __init__(self):
        self.stream_format = 0
        self.mfr_code = 0
        self.reserved_0 = 0