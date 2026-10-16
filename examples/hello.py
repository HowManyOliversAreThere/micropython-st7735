"""Check for a panel, then draw a test pattern in each rotation."""

import time
from machine import SPI, Pin

import st7735

SCK, MOSI, MISO, CS, DC, RST = 23, 22, 21, 1, 8, 14

ident = st7735.detect(Pin(SCK), Pin(MOSI), Pin(CS), Pin(DC), miso=Pin(MISO), rst=Pin(RST))
print("Display ID:", ident.hex() if ident else "nothing answered")

spi = SPI(1, baudrate=26_000_000, sck=Pin(SCK), mosi=Pin(MOSI), miso=Pin(MISO))
display = st7735.ST7735(spi, cs=Pin(CS), dc=Pin(DC), rst=Pin(RST))
colours = [st7735.color565(*c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255))]

for rotation in (0, 90, 180, 270):
    display.rotation(rotation)
    fb = display.fb
    fb.fill(0)
    bar = display.width // 4
    for i, c in enumerate(colours):
        fb.fill_rect(i * bar, 20, bar, display.height - 20, c)
    fb.text("rot {}".format(rotation), 2, 6, colours[3])
    display.show()
    time.sleep(2)
