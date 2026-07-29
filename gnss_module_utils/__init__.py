"""Инструменты для управления GNSS модулем"""
# gnss_module_utils/__init__.py
import time
import struct
from machine import Pin, UART
from micropython import const
from collections import namedtuple

# ID типов GNSS-модулей
MODULE_UNKNOWN = const(0)
MODULE_UBLOX = const(1)
MODULE_QUECTEL = const(2)
MODULE_MEDIATEK = const(3)

# Структура со всеми нужными вам параметрами аппаратного состояния модуля u-blox
UbloxHardwareStatus = namedtuple('UbloxHardwareStatus', [
    'status_ok',      # True/False (все ли в порядке с ядром, не в SafeBoot ли оно)
    'noise_level',     # уровень шума на антенне (0-255)
    'agc_count',       # показатель автоматической регулировки усиления (0-8191)
    'antenna_status',  # 0=INIT, 1=DONTKNOW, 2=OK, 3=SHORT, 4=OPEN
    'antenna_power'    # 0=OFF, 1=ON, 2=DONTKNOW
])


def gnss_module_id_to_str(gnss_module_id: int) -> str:
    """Возвращает строковое название производителя GNSS-модуля по его ID."""
    if gnss_module_id == MODULE_UBLOX:
        return 'UBLOX'
    if gnss_module_id == MODULE_QUECTEL:
        return 'QUECTEL'
    if gnss_module_id == MODULE_MEDIATEK:
        return 'MEDIATEK'
    return 'Unknown'

def detect_gnss_module_type(in_uart: UART, timeout: int = 1500) -> int:
    """Определяет тип GNSS-модуля по ответу на запрос версии."""

    def _probe(command: bytes, search_patterns: tuple) -> bytearray | None:
        """Очищает буфер, шлет команду и построчно ищет маркеры ответа."""
        # Очистка входного буфера от потока NMEA
        while in_uart.any():
            in_uart.read(in_uart.any())
            time.sleep_ms(5)

        in_uart.write(command)

        start_time = time.ticks_ms()
        buffer = bytearray()

        # Чтение с таймаутом
        while time.ticks_diff(time.ticks_ms(), start_time) < timeout:
            if in_uart.any():
                chunk = in_uart.read(in_uart.any())
                if chunk:
                    buffer.extend(chunk)
                    # Проверяю маркеры
                    for pattern in search_patterns:
                        if pattern in buffer:
                            return buffer
            time.sleep_ms(10)
        return None

    # u-blox? (UBX-MON-VER)
    # Поиск заголовка ответа MON-VER (\xB5\x62\x0A\x04)
    resp = _probe(
        b'\xB5\x62\x0A\x04\x00\x00\x0E\x34',
        (b'\xB5\x62\x0A\x04', b'ROM', b'PROT', b'FWVER')
    )
    if resp:
        return MODULE_UBLOX

    # Quectel/MediaTek? (PMTK605)
    # Ищем подстроку PMTK705
    resp = _probe(b"$PMTK605*31\r\n", (b'$PMTK705',))
    if resp:
        # Проверяю варианты бренда
        if b'QUECTEL' in resp or b'Quectel' in resp:
            return MODULE_QUECTEL
        return MODULE_MEDIATEK

    return MODULE_UNKNOWN


def send_gnss_reset(reset_uart: UART, module_id: int, show_info: bool, reset_pin: Pin = None) -> None:
    """
    Отправляет команды сброса в GNSS-модуль.
    Выполняет аппаратный сброс через GPIO-пин (если передан) или программный сброс
    через UART-команды (если пин не указан).

    Args:
        reset_uart: экземпляр UART для связи с GNSS-модулем (machine.UART).
        module_id: Идентификатор типа модуля (MODULE_UBLOX, MODULE_QUECTEL, MODULE_MEDIATEK, MODULE_UNKNOWN).
        show_info: Если True, выводит отладочные сообщения в консоль.
        reset_pin: Экземпляр machine.Pin для аппаратного сброса модуля.
                   Если передан (не None), выполняется импульс сброса (ACTIVE LOW).
                   По умолчанию None — используется программный сброс через UART.
    """
    if reset_pin is not None:
        if show_info:
            print("GNSS: Performing hardware reset via GPIO pin...")

        reset_pin.value(0)  # Активный уровень LOW
        time.sleep_ms(200)
        reset_pin.value(1)  # Отпускаем пин

        if show_info:
            print("GNSS: Hardware reset complete.")
        return

    # Программный сброс через UART-команды
    if module_id == MODULE_UBLOX:
        commands = (b'\xB5\x62\x06\x04\x04\x00\xFF\xFF\x00\x00\x0C\x5D',)
    elif module_id in (MODULE_QUECTEL, MODULE_MEDIATEK):
        commands = (b"$PMTK104*37\r\n",)
    else:
        commands = (
            b'\xB5\x62\x06\x04\x04\x00\xFF\xFF\x00\x00\x0C\x5D',
            b"$PMTK104*37\r\n",
            b"$PGRMO,,2*75\r\n",
        )

    delay_ms = 50 if len(commands) > 1 else 100

    if show_info:
        print(f"GNSS: Sending {len(commands)} reset command(s) for ID {module_id}...")

    for cmd in commands:
        reset_uart.write(cmd)
        time.sleep_ms(delay_ms)

    if show_info:
        print("GNSS: Reset sent, waiting for reboot...")


_REQ = b'\xB5\x62\x0A\x38\x00\x00\x42\xD0'
_HDR = b'\xB5\x62\x0A\x38'

# Смещения для u-blox M10
_OFS_FLAGS = 11  # header(6) + payload_header(4) + blockId(1) + flags
_OFS_ANT_STAT = 12
_OFS_ANT_PWR = 13
_OFS_NOISE = 22  # header(6) + payload_header(4) + block_header(12) + noise
_OFS_AGC = 24
# Минимальный размер пакета для чтения noise/agc: 6 + 20 + 2 = 28 байт
_MIN_PKT_SIZE = 28

def get_ublox_hardware_status(in_uart: UART) -> tuple | None:
    """
    Запрашивает аппаратное состояние GNSS-модуля u-blox по пакету UBX-MON-RF.

    Отправляет запрос мониторинга RF-части приёмника и парсит ответ,
    извлекая данные о шуме антенны, усилении приёмника и состоянии антенны.
    Поддерживает модули на базе чипов u-blox M8/M9/M10.

    Args:
        in_uart: Объект UART для связи с GNSS-модулем (machine.UART).
                 Baudrate должен соответствовать настройкам модуля (обычно 38400).

    Returns…> if result:
        ...     ok, noise, agc, ant_st, ant_pw = result
        ...     print(f"Шум: {noise}, AGC: {agc}, Антенна: {ant_st}")
        ...     status_ok (status_ok) - Флаг успешного получения и валидности данных (bool).
        ...     ant_pw (antenna_power: int) - Показывает, подается ли питание на активную антенну (int). 0 - off; 1 - on; 2 - dont know;
        ... else:
        ...     print("Ошибка получения статуса")

    Note:
        Для компактных модулей M10, поля antenna_status
        и antenna_power часто возвращают значение 1 (dont know), так как
        производитель не разводит цепь мониторинга состояния антенны. Не является ошибкой!
    """

    while in_uart.any():
        in_uart.read(in_uart.any())
    in_uart.write(_REQ)

    start = time.ticks_ms()
    buf = bytearray()

    while time.ticks_diff(time.ticks_ms(), start) < 500:
        if in_uart.any():
            chunk = in_uart.read(in_uart.any())
            if chunk:
                buf.extend(chunk)
                idx = buf.find(_HDR)
                if idx != -1:
                    if len(buf) < idx + _MIN_PKT_SIZE:
                        continue

                    plen = struct.unpack_from('<H', buf, idx + 4)[0]
                    total = 6 + plen + 2

                    if len(buf) < idx + total:
                        continue

                    pkt = buf[idx:idx + total]

                    ck_a = ck_b = 0
                    for i in range(2, total - 2):
                        ck_a = (ck_a + pkt[i]) & 0xFF
                        ck_b = (ck_b + ck_a) & 0xFF

                    if ck_a != pkt[total - 2] or ck_b != pkt[total - 1]:
                        return None

                    flags, a_st, a_pw = struct.unpack_from('<BBB', pkt, _OFS_FLAGS)
                    _noise, _agc = struct.unpack_from('<HH', pkt, _OFS_NOISE)
                    return True, _noise, _agc, a_st, a_pw
        time.sleep_ms(5)
    return None