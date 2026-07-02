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

try:
    from micropython import const, native, viper
except ImportError:
    def const(x):
        return x
    def native(f):
        return f
    def viper(f):
        return f

# === константы ===
_MAX_PACKET_SIZE = const(120)  # Макс. длина NMEA-пакета
# _MSG_RMC: bytes = b"RMC"
# _MSG_GGA: bytes = b"GGA"
_NEGATIVE_DIRS: tuple = (b'S', b'W')
_INVALID_FIXES: tuple = (b'0', b'')
_MINUTES_TO_DEGREES: float = 1.0 / 60.0
_KNOTS_TO_KMH: float = 1.852
_MAX_COMMAS: int = const(14)
_SCAN_LINE_ERROR: tuple = (-1, -1)

RESET_ALL: int = const(0)
RESET_GGA: int = const(1)
RESET_RMC: int = const(2)


# ASCII-коды
_DOLLAR = const(36)
_STAR = const(42)
_COMMA = const(44)
#_CR = const(13)
_LF = const(10)
_MIN_PACKET_LEN = const(10)
_G_CHAR = const(71)  # 'G'
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
    star_idx: int = -1
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

    if star_idx == -1 or star_idx + 3 > line_len:
        return _SCAN_LINE_ERROR

    # проверка CRC с валидацией HEX
    h1 = line_bytes[star_idx + 1]
    h2 = line_bytes[star_idx + 2]

    # Первый nibble
    if 48 <= h1 <= 57:
        n1 = h1 - 48
    elif 65 <= h1 <= 70:
        n1 = h1 - 55
    elif 97 <= h1 <= 102:
        n1 = h1 - 87
    else:
        return _SCAN_LINE_ERROR

    # Второй nibble
    if 48 <= h2 <= 57:
        n2 = h2 - 48
    elif 65 <= h2 <= 70:
        n2 = h2 - 55
    elif 97 <= h2 <= 102:
        n2 = h2 - 87
    else:
        return _SCAN_LINE_ERROR

    if calc_cs != ((n1 << 4) | n2):
        return _SCAN_LINE_ERROR

    return star_idx, comma_count

@native
def _parse_degrees(raw_bytes: bytes, direction_bytes: bytes) -> float | None:
    """Парсинг координат: find() + memoryview."""
    if not raw_bytes:
        return None

    # Быстрый поиск точки '.' на уровне Си
    dot_idx = raw_bytes.find(b'.')
    # Создаю memoryview
    mv = memoryview(raw_bytes)
    try:
        # Если точка не найдена то последние 2 байта это угловые минуты
        if dot_idx == -1:
            degrees = float(mv[:-2])
            minutes = float(mv[-2:])
        else:
            degrees = float(mv[:dot_idx - 2])
            minutes = float(mv[dot_idx - 2:])
    except (ValueError, TypeError):
        return None

    decimal = degrees + (minutes * _MINUTES_TO_DEGREES)

    if direction_bytes in _NEGATIVE_DIRS:
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

class LightNMEA:
    """Парсер NMEA для MicroPython."""

    def __init__(self, trust_gga_fix: bool = False, enable_diagnostics: bool = False) -> None:
        self._parse_buffer = bytearray(_MAX_PACKET_SIZE)
        #
        self._trust_gga: bool = trust_gga_fix
        self._time_buffer: list = len(time.localtime()) * [0]
        self._comma_pos: bytearray = bytearray(_MAX_COMMAS)

        self.valid: bool = False
        self.latitude: float | None = None
        self.longitude: float | None = None
        self.speed: float | None = None
        self.course: float | None = None
        self.altitude: float | None = None
        self.satellites: int = 0
        # берется из RMC
        self.time: bytes = b""
        # берется из RMC
        self.date: bytes = b""
        self.constellation = CST_UNKNOWN
        # Горизонтальная точность. Чем меньше, тем лучше!
        # < 1.0 - отличная (< 2.5 м)
        # 1.0-2.0 - хорошая (2.5-5 м)
        # 2.0-5.0 - средняя (5-10 м)
        # 5.0 - плохая (> 10 м)
        self.hdop: float | None = None
        # Mode indicator из RMC - тип фикса
        self.fix_mode: int | None = None
        # Фильтр по созвездиям (битовая маска). По умолчанию - все разрешены.
        # ConSTellation bit mast
        self._cst_mask: int = CST_MASK_ALL
        #
        self._enable_diagnostics: bool = enable_diagnostics
        self.reject_crc: int = 0
        self.reject_unknown_cst: int = 0
        self.reject_filtered_cst: int = 0
        self.reject_unknown_msg: int = 0
        self.reject_too_short: int = 0

    def reset(self, scope: int = RESET_RMC) -> None:
        """Сброс полей."""
        if scope == RESET_GGA:
            self.altitude = None
            self.satellites = 0
            self.hdop = None
        elif scope == RESET_RMC:
            self.valid = False
            self.latitude = None
            self.longitude = None
            self.speed = None
            self.course = None
            self.time = b""
            self.date = b""
            self.fix_mode = FIX_NOT_VALID
        else:
            self.valid = False
            self.latitude = None
            self.longitude = None
            self.speed = None
            self.course = None
            self.altitude = None
            self.satellites = 0
            self.time = b""
            self.date = b""
            self.constellation = CST_UNKNOWN
            self.fix_mode = FIX_NOT_VALID
            self.hdop = None

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
    def parse_line(self, buf: bytes, start: int = 0, end: int = -1) -> bool:
        """Основной метод парсинга.
        :param buf: bytes, bytearray или memoryview
        :param start: начальный индекс
        :param end: конечный индекс (-1 = до конца)"""
        if end == -1:
            end = len(buf)

        packet_len = end - start
        if packet_len > _MAX_PACKET_SIZE:
            return False

        # Копируем в pre-allocated буфер (без аллокаций!)
        self._parse_buffer[:packet_len] = buf[start:end]
        line_bytes = self._parse_buffer

        star_idx, comma_count = _scan_line(line_bytes, self._comma_pos)
        if star_idx == -1:
            if self._enable_diagnostics:
                self.reject_crc += 1
            return False

        # Определяю созвездие (для любого типа сообщения)
        cst = _get_constellation(line_bytes[1], line_bytes[2])
        self.constellation = cst

        # Неизвестное созвездие - пропуск
        if cst == CST_UNKNOWN:
            if self._enable_diagnostics:
                self.reject_unknown_cst += 1
            return False
        # Проверка, разрешено ли созвездие в маске
        if not (self._cst_mask & (1 << cst)):
            if self._enable_diagnostics:
                self.reject_filtered_cst += 1
            return False

        # Recommended Minimum Specific GNSS Data
        if line_bytes[3] == _R_CHAR and line_bytes[4] == _M_CHAR and line_bytes[5] == _C_CHAR:  # 'R', 'M', 'C'
            if comma_count < 9:
                if self._enable_diagnostics:
                    self.reject_too_short += 1
                return False

            #   Парсинг Mode Indicator (всегда, если есть поле)
            if comma_count >= 11:
                mode_st = self._comma_pos[10] + 1
                mode_en = star_idx
                if mode_en > mode_st:
                    mode_byte = line_bytes[mode_st]
                    if _A_CHAR <= mode_byte <= _R_CHAR:
                        self.fix_mode = _FIX_MODE_TABLE[mode_byte - _A_CHAR]
                    else:
                        self.fix_mode = FIX_NOT_VALID
                else:
                    self.fix_mode = FIX_NOT_VALID
            else:
                self.fix_mode = FIX_NOT_VALID

            #   Поле 2: статус
            s_st = self._comma_pos[1] + 1
            s_en = self._comma_pos[2]

            if s_en - s_st == 1 and line_bytes[s_st] == _A_CHAR:
                self.valid = True

                #   Поле 1
                t_st = 7
                t_en = self._comma_pos[1]
                self.time = line_bytes[t_st:t_en]  # Теперь срез [7:13] (для времени)

                #   Поля 3-4: широта
                lat_st = self._comma_pos[2] + 1
                lat_en = self._comma_pos[3]
                lat_raw = line_bytes[lat_st:lat_en]

                dir_st = self._comma_pos[3] + 1
                dir_en = self._comma_pos[4]
                dir_raw = line_bytes[dir_st:dir_en]

                self.latitude = _parse_degrees(lat_raw, dir_raw)

                #   Поля 5-6: долгота
                lon_st = self._comma_pos[4] + 1
                lon_en = self._comma_pos[5]
                lon_raw = line_bytes[lon_st:lon_en]

                vdir_st = self._comma_pos[5] + 1
                vdir_en = self._comma_pos[6]
                vdir_raw = line_bytes[vdir_st:vdir_en]

                self.longitude = _parse_degrees(lon_raw, vdir_raw)

                #   Поле 7: скорость
                sp_st = self._comma_pos[6] + 1
                sp_en = self._comma_pos[7]
                speed_raw = line_bytes[sp_st:sp_en]
                self.speed = float(speed_raw) * _KNOTS_TO_KMH if speed_raw else None

                #   Поле 8: курс
                cr_st = self._comma_pos[7] + 1
                cr_en = self._comma_pos[8]
                course_raw = line_bytes[cr_st:cr_en]
                self.course = float(course_raw) if course_raw else None

                #   Поле 9: дата
                d_st = self._comma_pos[8] + 1
                d_en = self._comma_pos[9]
                self.date = line_bytes[d_st:d_en]

                return True
            else:
                self.reset(RESET_RMC)
                return True

        # Global Positioning System Fix Data (хотя GGA = GNSS Geo Altitude)
        elif line_bytes[3] == _G_CHAR and line_bytes[4] == _G_CHAR and line_bytes[5] == _A_CHAR:  # 'G', 'G', 'A'
            if comma_count < 9:
                if self._enable_diagnostics:
                    self.reject_too_short += 1
                return False

            #   Поле 6: качество фикса
            fix_st = self._comma_pos[5] + 1
            fix_en = self._comma_pos[6]

            if fix_en > fix_st and line_bytes[fix_st] != _0_CHAR: # не 0 и не пустое
                #   Поле 7: спутники
                sat_st = self._comma_pos[6] + 1
                sat_en = self._comma_pos[7]
                sats = line_bytes[sat_st:sat_en]
                self.satellites = int(sats) if sats else 0

                # Поле 7: HDOP
                hdop_st = self._comma_pos[7] + 1
                hdop_en = self._comma_pos[8]
                if hdop_en > hdop_st:
                    self.hdop = float(line_bytes[hdop_st:hdop_en])

                #   Поле 9: высота
                alt_st = self._comma_pos[8] + 1
                alt_en = self._comma_pos[9]
                alt_raw = line_bytes[alt_st:alt_en]
                self.altitude = float(alt_raw) if alt_raw else None

                if self._trust_gga:
                    self.valid = True
                    # Обновляю fix_mode на основе качества из GGA
                    # fix_quality в int
                    fix_quality = int(line_bytes[fix_st:fix_en])

                    # Прямая индексация по tuple
                    if fix_quality < len(_GGA_QUALITY_FIX_MODE):
                        self.fix_mode = _GGA_QUALITY_FIX_MODE[fix_quality]
                    # Если fix_quality > 5 - не трогаю self.fix_mode
                    # возможно, он уже установлен из RMC, или останется FIX_NOT_VALID
            else:
                if self._trust_gga:
                    self.valid = False
                self.reset(RESET_GGA)
            return True

        if self._enable_diagnostics:
            self.reject_unknown_msg += 1

        return False