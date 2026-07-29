"""Инструменты для управления GNSS модулем"""
# gnss_module_utils/__init__.py
import time
from machine import UART
from micropython import const

# ID типов GNSS-модулей
MODULE_UNKNOWN = const(0)
MODULE_UBLOX = const(1)
MODULE_QUECTEL = const(2)
MODULE_MEDIATEK = const(3)


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



def send_gnss_reset(reset_uart: UART, module_id: int, show_info: bool) -> None:
    """Отправляет команды сброса в GNSS-модуль."""
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
