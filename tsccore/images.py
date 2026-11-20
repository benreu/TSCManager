"""
Turning a picture into a file a TSC printer can print with PUTBMP or PUTPNG.

The printer prints the file pixel for pixel, one pixel to a dot, so the
picture is first resized to the size it should print at, in dots. Then it
becomes one of:

- a 1-bit BMP: black and white, the form every TSPL printer takes (p.92);
- an 8-bit grayscale BMP, printed in grey with PUTBMP's bpp 8: firmware
  V6.91 EZ or later, direct thermal only;
- a PNG (PUTPNG, firmware A2.12 or later), black and white like the 1-bit
  BMP but compressed, so it takes less of the printer's memory.

Black and white is made either by dithering (a photo keeps its shading as a
pattern of dots) or by a threshold (a logo or text stays crisp).

prepare() returns the file's bytes together with the image they hold, so a
frontend previews exactly what will be sent.
"""

import io
from dataclasses import dataclass
from typing import Optional, Tuple

from PIL import Image

BMP_1BIT, BMP_8BIT, PNG = 'bmp1', 'bmp8', 'png'

# (format, label, extension, what the printer needs), in menu order.
FORMATS = (
    (BMP_1BIT, "BMP, black and white", '.BMP', "any TSPL printer"),
    (BMP_8BIT, "BMP, grayscale", '.BMP',
     "firmware V6.91 EZ or later, direct thermal"),
    (PNG, "PNG, black and white", '.PNG', "firmware A2.12 or later"),
)
EXTENSIONS = {fmt: extension for fmt, _label, extension, _needs in FORMATS}

MM_PER_INCH = 25.4


def dots(mm: float, dpi: int) -> int:
    """`mm` as a whole number of dots at `dpi`, never less than one."""
    return max(1, round(mm * dpi / MM_PER_INCH))


def millimetres(count: int, dpi: int) -> float:
    return count * MM_PER_INCH / dpi


def fit_size(size: Tuple[int, int], width: Optional[int] = None,
             height: Optional[int] = None) -> Tuple[int, int]:
    """The picture's `size` scaled to `width` or `height` (in dots),
    keeping its proportions. Given both, the largest size that fits inside
    them; given neither, the size it has."""
    w, h = size
    if width and height:
        scale = min(width / w, height / h)
    elif width:
        scale = width / w
    elif height:
        scale = height / h
    else:
        return size
    return max(1, round(w * scale)), max(1, round(h * scale))


def flatten(image: Image.Image) -> Image.Image:
    """The picture in shades of grey, see-through parts as white paper."""
    if image.mode in ('RGBA', 'LA', 'PA') or (
            image.mode == 'P' and 'transparency' in image.info):
        rgba = image.convert('RGBA')
        paper = Image.new('RGBA', rgba.size, (255, 255, 255, 255))
        paper.alpha_composite(rgba)
        image = paper
    return image.convert('L')


@dataclass
class Prepared:
    data: bytes              # the file, ready for DOWNLOAD
    preview: Image.Image     # what it holds, in mode 'L'
    extension: str           # '.BMP' or '.PNG'


def black_and_white(grey: Image.Image, dither: bool = True,
                    threshold: int = 128) -> Image.Image:
    """A mode '1' image: Floyd-Steinberg dithered, or every pixel darker
    than `threshold` black."""
    if dither:
        return grey.convert('1')
    return grey.point(lambda v: 255 if v >= threshold else 0).convert(
        '1', dither=Image.Dither.NONE if hasattr(Image, 'Dither') else 0)


def prepare(image: Image.Image, size: Tuple[int, int], fmt: str = BMP_1BIT,
            dither: bool = True, threshold: int = 128) -> Prepared:
    """`image` at `size` dots, as a file in `fmt`. `dither` and `threshold`
    say how black and white is made, for the 1-bit BMP and the PNG."""
    grey = flatten(image)
    if grey.size != tuple(size):
        grey = grey.resize(tuple(size), Image.LANCZOS)
    out = io.BytesIO()
    if fmt == BMP_8BIT:
        grey.save(out, format='BMP')
        return Prepared(out.getvalue(), grey, '.BMP')
    mono = black_and_white(grey, dither, threshold)
    if fmt == PNG:
        mono.save(out, format='PNG', optimize=True)
        return Prepared(out.getvalue(), mono.convert('L'), '.PNG')
    mono.save(out, format='BMP')
    return Prepared(out.getvalue(), mono.convert('L'), '.BMP')


def test_pattern(width: int = 96, height: int = 64) -> Image.Image:
    """A picture that shows at a glance if it printed mirrored, upside
    down or inverted: a black arrow pointing right along the top edge, a
    filled square in the top-left corner, "TL" beside it and a frame."""
    from PIL import ImageDraw
    image = Image.new('L', (width, height), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=0)
    draw.rectangle((3, 3, 16, 16), fill=0)
    draw.text((21, 4), "TL", fill=0)
    mid = height * 2 // 3
    draw.line((8, mid, width - 14, mid), fill=0, width=3)
    draw.polygon(((width - 6, mid), (width - 18, mid - 8),
                  (width - 18, mid + 8)), fill=0)
    return image


def gradient(width: int = 128, height: int = 48) -> Image.Image:
    """Black on the left to white on the right, for the grey BMP."""
    image = Image.new('L', (width, height))
    image.putdata([255 * x // (width - 1) for _y in range(height)
                   for x in range(width)])
    return image
