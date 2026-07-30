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

"""Base interface for NMEA-0183 GNSS parsers.
Defines the interface that any parser must implement to work with NMEAStreamReader."""

try:
    from micropython import const, native
except ImportError:
    def const(val):
        return val
    def native(func):
        return func


class IGNSSParser:
    """Base interface for all NMEA-0183 GNSS parsers.

    Note: The term 'data provider' used below refers to the provider of NMEA-183 'sentences'!
    Example of minimal implementation:

        class MyParser(IGNSSParser):
            def is_valid(self) -> bool:
                return self._valid

            def get_constellation(self) -> int:
                return self._constellation

            def parse_line(self, line_bytes: bytes, start: int, end: int) -> bool:
                # NMEA sentence parsing
                return True

            def reset(self) -> None:
                self._valid = False
                self._constellation = 0
    """
    INTERFACE_VERSION = 0b0001_0001

    def is_valid(self) -> bool:
        """
        Returns the validity flag of the parser's current state.

        True  - The parser has valid data (fix, coordinates, etc.).
        False - Data is missing or invalid.

        Used by the data provider in a callback function for statistics.

        Returns:
            bool: True if data is valid, otherwise False.

        Raises:
            NotImplementedError: If the method is not overridden in the subclass.
        """
        raise NotImplementedError(
            "Method is_valid() must be implemented in the IGNSSParser subclass"
        )

    def get_constellation(self) -> int:
        """
        Returns the numeric identifier of the current GNSS constellation.

        Identifier values (standard CST_* constants):
            0 - Unknown constellation (CST_UNKNOWN)
            1 - GPS
            2 - GLONASS
            3 - Galileo
            4 - BeiDou
            5 - QZSS
            6 - NavIC (IRNSS)
            7 - Multi-GNSS (mixed solution)

        If the constellation is not defined, the method must return 0 (CST_UNKNOWN).

        Returns:
            int: Constellation identifier (0..7).

        Raises:
            NotImplementedError: If the method is not overridden in the subclass.
        """
        raise NotImplementedError(
            "Method get_constellation() must be implemented in the IGNSSParser subclass"
        )

    def parse_line(self, line_bytes: bytes, start: int, end: int) -> bool:
        """
        Parses a single NMEA sentence from a byte buffer.

        The main method of the parser. Called by the data provider for each
        completed packet (from '$' to CR+LF inclusive).

        Args:
            line_bytes (bytes|bytearray): Buffer containing the NMEA sentence.
                The parser MUST NOT modify the buffer and MUST NOT save
                a reference to it after returning from the method.
            start (int): Index of the first byte of the sentence (inclusive).
                Usually points to the '$' character.
            end (int): Index of the end of the sentence (exclusive).
                Usually points to the byte immediately after '\\n'.

        Returns:
            bool: True  - The packet was recognized and successfully processed.
                  False - The packet was not recognized (unknown type) or rejected
                          (CRC error, too short, etc.).

        Raises:
            NotImplementedError: If the method is not overridden in the subclass.
        """
        raise NotImplementedError(
            "Method parse_line(line_bytes, start, end) must be implemented "
            "in the IGNSSParser subclass"
        )

    def reset(self) -> None:
        """
        Resets the internal state of the parser to default values.

        Called when:
            - UART baud rate changes,
            - UART errors are detected (buffer overflow, loss of synchronization),
            - GNSS module loses power,
            - Explicit user request.

        After calling reset(), the parser must be in a state
        equivalent to a newly created instance:
            - is_valid() returns False,
            - get_constellation() returns 0,
            - All internal counters and buffers are cleared.

        Raises:
            NotImplementedError: If the method is not overridden in the subclass.
        """
        raise NotImplementedError(
            "Method reset() must be implemented in the IGNSSParser subclass"
        )


# Type alias for use in NMEAStreamReader annotations.
# In MicroPython, type annotations are not checked at runtime, but help IDEs.
GNSSParser = IGNSSParser