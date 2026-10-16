"""
MicroPython driver for Sitronix ST7735 / ST7735S / ST7735R colour TFT
controllers over SPI, drawing through a framebuf.FrameBuffer.

The whole screen is buffered in RAM as RGB565 (128x160 = 40 KB) and sent
with show(). Draw with the usual framebuf methods on `display.fb` (fill,
text, rect, line, blit ...) using colours from color565().

Quick start
-----------
    from machine import SPI, Pin
    import st7735

    spi = SPI(1, baudrate=26_000_000, sck=Pin(23), mosi=Pin(22))
    display = st7735.ST7735(spi, cs=Pin(1), dc=Pin(8), rst=Pin(14))
    fb = display.fb
    fb.fill(st7735.color565(0, 0, 0))
    fb.text("Hello", 10, 10, st7735.color565(255, 255, 0))
    display.show()

Panels differ in colour order and in how the visible area sits in the
controller's 132x162 memory, so `bgr`, `x_offset`, `y_offset` and
`invert` may need adjusting for yours.

detect() checks whether a panel is connected at all, by reading its ID
over the bidirectional SDA line (needs the pins, not the SPI object).
"""

import framebuf
import time
from micropython import const

_SWRESET = const(0x01)
_RDDID = const(0x04)
_SLPIN = const(0x10)
_SLPOUT = const(0x11)
_NORON = const(0x13)
_INVOFF = const(0x20)
_INVON = const(0x21)
_DISPOFF = const(0x28)
_DISPON = const(0x29)
_CASET = const(0x2A)
_RASET = const(0x2B)
_RAMWR = const(0x2C)
_MADCTL = const(0x36)
_COLMOD = const(0x3A)

_MADCTL_MY = const(0x80)
_MADCTL_MX = const(0x40)
_MADCTL_MV = const(0x20)
_MADCTL_BGR = const(0x08)

# MADCTL for rotations 0, 90, 180 and 270 degrees (clockwise).
_ROTATIONS = (_MADCTL_MX | _MADCTL_MY, _MADCTL_MY | _MADCTL_MV, 0, _MADCTL_MX | _MADCTL_MV)

# (command, data, delay ms) - the usual ST7735R/S power-up sequence.
_INIT = (
    (_SWRESET, b"", 150),
    (_SLPOUT, b"", 255),
    (0xB1, b"\x01\x2c\x2d", 0),  # FRMCTR1: frame rate, normal mode
    (0xB2, b"\x01\x2c\x2d", 0),  # FRMCTR2: idle mode
    (0xB3, b"\x01\x2c\x2d\x01\x2c\x2d", 0),  # FRMCTR3: partial mode
    (0xB4, b"\x07", 0),  # INVCTR: no inversion
    (0xC0, b"\xa2\x02\x84", 0),  # PWCTR1
    (0xC1, b"\xc5", 0),  # PWCTR2
    (0xC2, b"\x0a\x00", 0),  # PWCTR3
    (0xC3, b"\x8a\x2a", 0),  # PWCTR4
    (0xC4, b"\x8a\xee", 0),  # PWCTR5
    (0xC5, b"\x0e", 0),  # VMCTR1
    (_COLMOD, b"\x05", 0),  # 16 bits per pixel
    (0xE0, b"\x02\x1c\x07\x12\x37\x32\x29\x2d\x29\x25\x2b\x39\x00\x01\x03\x10", 0),  # gamma +
    (0xE1, b"\x03\x1d\x07\x06\x2e\x2c\x29\x2d\x2e\x2e\x37\x3f\x00\x00\x02\x10", 0),  # gamma -
    (_NORON, b"", 10),
)


def color565(r, g, b):
    """An RGB colour for drawing on the framebuffer. framebuf stores
    pixels little-endian, but the panel wants them big-endian, so the
    bytes are swapped here once rather than on every show()."""
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c & 0xFF) << 8) | (c >> 8)


def detect(sck, sda, cs, dc, miso=None, rst=None):
    """Read the panel's ID (RDDID) by bit-banging the SPI pins, with SDA
    switched to an input (pulled up) for the reply. Returns the 3 ID
    bytes, or None if nothing answers (all ones or all zeros). Also
    samples `miso`, for boards that bring a separate SDO out.

    The pins are left as plain GPIOs: (re)initialise the SPI bus
    afterwards. sck, sda, cs, dc, miso and rst are machine.Pin objects."""
    from machine import Pin

    if rst is not None:
        rst.init(Pin.OUT, value=1)
        rst(0)
        time.sleep_ms(5)
        rst(1)
        time.sleep_ms(120)
    cs.init(Pin.OUT, value=1)
    dc.init(Pin.OUT, value=0)
    sck.init(Pin.OUT, value=0)
    sda.init(Pin.OUT, value=0)
    if miso is not None:
        miso.init(Pin.IN, Pin.PULL_UP)
    cs(0)
    for i in range(7, -1, -1):  # command byte, MSB first, latched on the rising edge
        sda((_RDDID >> i) & 1)
        sck(1)
        sck(0)
    sda.init(Pin.IN, Pin.PULL_UP)
    bits_sda = 0
    bits_miso = 0
    for _ in range(25):  # one dummy clock, then 24 bits of ID
        sck(1)
        bits_sda = (bits_sda << 1) | sda()
        if miso is not None:
            bits_miso = (bits_miso << 1) | miso()
        sck(0)
    cs(1)
    for bits in (bits_sda, bits_miso):
        for value in (bits & 0xFFFFFF, bits >> 1):
            if value not in (0, 0xFFFFFF):
                return bytes(((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF))
    return None


class ST7735:
    def __init__(self, spi, cs, dc, rst=None, width=128, height=160, rotation=0,
                 bgr=True, x_offset=0, y_offset=0, invert=False, buffer=None):
        """
        spi      : machine.SPI, already initialised (up to ~26 MHz is typical)
        cs, dc   : machine.Pin outputs
        rst      : optional machine.Pin for the panel's reset line
        width,
        height   : the panel's size in its native (rotation 0) orientation
        rotation : 0, 90, 180 or 270
        bgr      : panel wired blue-green-red (most 1.8" ST7735S panels)
        x_offset,
        y_offset : where the visible area starts in controller memory,
                   at rotation 0
        invert   : panels that show inverted colours need this
        buffer   : optional bytearray of width*height*2 to draw into
        """
        self._spi = spi
        self._cs = cs
        self._dc = dc
        self._rst = rst
        self._native = (width, height)
        self._offsets = (x_offset, y_offset)
        self._bgr = bgr
        self._invert = invert
        cs.init(cs.OUT, value=1)
        dc.init(dc.OUT, value=0)
        if rst is not None:
            rst.init(rst.OUT, value=1)
        self.buffer = buffer if buffer is not None else bytearray(width * height * 2)
        self._rotation = None
        self.init()
        self.rotation(rotation)

    # ---- Low-level --------------------------------------------------------
    def _command(self, cmd, data=b""):
        self._cs(0)
        self._dc(0)
        self._spi.write(bytes((cmd,)))
        if data:
            self._dc(1)
            self._spi.write(data)
        self._cs(1)

    def init(self):
        """Reset and configure the controller (blank, display on)."""
        if self._rst is not None:
            self._rst(0)
            time.sleep_ms(5)
            self._rst(1)
            time.sleep_ms(120)
        for cmd, data, delay in _INIT:
            self._command(cmd, data)
            if delay:
                time.sleep_ms(delay)
        self._command(_INVON if self._invert else _INVOFF)
        if self._rotation is not None:
            self._apply_rotation()
        self._command(_DISPON)
        time.sleep_ms(10)

    # ---- Geometry ---------------------------------------------------------
    def rotation(self, degrees=None):
        """Get or set the rotation (0, 90, 180, 270). Turning between
        portrait and landscape swaps width and height, and makes a new
        `fb` over the same buffer, so redraw everything after it."""
        if degrees is None:
            return self._rotation
        if degrees not in (0, 90, 180, 270):
            raise ValueError("rotation must be 0, 90, 180 or 270")
        self._rotation = degrees
        w, h = self._native
        if degrees in (90, 270):
            w, h = h, w
        self.width, self.height = w, h
        self.fb = framebuf.FrameBuffer(self.buffer, w, h, framebuf.RGB565)
        self._apply_rotation()
        return degrees

    def _apply_rotation(self):
        r = self._rotation // 90
        madctl = _ROTATIONS[r] | (_MADCTL_BGR if self._bgr else 0)
        self._command(_MADCTL, bytes((madctl,)))
        # Controller memory is 132x162; where the panel sits in it
        # depends on which way it's being scanned.
        xo, yo = self._offsets
        if r in (1, 3):
            xo, yo = yo, xo
        self._x0, self._y0 = xo, yo

    def _window(self, x0, y0, x1, y1):
        xs, ys = self._x0 + x0, self._y0 + y0
        xe, ye = self._x0 + x1, self._y0 + y1
        self._command(_CASET, bytes((xs >> 8, xs & 0xFF, xe >> 8, xe & 0xFF)))
        self._command(_RASET, bytes((ys >> 8, ys & 0xFF, ye >> 8, ye & 0xFF)))

    # ---- Output -----------------------------------------------------------
    def show(self):
        """Send the whole framebuffer to the panel."""
        self._window(0, 0, self.width - 1, self.height - 1)
        self._command(_RAMWR, self.buffer)

    def show_rows(self, y0, y1):
        """Send rows y0..y1 (inclusive) only - quicker for small changes."""
        y0 = max(0, y0)
        y1 = min(self.height - 1, y1)
        if y1 < y0:
            return
        self._window(0, y0, self.width - 1, y1)
        row = self.width * 2
        self._command(_RAMWR, memoryview(self.buffer)[y0 * row : (y1 + 1) * row])

    # ---- Power ------------------------------------------------------------
    def sleep(self):
        """Display off and controller asleep (a few uA). The backlight is
        separate - switch it off too."""
        self._command(_DISPOFF)
        self._command(_SLPIN)
        time.sleep_ms(5)

    def wake(self):
        self._command(_SLPOUT)
        time.sleep_ms(120)
        self._command(_DISPON)

    def power(self, on):
        if on:
            self.wake()
        else:
            self.sleep()
