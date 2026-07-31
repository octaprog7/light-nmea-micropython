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
import time
from light_nmea.gnss_parser_base import IGNSSParser

try:
    from micropython import const
except ImportError:
    def const(x): return x

try:
    from micropython import native
except ImportError:
    def native(f): return f

try:
    from micropython import viper
except ImportError:
    def viper(f): return f


# постоянные
_MAX_PACKET_SIZE = const(120)  # Максимальная длина NMEA-пакета в ASCII
_NEGATIVE_DIRS = (b'S', b'W')
_INVALID_FIXES = (b'0', b'')
_MINUTES_TO_DEGREES = 1.0 / 60.0
_KNOTS_TO_KMH = 1.852
_MAX_COMMAS = const(14)
_NOT_FOUND = const(-1)  # Результат поиска, когда элемент не найден
_SCAN_LINE_ERROR = (-1, -1)

RESET_ALL = const(0)
RESET_GGA = const(1)
RESET_RMC = const(2)


# ASCII-коды
_DOLLAR = const(36)
_STAR = const(42)
_COMMA = const(44)
_LF = const(10)
_MIN_PACKET_LEN = const(10)
#
_G_CHAR = const(71)  # 'G'
_V_CHAR = const(86)  # 'V'
_L_CHAR = const(76)  # 'L'
_T_CHAR = const(84)  # 'T'
#
_T2_OFFSET = const(65)  # ord('A') - начало диапазона второго байта
_T2_MAX = const(81)     # ord('Q') - конец диапазона второго байта

# ASCII-коды букв для сравнения msg_type
_A_CHAR = const(65)   # 'A'
_B_CHAR = const(66)   # 'B'
_C_CHAR = const(67)   # 'C'
_D_CHAR = const(68)   # 'D'
_M_CHAR = const(77)   # 'M'
_R_CHAR = const(82)   # 'R'
# для сравнений status и direction
_S_CHAR = const(83)   # 'S' - South (для _NEGATIVE_DIRS)
_W_CHAR = const(87)   # 'W' - West  (для _NEGATIVE_DIRS)
_0_CHAR = const(48)   # '0' - для fix_quality
#
_I_CHAR = const(73)
_Q_CHAR = const(81)
_Z_CHAR = const(90)

# Constellation Constants
CST_UNKNOWN = const(0)
CST_GPS     = const(1)
CST_GLONASS = const(2)
CST_GALILEO = const(3)
CST_BEIDOU  = const(4)
CST_QZSS    = const(5)
CST_NAVIC   = const(6)
CST_MULTI   = const(7)

# Constellation Bitmasks
CST_MASK_GPS     = const(1 << CST_GPS)
CST_MASK_GLONASS = const(1 << CST_GLONASS)
CST_MASK_GALILEO = const(1 << CST_GALILEO)
CST_MASK_BEIDOU  = const(1 << CST_BEIDOU)
CST_MASK_QZSS    = const(1 << CST_QZSS)
CST_MASK_NAVIC   = const(1 << CST_NAVIC)
CST_MASK_MULTI   = const(1 << CST_MULTI)

# Маска "Разрешить всё" (по умолчанию)
CST_MASK_ALL = const(
    CST_MASK_GPS | CST_MASK_GLONASS | CST_MASK_GALILEO |
    CST_MASK_BEIDOU | CST_MASK_QZSS | CST_MASK_NAVIC | CST_MASK_MULTI
)

# Таблица: индекс = (ASCII второго байта - 65)
# Диапазон 65 ('A') - 81 ('Q') = 17 элементов
_CST_LOOKUP_BY_SECOND_BYTE = (
    CST_GALILEO,   # 65 'A'   GA - ЕС
    CST_BEIDOU,    # 66 'B'   GB/BD - Китай (старый формат)
    CST_UNKNOWN,   # 67 'C'   не используется)
    CST_BEIDOU,    # 68 'D'   BD - Китай (новый стандарт IALA)
    CST_UNKNOWN,   # 69 'E'   не используется
    CST_UNKNOWN,   # 70 'F'   не используется
    CST_UNKNOWN,   # 71 'G'   не используется
    CST_UNKNOWN,   # 72 'H'   не используется
    CST_NAVIC,     # 73 'I'   GI - Индия
    CST_UNKNOWN,   # 74 'J'   не используется
    CST_UNKNOWN,   # 75 'K'   не используется
    CST_GLONASS,   # 76 'L'   GL - Россия
    CST_UNKNOWN,   # 77 'M'   не используется
    CST_MULTI,     # 78 'N'   GN - Multi-GNSS
    CST_UNKNOWN,   # 79 'O'   не используется
    CST_GPS,       # 80 'P'   GP - США
    CST_QZSS,      # 81 'Q'   GQ - Япония
)

# Lookup-таблица для новых идентификаторов NMEA v4.10+
# Формат: (byte1, byte2, constellation)
# линейный поиск - для 3 элементов
_CST_LOOKUP_NMEA_4_10_PLUS = (
    (_B_CHAR, _D_CHAR, CST_BEIDOU),   # 'B', 'D' - BeiDou (новый стандарт)
    (_Q_CHAR, _Z_CHAR, CST_QZSS),     # 'Q', 'Z' - QZSS (Япония, новый)
    (_I_CHAR, _R_CHAR, CST_NAVIC),    # 'I', 'R' - NavIC (Индия, новый)
)

# Mode indicator из RMC - тип фикса
FIX_AUTONOMOUS = const(0)  # 'A';   с точностью до дома
FIX_DGPS       = const(1)  # 'D';   с точностью до квартиры
FIX_ESTIMATED  = const(2)  # 'E';   вы где-то рядом
FIX_NOT_VALID  = const(3)  # 'N';   Не(!) знаю, где вы
FIX_RTK_FIXED  = const(4)  # 'P';   Профессиональное геодезическое оборудование!
FIX_RTK_FLOAT  = const(5)  # 'R';   Почти точно, но уточняю!

# Lookup таблица: ASCII код -> Fix Mode
# Диапазон: 'A'(65) до 'R'(82) = 18 элементов
# Индекс = (ascii_code - 65)
_FIX_MODE_TABLE = (
    FIX_AUTONOMOUS,  # 65: 'A'
    FIX_NOT_VALID,   # 66: 'B' (не используется)
    FIX_NOT_VALID,   # 67: 'C'
    FIX_DGPS,        # 68: 'D'
    FIX_ESTIMATED,   # 69: 'E'
    FIX_NOT_VALID,   # 70: 'F'
    FIX_NOT_VALID,   # 71: 'G'
    FIX_NOT_VALID,   # 72: 'H'
    FIX_NOT_VALID,   # 73: 'I'
    FIX_NOT_VALID,   # 74: 'J'
    FIX_NOT_VALID,   # 75: 'K'
    FIX_NOT_VALID,   # 76: 'L'
    FIX_NOT_VALID,   # 77: 'M'
    FIX_NOT_VALID,   # 78: 'N'
    FIX_NOT_VALID,   # 79: 'O'
    FIX_RTK_FIXED,   # 80: 'P'
    FIX_NOT_VALID,   # 81: 'Q'
    FIX_RTK_FLOAT,   # 82: 'R'
)

# качество фикса из GGA (поле 6) в тип фикса
# Индекс = значение fix_quality (0-5)
_GGA_QUALITY_FIX_MODE = (
    FIX_NOT_VALID,    # 0: Fix not available or invalid
    FIX_AUTONOMOUS,   # 1: GPS SPS Mode, fix valid
    FIX_DGPS,         # 2: Differential GPS, SPS Mode
    FIX_NOT_VALID,    # 3: PPS Mode (редко)
    FIX_RTK_FIXED,    # 4: Real Time Kinematic (Fixed)
    FIX_RTK_FLOAT,    # 5: Real Time Kinematic (Float)
)

# === Модульные функции ===
@native
def _scan_line(line_bytes: bytes, comma_pos: bytearray) -> int | tuple:
    """Однопроходный сканер + CRC проверка. Возвращает (star_idx, comma_count) или _SCAN_LINE_ERROR."""
    line_len: int = len(line_bytes)
    if line_len < _MIN_PACKET_LEN or line_bytes[0] != _DOLLAR:
        return _SCAN_LINE_ERROR

    calc_cs: int = 0
    star_idx: int = _NOT_FOUND
    comma_count: int = 0

    for i in range(1, line_len):
        b = line_bytes[i]
        if b == _STAR:
            star_idx = i
            break
        if b == _COMMA:
            if comma_count < _MAX_COMMAS:
                comma_pos[comma_count] = i
                comma_count += 1
        calc_cs ^= b

    if star_idx == _NOT_FOUND or star_idx + 3 > line_len:
        return _SCAN_LINE_ERROR

    # проверка CRC с валидацией HEX
    h1 = line_bytes[star_idx + 1]
    h2 = line_bytes[star_idx + 2]

    # Проверка валидности (необязательно!)
    if not ((48 <= h1 <= 57) or (65 <= h1 <= 70) or (97 <= h1 <= 102)):
        return _SCAN_LINE_ERROR
    if not ((48 <= h2 <= 57) or (65 <= h2 <= 70) or (97 <= h2 <= 102)):
        return _SCAN_LINE_ERROR

    n1 = (h1 & 0x0F) + (9 * ((h1 >> 6) & 1))
    n2 = (h2 & 0x0F) + (9 * ((h2 >> 6) & 1))

    if calc_cs != ((n1 << 4) | n2):
        return _SCAN_LINE_ERROR

    return star_idx, comma_count

@native
def _parse_degrees(raw_bytes: bytes, lat_st: int, lat_en: int, dir_st: int, dir_en: int) -> float | None:
    """Парсинг координат. Работает напрямую с исходным буфером через индексы."""
    if lat_st >= lat_en:
        return None

    # Быстрый поиск точки с указанием диапазона (без создания среза!)
    dot_idx = raw_bytes.find(b'.', lat_st, lat_en)

    # Создаем memoryview ОДИН раз для всего буфера
    mv = memoryview(raw_bytes)

    try:
        if dot_idx == _NOT_FOUND:
            # Нет точки: формат DDMM (последние 2 байта - минуты)
            degrees = float(mv[lat_st:lat_en - 2])
            minutes = float(mv[lat_en - 2:lat_en])
        else:
            # Есть точка: формат DDMM.MMMM
            degrees = float(mv[lat_st:dot_idx - 2])
            minutes = float(mv[dot_idx - 2:lat_en])
    except (ValueError, TypeError):
        return None

    decimal = degrees + (minutes * _MINUTES_TO_DEGREES)

    # Проверяю направление напрямую по байту (без создания среза dir_raw!)
    if dir_st < dir_en:
        dir_byte = raw_bytes[dir_st]
        if dir_byte == _S_CHAR or dir_byte == _W_CHAR:
            decimal = -decimal

    return decimal


@native
def _get_constellation(talker_byte_1: int, talker_byte_2: int) -> int:
    """Определяет созвездие по байтам Talker ID.

    :return: Код созвездия в диапазоне [0, 7]:
             CST_UNKNOWN(0), CST_GPS(1), CST_GLONASS(2), CST_GALILEO(3),
             CST_BEIDOU(4), CST_QZSS(5), CST_NAVIC(6), CST_MULTI(7)"""
    if talker_byte_1 == _G_CHAR and _T2_OFFSET <= talker_byte_2 <= _T2_MAX:  # 'G' и валидный диапазон
        return _CST_LOOKUP_BY_SECOND_BYTE[talker_byte_2 - _T2_OFFSET]
    # Новые идентификаторы (NMEA v4.10+)
    for b1, b2, cst in _CST_LOOKUP_NMEA_4_10_PLUS:
        if talker_byte_1 == b1 and talker_byte_2 == b2:
            return cst
    # неизвестное созвездие спутников
    return CST_UNKNOWN


# === Класс парсера ===

class LightNMEA(IGNSSParser):
    """Парсер NMEA для MicroPython."""

    def __init__(self, trust_gga_fix: bool = False, enable_diagnostics: bool = False) -> None:
        # Внутренние буферы для парсинга
        self._parse_buffer = bytearray(_MAX_PACKET_SIZE)    # Буфер для копирования входных данных
        self._time_buffer: list = len(time.localtime()) * [0]  # Буфер для конвертации времени в tuple
        self._comma_pos: bytearray = bytearray(_MAX_COMMAS) # Позиции запятых в пакете (для быстрого доступа к полям)
        # Настройки парсера
        self._trust_gga: bool = trust_gga_fix   # Если True, использовать GGA для установки valid и fix_mode
        self._enable_diagnostics: bool = enable_diagnostics # Включить счётчики отклонённых пакетов
        # Основные данные навигации (обновляются из RMC и GGA)
        self.valid: bool = False    # Флаг фикса (True = есть координаты)
        self.latitude: float | None = None  # Широта в градусах (десятичные, +N/-S)
        self.longitude: float | None = None # Долгота в градусах (десятичные, +E/-W)
        self.speed: float | None = None # Скорость в км/ч (из RMC, поле 7)
        self.course: float | None = None    # Курс в градусах (0-360°, из RMC, поле 8)
        self.altitude: float | None = None  # Высота над уровнем моря в метрах (из GGA, поле 9)
        self.satellites: int = 0    # Количество используемых спутников (из GGA, поле 7)
        # Временные метки (из RMC)
        self.time: bytes = b""   # Время UTC в формате HHMMSS.SS (байты)
        # берется из RMC
        self.date: bytes = b""  # Дата в формате DDMMYY (байты)
        # Качество и тип фикса
        self.constellation = CST_UNKNOWN    # Созвездие спутников (CST_GPS, CST_GLONASS, ...)
        # Горизонтальная точность. Чем меньше, тем лучше!
        # < 1.0 - отличная (< 2.5 м)
        # 1.0-2.0 - хорошая (2.5-5 м)
        # 2.0-5.0 - средняя (5-10 м)
        # 5.0 - плохая (> 10 м)
        self.hdop: float | None = None
        # Тип фикса (из RMC mode indicator или GGA quality)
        # FIX_AUTONOMOUS, FIX_DGPS, FIX_RTK_FIXED
        self.fix_mode: int | None = None
        # Фильтр по созвездиям (битовая маска). По умолчанию - все разрешены.
        # ConSTellation bit mast
        # Пример: CST_MASK_GPS | CST_MASK_GLONASS
        self._cst_mask: int = CST_MASK_ALL
        # Диагностические счётчики (если enable_diagnostics=True)
        self.reject_crc: int = 0    # Пакетов отклонено: ошибка CRC
        self.reject_unknown_cst: int = 0    # Пакетов отклонено: неизвестное созвездие
        self.reject_filtered_cst: int = 0   # Пакетов отклонено: созвездие отфильтровано маской
        self.reject_unknown_msg: int = 0    # Пакетов отклонено: неизвестное сообщение (не RMC/GGA)
        self.reject_too_short: int = 0      # Пакетов отклонено: пакет слишком короткий

    def reset(self, scope: int = RESET_ALL) -> None:
        """Сброс полей навигации. Простой и объединенный."""
        # Сброс общий и для GGA, и для RMC, так как оба дают координаты
        self.valid = False
        self.latitude = None
        self.longitude = None
        self.fix_mode = FIX_NOT_VALID

        # Сброс данных, приходящих из пакета типа GGA
        if scope == RESET_GGA or scope == RESET_ALL:
            self.altitude = None
            self.satellites = 0
            self.hdop = None

        # Сброс данных, приходящих из пакета типа RMC
        if scope == RESET_RMC or scope == RESET_ALL:
            self.speed = None
            self.course = None
            self.time = b""
            self.date = b""

        # Общий сброс (только при RESET_ALL)
        if scope == RESET_ALL:
            self.constellation = CST_UNKNOWN

    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def has_navigation(self) -> bool:
        return (
                self.has_coordinates()
                and self.speed is not None
                and self.course is not None
        )

    def has_3d_fix(self) -> bool:
        return self.has_coordinates() and self.altitude is not None

    def set_cst_filter(self, cst_mask: int) -> None:
        """Устанавливает фильтр по созвездиям через битовую маску.

        :param cst_mask: Битовая маска разрешённых созвездий.
                         Используйте CST_MASK_ALL для приёма всех пакетов.

        Пример:
            parser.set_cst_filter(CST_MASK_GPS | CST_MASK_GALILEO)"""
        self._cst_mask = cst_mask

    def _update_time_buffer(self) -> bool:
        """Zero-Allocation перезапись буфера времени."""
        if len(self.date) < 6 or len(self.time) < 6:
            return False
        try:
            mv_date = memoryview(self.date)
            mv_time = memoryview(self.time)
            self._time_buffer[0] = 2000 + int(mv_date[4:6])
            self._time_buffer[1] = int(mv_date[2:4])
            self._time_buffer[2] = int(mv_date[0:2])
            self._time_buffer[3] = int(mv_time[0:2])
            self._time_buffer[4] = int(mv_time[2:4])
            self._time_buffer[5] = int(mv_time[4:6])
            self._time_buffer[6] = 0
            self._time_buffer[7] = 0
            return True
        except ValueError:
            return False

    def get_time(self) -> tuple | None:
        """Конвертирует дату/время в кортеж."""
        if not self._update_time_buffer():
            return None
        seconds = time.mktime(self._time_buffer) # type: ignore
        return time.localtime(seconds)

    def sync_hardware_rtc(self, rtc_object) -> None:
        """Синхронизация RTC."""
        if self._update_time_buffer():
            rtc_object.datetime((
                self._time_buffer[0], self._time_buffer[1], self._time_buffer[2], 0,
                self._time_buffer[3], self._time_buffer[4], self._time_buffer[5], 0
            ))

    @native
    def _parse_coordinates(self, line_bytes: bytearray, start_idx: int) -> bool:
        """Универсальный парсер координат из сообщений типа RMC, GGA, GLL.
        Принимает только начальный индекс поля lat."""
        # Широта (поле start_idx)
        lat = _parse_degrees(
            line_bytes,
            self._comma_pos[start_idx] + 1, self._comma_pos[start_idx + 1],
            self._comma_pos[start_idx + 1] + 1, self._comma_pos[start_idx + 2]
        )
        if lat is None:
            return False
        self.latitude = lat

        # Долгота (поле start_idx + 2)
        lon = _parse_degrees(
            line_bytes,
            self._comma_pos[start_idx + 2] + 1, self._comma_pos[start_idx + 3],
            self._comma_pos[start_idx + 3] + 1, self._comma_pos[start_idx + 4]
        )
        if lon is None:
            return False
        self.longitude = lon

        return True

    @native
    def _parse_rmc(self, line_bytes: bytearray, star_idx: int, comma_count: int) -> bool:
        """Парсинг RMC (Recommended Minimum Specific GNSS Data)."""
        if comma_count < 9:
            if self._enable_diagnostics:
                self.reject_too_short += 1
            return False

        # Mode Indicator - поле 12 (NMEA v3.0+)
        self.fix_mode = FIX_NOT_VALID

        if comma_count >= 12:
            mode_st = self._comma_pos[11] + 1  # Начало поля 12
            mode_en = self._comma_pos[12] if comma_count > 12 else star_idx

            if mode_en > mode_st:
                mode_byte = line_bytes[mode_st]
                if _A_CHAR <= mode_byte <= _R_CHAR:
                    self.fix_mode = _FIX_MODE_TABLE[mode_byte - _A_CHAR]

        # Статус (поле 2)
        s_st = self._comma_pos[1] + 1
        if line_bytes[s_st] != _A_CHAR:
            self.reset(RESET_RMC)
            return True

        self.valid = True

        # Время (поле 1)
        self.time = line_bytes[7:self._comma_pos[1]]

        # парсинг координат (RMC: start_idx = 2)
        if not self._parse_coordinates(line_bytes, 2):
            self.reset(RESET_RMC)
            return False

        # Скорость и курс (один memoryview)
        rmc_mv = memoryview(line_bytes)

        sp_st, sp_en = self._comma_pos[6] + 1, self._comma_pos[7]
        self.speed = float(rmc_mv[sp_st:sp_en]) * _KNOTS_TO_KMH if sp_en > sp_st else None

        cr_st, cr_en = self._comma_pos[7] + 1, self._comma_pos[8]
        self.course = float(rmc_mv[cr_st:cr_en]) if cr_en > cr_st else None

        # Дата (поле 9)
        self.date = line_bytes[self._comma_pos[8] + 1:self._comma_pos[9]]
        return True

    @native
    def _parse_gga(self, line_bytes: bytearray, comma_count: int) -> bool:
        """Парсинг GGA (GNSS Fix Data)."""
        if comma_count < 9:
            if self._enable_diagnostics:
                self.reject_too_short += 1
            return False

        gga_mv = memoryview(line_bytes)
        fix_st = self._comma_pos[5] + 1
        fix_en = self._comma_pos[6]

        # Проверяю качество фикса (не '0' и не пусто)
        if fix_en > fix_st and line_bytes[fix_st] != _0_CHAR:
            fix_quality = int(gga_mv[fix_st:fix_en])

            # Обновляю режим фикса из таблицы GGA
            if fix_quality < len(_GGA_QUALITY_FIX_MODE):
                self.fix_mode = _GGA_QUALITY_FIX_MODE[fix_quality]

            # парсинг координат (GGA: start_idx = 1)
            if not self._parse_coordinates(line_bytes, 1):
                self.reset(RESET_GGA)
                return False

            # Спутники (поле 7)
            sat_st, sat_en = self._comma_pos[6] + 1, self._comma_pos[7]
            self.satellites = int(gga_mv[sat_st:sat_en]) if sat_en > sat_st else 0

            # HDOP (поле 8)
            hdop_st, hdop_en = self._comma_pos[7] + 1, self._comma_pos[8]
            self.hdop = float(gga_mv[hdop_st:hdop_en]) if hdop_en > hdop_st else None

            # Высота (поле 9)
            alt_st, alt_en = self._comma_pos[8] + 1, self._comma_pos[9]
            self.altitude = float(gga_mv[alt_st:alt_en]) if alt_en > alt_st else None

            # Если доверяю GGA, он становится основным источником valid
            if self._trust_gga:
                self.valid = True
        else:
            # Нет фикса (fix_quality == 0)
            if self._trust_gga:
                self.valid = False
            self.reset(RESET_GGA)

        return True

    @native
    def _parse_vtg(self, line_bytes: bytearray, comma_count: int) -> bool:
        """Парсинг VTG (Track Made Good and Ground Speed)."""
        if comma_count < 8:
            if self._enable_diagnostics:
                self.reject_too_short += 1
            return False

        vtg_mv = memoryview(line_bytes)

        # Курс
        cr_st, cr_en = self._comma_pos[0] + 1, self._comma_pos[1]
        if cr_en > cr_st:
            self.course = float(vtg_mv[cr_st:cr_en])

        # Скорость в узлах
        sp_st, sp_en = self._comma_pos[4] + 1, self._comma_pos[5]
        if sp_en > sp_st:
            self.speed = float(vtg_mv[sp_st:sp_en]) * _KNOTS_TO_KMH

        # Скорость в км/ч (перезаписывает, если есть)
        sp_kmh_st, sp_kmh_en = self._comma_pos[6] + 1, self._comma_pos[7]
        if sp_kmh_en > sp_kmh_st:
            self.speed = float(vtg_mv[sp_kmh_st:sp_kmh_en])

        return True

    @native
    def _parse_gll(self, line_bytes: bytearray, comma_count: int) -> bool:
        """Парсинг GLL (Geographic Position)."""
        if comma_count < 6:
            if self._enable_diagnostics:
                self.reject_too_short += 1
            return False

        s_st = self._comma_pos[5] + 1
        s_en = self._comma_pos[6]

        if s_en > s_st and line_bytes[s_st] == _A_CHAR:
            self.valid = True
            self.time = line_bytes[self._comma_pos[4] + 1:self._comma_pos[5]]

            # парсинг координат (GLL: start_idx = 0)
            if not self._parse_coordinates(line_bytes, 0):
                self.reset(RESET_RMC)
                return False
            return True
        else:
            # Статус не 'A' - сбрасываю навигационные данные
            self.reset(RESET_RMC)
            return True


# fix_mode обновляется только из RMC и GGA
# VTG содержит данные только скорости и курса
# GLL содержит данные только координат и времени

    @native
    def parse_line(self, buf: bytes, start: int = 0, end: int = _NOT_FOUND) -> bool:
        """Основной метод парсинга. Диспетчер сообщений."""
        if end == _NOT_FOUND:
            end = len(buf)

        packet_len = end - start
        if packet_len > _MAX_PACKET_SIZE:
            return False

        # Копирую в pre-allocated буфер
        self._parse_buffer[:packet_len] = buf[start:end]
        line_bytes = self._parse_buffer

        star_idx, comma_count = _scan_line(line_bytes, self._comma_pos)
        if star_idx == _NOT_FOUND:
            if self._enable_diagnostics:
                self.reject_crc += 1
            return False

        # Определяю созвездие
        cst = _get_constellation(line_bytes[1], line_bytes[2])
        self.constellation = cst

        if cst == CST_UNKNOWN:
            if self._enable_diagnostics:
                self.reject_unknown_cst += 1
            return False

        if not (self._cst_mask & (1 << cst)):
            if self._enable_diagnostics:
                self.reject_filtered_cst += 1
            return False

        # Диспетчер по типам сообщений
        b3, b4, b5 = line_bytes[3], line_bytes[4], line_bytes[5]
        if b3 == _R_CHAR and b4 == _M_CHAR and b5 == _C_CHAR:   # RMC
            return self._parse_rmc(line_bytes, star_idx, comma_count)
        elif b3 == _G_CHAR and b4 == _G_CHAR and b5 == _A_CHAR: # GGA
            return self._parse_gga(line_bytes, comma_count)
        elif b3 == _V_CHAR and b4 == _T_CHAR and b5 == _G_CHAR: # VTG
            return self._parse_vtg(line_bytes, comma_count)
        elif b3 == _G_CHAR and b4 == _L_CHAR and b5 == _L_CHAR: # GLL
            return self._parse_gll(line_bytes, comma_count)
        if self._enable_diagnostics:
            self.reject_unknown_msg += 1
        return False

    def is_valid(self) -> bool:
        """Реализация интерфейса IGNSSParser."""
        return self.valid

    def get_constellation(self) -> int:
        """Реализация интерфейса IGNSSParser."""
        return self.constellation if self.constellation is not None else CST_UNKNOWN