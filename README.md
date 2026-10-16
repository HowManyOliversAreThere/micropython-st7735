# ST7735 TFT display

A MicroPython driver for **Sitronix ST7735 / ST7735S / ST7735R** colour
TFT controllers (such as common 1.8" 128×160 panels) over SPI. It draws
into a full-screen RGB565 `framebuf.FrameBuffer`, so every framebuf
drawing method works, then sends it with `show()`.

Copy `st7735.py` onto your board, or install it with `mip`:

```python
import mip
mip.install("github:HowManyOliversAreThere/micropython-st7735")
```

## Usage

```python
from machine import SPI, Pin
import st7735

spi = SPI(1, baudrate=26_000_000, sck=Pin(23), mosi=Pin(22))
display = st7735.ST7735(spi, cs=Pin(1), dc=Pin(8), rst=Pin(14), rotation=0)

fb = display.fb
fb.fill(st7735.color565(0, 0, 40))
fb.rect(4, 4, display.width - 8, display.height - 8, st7735.color565(255, 255, 255))
fb.text("Hello!", 12, 12, st7735.color565(255, 200, 0))
display.show()

display.rotation(90)    # landscape: width/height swap, redraw everything
display.sleep()         # and switch the backlight off separately
```

### Is a display connected?

`detect()` bit-bangs the panel's Read Display ID command on the SPI pins,
listening on SDA (and MISO, if given) with a pull-up. It returns the
three ID bytes, or `None` if nothing answers. Call it before setting up
the SPI bus, or re-initialise the bus afterwards:

```python
ident = st7735.detect(sck=Pin(23), sda=Pin(22), cs=Pin(1), dc=Pin(8), miso=Pin(21), rst=Pin(14))
```

This only works on panels that let the controller drive SDA (or bring
SDO out). On a module where SDA is input-only, it reports `None` even
when a panel is connected.

## Notes

- Colours from `color565()` are byte-swapped for the panel, so use them
  (not plain RGB565 values) when drawing.
- Panels vary. If colours are red/blue swapped, flip `bgr`. If there's a
  stripe of noise at an edge, set `x_offset`/`y_offset` (often 2 and 1).
  If colours are inverted, set `invert=True`.
- The buffer takes `width × height × 2` bytes (40 KB at 128×160). Pass
  your own `buffer` to share or preallocate it.
- `show_rows(y0, y1)` sends only part of the screen, which is quicker for
  small updates.

## License

MIT - see [LICENSE](LICENSE).
