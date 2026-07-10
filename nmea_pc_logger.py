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
import serial
from datetime import datetime

# Библиотека pyserial на ПК и драйверы операционной системы требуют указать скорость как обязательный аргумент при открытии порта.
# Для виртуального COM-порта (USB CDC) этот параметр полностью игнорируется контроллером USB.
# Реальная скорость ограничена только пропускной способностью USB-шины и буферами MicroPython!

# НАСТРОЙКИ
BAUD_RATE = 115200
#
COM_PORT = "/dev/ttyACM0"
OUTPUT_FILE = 'gnss_log.csv'

# Заголовок CSV (пробелы после запятых убраны для парсинга)
_CSV_HEADER = "valid,satellites,latitude,longitude,speed,course,altitude,time,date,constellation,fix_mode,hdop\n"

def _write_csv_header(file_obj, header: str = _CSV_HEADER):
    """Записывает заголовок в CSV-файл и сбрасывает буфер."""
    file_obj.write(header)
    file_obj.flush()

print(f"Открываю порт {COM_PORT}...")
serial_dev = None
try:
    serial_dev = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
    print(f"Порт открыт. Пишу в {OUTPUT_FILE}")
    print("Нажми Ctrl+C для остановки\n")

    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
        if f.tell() == 0:
            _write_csv_header(f)

        while True:
            if serial_dev.in_waiting > 0:
                line = serial_dev.readline().decode('utf-8').strip()
                if line:
                    # вывод с временем получения
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp}] {line}")
                    f.write(line + "\n")
                    f.flush()

except KeyboardInterrupt:
    print("\n\nОстановка. Данные сохранены в", OUTPUT_FILE)
finally:
    serial_dev.close()