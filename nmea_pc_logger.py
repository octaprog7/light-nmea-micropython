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
import fcntl
import serial
import traceback
from time import monotonic
from datetime import datetime

# Библиотека pyserial на ПК и драйверы операционной системы требуют указать скорость как обязательный аргумент при открытии порта.
# Для виртуального COM-порта (USB CDC) этот параметр полностью игнорируется контроллером USB.
# Реальная скорость ограничена только пропускной способностью USB-шины и буферами MicroPython!

# НАСТРОЙКИ
BAUD_RATE = 115200
_RECONNECT_DELAY = 2  # Cекунды между попытками переподключения
COM_PORT = "/dev/ttyACM0"
OUTPUT_FILE = 'gnss_log.csv'

def _read_until_quiet(ser: serial.Serial, quiet_delay: float = 0.3) -> None:
    """Вычитывает баннер REPL, пока данные не перестанут поступать."""
    old_timeout = ser.timeout
    ser.timeout = 0.1
    last = monotonic()
    while monotonic() - last < quiet_delay:
        if ser.read(0x100):
            last = monotonic()
    ser.timeout = old_timeout

# Заголовок CSV (пробелы после запятых убраны для парсинга)
_CSV_HEADER = "valid,satellites,latitude,longitude,speed,course,altitude,time,date,constellation,fix_mode,hdop\n"

def _write_csv_header(file_obj, header: str = _CSV_HEADER):
    """Записывает заголовок в CSV-файл и сбрасывает буфер."""
    file_obj.write(header)
    file_obj.flush()

def _open_serial(port: str, baud: int) -> serial.Serial | None:
    """Открывает последовательный порт с обработкой ошибок.
    Возвращает объект serial.Serial либо None при неудаче.
    """
    print(f"Открываю порт {port}...")
    try:
        ser = serial.Serial(port, baud, timeout=1)
        # захват порта:
        #   BlockingIOError  -> порт уже занят другим процессом
        #   FileNotFoundError -> устройство исчезло между open() и flock()
        fcntl.flock(ser.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        #
        ser.dtr = True
        ser.rts = True
        # Если MicroPython код перехватывает KeyboardInterrupt, то этот метод пробуждения
        # USB-CDC стека MicroPython не сработает!
        ser.write(b'\x03')  # Ctrl+C прерывает выполнение main.py, вернуться в REPL
        time.sleep(0.5)
        ser.write(b'\x04')  # Ctrl+D - soft reset REPL
        ser.flush()
        time.sleep(1.5)  # перезагрузка и старт main.py (DTR уже поднят)
        _read_until_quiet(ser) # вычитывает REPL-заставку
        ser.reset_input_buffer()
        print(f"Порт открыт. Пишу в {OUTPUT_FILE}")
        return ser

    except serial.SerialException as ex:
        print(f"Ошибка. Не удалось открыть порт: {ex}")
        print(f"Совет. Проверьте подключение Pico и порт {port}")
        return None
    except BlockingIOError:
        print(f"Ошибка. Порт {port} уже занят другим процессом!")
        print(f"Совет. Проверьте: sudo fuser -v {port}")
        return None
    except FileNotFoundError:
        print(f"Ошибка. Устройство {port} исчезло при открытии (перезагрузка платы?)")
        print("Совет. Смотрите dmesg: dmesg -T | grep -iE 'usb|acm'")
        return None
    except OSError as ex:
        print(f"Ошибка. Системная ошибка при открытии порта: {ex}")
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