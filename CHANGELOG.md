# Changelog

All notable changes to the light_nmea project will be documented in this file.

## - 2026-09-22

### Fixed
- **Parser. Robustness against malformed numeric fields:** Added module-level helpers `_to_float()` and `_to_int()` with `@native` and `try/except (ValueError, TypeError)`. Numeric conversions in `_parse_rmc` (speed, course), `_parse_gga` (fix quality, satellites, HDOP, altitude) and `_parse_vtg` (course, speed knots/km/h) are now protected — a packet with a non-numeric field (e.g. `abc` as speed) and a valid CRC previously raised `ValueError`, aborting the calling main loop. A corrupted field now yields `None`/`0` while the rest of the packet is still parsed.
- **Parser. Fix-mode tables aligned with NMEA-0183 (gpsd reference):**
  - `_FIX_MODE_TABLE` (RMC field 12, FAA Mode Indicator): `'F'` → `FIX_RTK_FLOAT`, `'R'` → `FIX_RTK_FIXED` (RTK Integer) — the letters were swapped; `'P'` (Precise) documented as ≈ `FIX_RTK_FIXED`.
  - `_GGA_QUALITY_FIX_MODE` (GGA field 6): extended from 0–5 to 0–8 — added `6` (Estimated → `FIX_ESTIMATED`), `7` (Manual input → `FIX_NOT_VALID`), `8` (Simulation → `FIX_NOT_VALID`); `3` (PPS) now maps to `FIX_AUTONOMOUS` instead of `FIX_NOT_VALID`.
- **Dashboard. `show_msg()`:** Fixed swapped `y`/`x` arguments in `curses.addstr()` — the "Terminal too small" warning is now drawn in the correct position.
- **Dashboard. Accuracy analysis:** `AccuracyTracker` now counts only real GNSS fixes (`_VALID_FIX_MODES`: Autonomous, DGPS, RTK Fixed, RTK Float) — `Unknown` and `Estimated` are no longer counted as valid, so the valid-fix percentage is honest.
- **Dashboard. Serial buffer:** Added `_MAX_BUFFER_SIZE` (4096) limit in `SerialParser.poll()` — a byte stream without `\n` (UART garbage) can no longer grow the buffer unboundedly.

### Changed
- **Parser.** Redundant `memoryview` allocations removed in `_parse_rmc` and `_parse_vtg` — slices are now created once per field via the `_to_float`/`_to_int` helpers.
- **Parser.** Comments for `FIX_*` constants updated to match the standard letter assignments (`'R'`/`'P'` → `FIX_RTK_FIXED`, `'F'` → `FIX_RTK_FLOAT`).

### Added
- **Test packets generator (`nav_gen.py`):** 7 new packets (indices 24–30) with invalid numeric fields and valid checksums — RMC speed `xyz`, RMC course `abc`, GGA HDOP `abc`, GGA satellites `xx`, GGA altitude `15x.3`, VTG km/h `4.72x`, VTG course `08x.4`. They pass the CRC check, reach the numeric conversion and exercise the new exception protection. Existing packet indices used by tests are unaffected.
- **Tests (`test_conv_to_hrf.py`):** updated to the current 12-field CSV format and `_fmt_dt` output (`HH:MM:SS`, `DD.MM.20YY`); fixed `NameError` from unimported `to_txt`/`to_compact`; extended `test_csv_format` with a full index-level CSV contract check.

### Performance (measured 2026-09-22)
- **CPython:** 115,262 pkt/s — **3.4x** faster than micropyGPS.
- **MicroPython RP2040 @ 133 MHz (interpreter mode, no @native support):** 486 pkt/s — **22.5x** faster than micropyGPS.
- **0 bytes** RAM allocated during parsing — confirms the zero-allocation hot path (`try/except` does not allocate on the happy path).

## - 2026-09-09

### Added
- **Dashboard. Monopoly port locking:** Implemented interface locking in `_open_serial` to prevent joint device access conflicts.
- **Dashboard. Logging to curses console:** Added `show_msg` helper function for correct string rendering.

### Fixed and optimized (MicroPython code)
- **Deferred (lazy) memory allocation:** Creation of `memoryview` objects inside `_parse_rmc` and `_parse_vtg` parsers now happens strictly on demand, reducing the load on the hot processing loop.
- **Buffer copying:** Optimized data copying mechanism in `parse_line` using high-performance `memoryview`.
- **String scanner:** Passed an explicit `packet_len` parameter to the `_scan_line` method for precise packet boundary control.
- **Data type optimization:** Internal time buffer `_time_buffer` migrated from a standard Python list (`list`) to a fast, fixed-size array (`array`).
- **MicroPython code cleanup:** Removed an unused import of the `@viper` decorator for absolute RAM purity.
- **USB-CDC stack and initialization stabilization:**
  - Redesigned USB-CDC wakeup logic on the controller side (trigger changed from `0x03` to `0x04`).
  - Added correct initialization waiting sequence for `/dev/ttyXXX` devices on Linux hosts during board connection.
  - Fixed USB-CDC auto-start: added mandatory DTR/RTS lines reset sequence before raising them again.
- **Time and RTC modules:** Fixed a bug in the `get_time` method — added explicit `tuple()` call for compatibility with `time.mktime`. Applied cosmetic refactoring to the hardware real-time clock synchronization module (`sync_hardware_rtc`).

## - 2026-08-09

### Added
- Lookup table `_HEX_VALUE` for fast CRC verification.
- 24-bit message type identifiers (`_MSG_ID_RMC`, `_MSG_ID_GGA`, `_MSG_ID_VTG`, `_MSG_ID_GLL`).
- 16-bit Talker ID constants for NMEA v4.10+ (`_TALKER_ID_BD`, `_TALKER_ID_QZ`, `_TALKER_ID_IR`).

### Technical details
- All `@native` and `@viper` decorators are optional — the code runs in a pure MicroPython interpreter without any loss of functionality.

### Changed
- **`parse_line()`**: fast filtering by constellation and message type **before** copying to buffer — dropping junk packets.
- **`_scan_line()`**: single-pass scanner with early exit upon finding `*`, CRC verification via HEX table.
- **`_get_constellation()`**: constellation determination via lookup table instead of a comparison loop.
- **`_parse_rmc()`**: localized `self._comma_pos` into a local variable `cp`, removed repetitive attribute lookups.
- **`_parse_gga()`**: localized trans...

### Performance
- **MicroPython (RP2040 @ 133MHz)**: 494 pkt/s at 176 bytes RAM per packet.
- **CPython (3.9 GHz)**: 109,453 pkt/s.
- **22.6x faster** than micropyGPS on RP2040.
- **2.8x faster** than micropyGPS on CPython.
- **1.4x faster** than adafruit_gps on CPython.
- **1.3x faster** than pynmea2 on CPython.
- **2.1x faster** than pynmeagps on CPython.
- **1.7x faster** than vihasnaps on CPython.
- Specific efficiency: **27.93 packets/MHz** (vs 20.18 for adafruit_gps).
- 100% successfully processed packets in tests (333,333 out of 333,333).

## - 2026-07-30

### Added
- `get_ublox_hardware_status()` function for monitoring the RF part of u-blox M10.
- Support for hardware GNSS module reset via GPIO pin (`reset_pin`).
- `PositionWindow`, `GNSSWindow`, `MotionWindow` windows with accuracy analysis based on Welford's algorithm.
- GNSS data logging to `gnss_log.csv` with timestamp.
- Processing of system messages `SYS_MSG` from the MicroPython board.
- Check for minimum terminal size for the curses dashboard.
- Protection against port interception by other programs (Thonny, screen).

### Changed
- Moved GNSS utilities into a separate package `gnss_module_utils`.
- Redirected `stderr` to `mcu_debug.log`.

## - 2026-07-23

### Added
- Base interface `IGNSSParser` for unifying the API of all GNSS parsers.
- Interface methods: `is_valid()`, `get_constellation()`, `parse_line()`, `reset()`.
- Constant `INTERFACE_VERSION = 0b0001_0001` for compatibility verification.
- Export of `IGNSSParser` to `__init__.py` for convenient extension.
- Support for parsing coordinates from GGA via unified `_parse_coordinates` method.

### Changed
- `NMEAStreamReader` is now typed and uses interface methods... (added wrapper methods `is_valid()`, `get_constellation()`).
- Simplified `reset()` logic — single method to reset all states.
- Improved memory benchmark accuracy: switched from `gc.mem_free()` to `gc.mem_alloc()` to eliminate the impact of heap fragmentation.

### Performance
- **23.8x** faster than micropyGPS on RP2040 (502 pkt/s vs 21 pkt/s).

## - 2026-07-12

### Added
- Support for VTG (Track Made Good and Ground Speed).
- Support for GLL (Geographic Position).
- Support for VTG without Mode Indicator (legacy NMEA format).
- Diagnostics by message types.
- Module `conv_to_hrf` with formatting functions: `_to_txt`, `_to_csv`, `_to_json`, `_to_compact`.
- `to_format()` function and format constants (`FMT_TXT`, `FMT_CSV`, `FMT_JSON`, `FMT_COMPACT`).
- Formatting of time and date via `_fmt_dt()` with `bytes` and `str` support.

### Changed
- `parse_line` broken down into separate methods: `_parse_rmc`, `_parse_gga`, `_parse_vtg`, `_parse_gll`.
- GLL upon 'V' status resets coordinates only, leaving data from other messages intact.
- One `memoryview` for all GGA fields (instead of multiple).
- Assembly of CSV strings migrated to `",".join()` for correct parsing in MicroPython.
- All magic strings, numbers, and identifiers moved to module constants.

### Fixed
- Critical `TypeError` when comparing `NoneType` fields with `int` (HDOP, constellation, fix mode) before a complete GGA packet is received.
- `SyntaxError` in MicroPython when using multi-line f-strings.
- `TypeError: join expects a list of str/bytes` error in `_to_csv` (added explicit type casting).
- Incorrect `None` output in text and JSON formats (now returning empty strings or default values).

## - 2026-07-06

### Added
- Initial release.
- Support for RMC and GGA.
- Multi-GNSS: GPS, GLONASS, BeiDou, Galileo, QZSS, NavIC.
- RTK Fixed/Float.
- Zero-allocation parsing.
- Filtering by constellations.
- Diagnostic counters.