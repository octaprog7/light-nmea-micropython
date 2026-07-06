# Changelog

Все значимые изменения в проекте light_nmea.

## [2.0.0] - 2026-07-07

### Добавлено
- Поддержка VTG (Track Made Good and Ground Speed)
- Поддержка GLL (Geographic Position)
- Поддержка VTG без Mode Indicator (старый формат NMEA)
- Диагностика по типам сообщений

### Изменено
- `parse_line` разбит на отдельные методы: `_parse_rmc`, `_parse_gga`, `_parse_vtg`, `_parse_gll`
- GLL при статусе 'V' сбрасывает только координаты, не трогая данные из других сообщений
- Один `memoryview` для всех полей GGA (вместо нескольких)

## [1.0.0] - 2026-07-06

### Добавлено
- Первоначальный релиз
- Поддержка RMC и GGA
- Multi-GNSS: GPS, GLONASS, BeiDou, Galileo, QZSS, NavIC
- RTK Fixed/Float
- Zero-allocation парсинг
- Фильтрация по созвездиям
- Диагностические счётчики