"""GNSS Data Logger - Запись навигационных данных с микроконтроллера в CSV-файл.

Считывает данные через последовательный порт (COM/ttyACM) и сохраняет в gnss_log.csv.
Требует pyserial: pip install pyserial

Конфигурация:
    COM_PORT - последовательный порт (напр., '/dev/ttyACM0')
    BAUD_RATE - скорость передачи (по умолчанию 38400)
    OUTPUT_FILE - имя выходного файла (по умолчанию 'gnss_log.csv')

Формат CSV: timestamp,valid,satellites,latitude,longitude,speed,course,altitude,time,date,constellation,fix_mode,hdop

Использование:
    1. Закройте IDE (освободите порт)
    2. Настройте COM_PORT и BAUD_RATE
    3. Запустите: python3 nmea_pc_logger.py
    4. Остановка: Ctrl+C

Автор: Roman Shevchik | Лицензия: GPL-3.0"""
import time
import serial
import traceback
from datetime import datetime

# Библиотека pyserial на ПК и драйверы операционной системы требуют указать скорость как обязательный аргумент при открытии порта.
# Для виртуального COM-порта (USB CDC) этот параметр полностью игнорируется контроллером USB.
# Реальная скорость ограничена только пропускной способностью USB-шины и буферами MicroPython!

# НАСТРОЙКИ
BAUD_RATE = 115200
_RECONNECT_DELAY = 2  # Cекунды между попытками переподключения
COM_PORT = "/dev/ttyACM0"
OUTPUT_FILE = 'gnss_log.csv'

# Заголовок CSV (пробелы после запятых убраны для парсинга)
_CSV_HEADER = "valid,satellites,latitude,longitude,speed,course,altitude,time,date,constellation,fix_mode,hdop\n"

def _write_csv_header(file_obj, header: str = _CSV_HEADER):
    """Записывает заголовок в CSV-файл и сбрасывает буфер."""
    file_obj.write(header)
    file_obj.flush()

def _open_serial(port: str, baud: int) -> None | serial.Serial:
    """Открывает порт с обработкой ошибок."""
    print(f"Открываю порт {port}...")
    try:
        ser = serial.Serial(port, baud, timeout=1)
        print(f"Порт открыт. Пишу в {OUTPUT_FILE}")
        return ser
    except serial.SerialException as e:
        print(f"Ошибка. Не удалось открыть порт: {e}")
        print(f"Совет. Проверьте подключение Pico и порт {port}")
        return None

serial_dev = None
packet_count = 0

try:
    serial_dev = _open_serial(COM_PORT, BAUD_RATE)
    if serial_dev is None:
        raise SystemExit("Не удалось открыть порт")

    print("Нажми Ctrl+C для остановки\n")
    print(f"Порт открыт. Пишу в {OUTPUT_FILE}")

    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
        if f.tell() == 0:
            _write_csv_header(f)

        while True:
            # Переподключение если порт отвалился
            if serial_dev is None or not serial_dev.is_open:
                print(f"Попытка переподключения к {COM_PORT}...")
                serial_dev = _open_serial(COM_PORT, BAUD_RATE)
                if serial_dev is None:
                    time.sleep(_RECONNECT_DELAY)
                    continue
                print("Порт восстановлен\n")
                packet_count = 0  # Сброс счётчика

            try:
                if serial_dev.in_waiting > 0:
                    line = serial_dev.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        packet_count += 1
                        # вывод с временем получения
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"[{timestamp}] {line}")
                        f.write(line + "\n")
                        f.flush()
            except OSError as e:
                # Обработка отвала порта
                print(f"\nПорт отвалился: {e}")
                print(f"Записано пакетов: {packet_count}")
                if serial_dev and serial_dev.is_open:
                    serial_dev.close()
                serial_dev = None
                time.sleep(_RECONNECT_DELAY)

except KeyboardInterrupt:
    print(f"\n\nСтатистика:")
    print(f"Записано пакетов: {packet_count}")
    print("\n\nОстановка. Данные сохранены в", OUTPUT_FILE)

except Exception as e:
    print(f"\nОшибка: {e}")
    traceback.print_exc()

finally:
    if serial_dev and serial_dev.is_open:
        serial_dev.close()
        print("Порт закрыт")