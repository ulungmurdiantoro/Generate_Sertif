import os
import sys
import tempfile
from pathlib import Path

import pytest

# Harus di-set sebelum app di-import: get_settings() di-cache saat import.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="sertif-test-")
os.environ["BASIC_AUTH_USER"] = ""
os.environ["BASIC_AUTH_PASS"] = ""
os.environ["RENDER_WORKERS"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_font(path: Path, chars: str) -> Path:
    """Font TTF minimal yang HANYA punya glyph untuk `chars`."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    names = {ch: f"uni{ord(ch):04X}" for ch in chars}
    order = [".notdef", *names.values()]

    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((50, 600))
    pen.lineTo((450, 600))
    pen.lineTo((450, 0))
    pen.closePath()
    box = pen.glyph()

    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({ord(ch): name for ch, name in names.items()})
    fb.setupGlyf({name: box for name in order})
    fb.setupHorizontalMetrics({name: (500, 50) for name in order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=800, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.save(str(path))
    return path


@pytest.fixture
def font_factory(tmp_path):
    return lambda chars, name="test.ttf": make_font(tmp_path / name, chars)


def make_pdf(pages: int) -> bytes:
    """PDF kosong tanpa lapisan teks."""
    return make_text_pdf([[] for _ in range(pages)])


def make_text_pdf(pages: list) -> bytes:
    """PDF dgn lapisan teks (Helvetica); `pages` = list baris teks per halaman."""
    import io

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    for lines in pages:
        page = writer.add_blank_page(width=300, height=300)
        if not lines:
            continue
        ops = ["BT", "/F1 12 Tf", "20 260 Td"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops += [f"({escaped}) Tj", "0 -20 Td"]
        ops.append("ET")
        stream = DecodedStreamObject()
        stream.set_data("\n".join(ops).encode("latin-1"))
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
