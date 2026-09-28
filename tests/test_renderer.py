from PIL import Image

from app.models import TemplateConfig, TextField
from app.renderer import fit_text_to_font, render_pages

LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ "


def test_curly_apostrophe_falls_back_to_ascii_when_font_lacks_it(font_factory):
    font = font_factory(LETTERS + "'")
    assert fit_text_to_font("Ma’ruf O‘Brien", str(font)) == "Ma'ruf O'Brien"


def test_curly_apostrophe_kept_when_font_has_it(font_factory):
    font = font_factory(LETTERS + "'’")
    assert fit_text_to_font("Ma’ruf", str(font)) == "Ma’ruf"


def test_invisible_chars_removed_and_nfc_applied(font_factory):
    font = font_factory(LETTERS + "é")
    decomposed = "René​ Ama"
    assert fit_text_to_font(decomposed, str(font)) == "René Ama"


def test_unknown_char_without_fallback_is_left_as_is(font_factory):
    font = font_factory(LETTERS)
    assert fit_text_to_font("A中B", str(font)) == "A中B"


def test_render_pages_with_apostrophe_name(tmp_path, font_factory):
    (tmp_path / "fonts").mkdir()
    font_factory(LETTERS + "'", name="fonts/custom.ttf")
    Image.new("RGB", (842, 595), "white").save(tmp_path / "bg.png")
    cfg = TemplateConfig(
        id="t1", bg_front="bg.png",
        fields=[TextField(key="nama", font="custom.ttf", y=200, align="center")],
    )
    pages = render_pages(cfg, {"nama": "Ma’ruf Amin"}, str(tmp_path))
    assert len(pages) == 1
    assert pages[0].getbbox() is not None
