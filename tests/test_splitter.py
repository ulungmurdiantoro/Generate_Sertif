import zipfile

import pytest

from app.splitter import UNREADABLE_REPORT, _degap, extract_name, split_pdf
from conftest import make_pdf, make_text_pdf

LETTER_SPACED = (
    "T H I S  C E R T I F I C A T E  I S  P R E S E N T E D  T O :\n"
    "D r .  J u l i a n i  D y a h  T r i s n a w a t i ,  S . S i . ,  M . M . ,  C P P M .\n"
    "S e m a r a n g ,  1 9 t h  S e p t e m b e r  2 0 2 6"
)


def test_degap_rejoins_letter_spaced_text():
    assert _degap(LETTER_SPACED).splitlines() == [
        "THIS CERTIFICATE IS PRESENTED TO:",
        "Dr. Juliani Dyah Trisnawati, S.Si., M.M., CPPM.",
        "Semarang, 19th September 2026",
    ]


@pytest.mark.parametrize("text", [
    "Diberikan kepada:\nBudi Santoso\natas partisipasinya.",
    "Number : T-017/SERT/EDUKIA/IX/2026",
    "",
])
def test_degap_leaves_normal_text_alone(text):
    assert _degap(text) == text


def test_extract_name_after_degap():
    name = extract_name(_degap(LETTER_SPACED), "THIS CERTIFICATE IS PRESENTED TO:")
    assert name == "Dr. Juliani Dyah Trisnawati, S.Si., M.M., CPPM"


def test_extract_name_regex_wins_over_anchor():
    text = "Kepada: Budi Santoso\nDiberikan kepada: Salah"
    assert extract_name(text, "Diberikan kepada", r"Kepada:\s*(.+)") == "Budi Santoso"


def test_extract_name_invalid_regex():
    with pytest.raises(ValueError):
        extract_name("x", regex="(")


def test_split_pdf_writes_named_files_to_zip(tmp_path):
    zip_path = tmp_path / "out.zip"
    seen = []
    result = split_pdf(
        make_pdf(4), str(zip_path), names=["Ma’ruf", "O'Brien"], pages_per_doc=2,
        progress=lambda done, total: seen.append((done, total)),
    )
    assert result.count == 2
    assert seen == [(1, 2), (2, 2)]
    with zipfile.ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == ["Ma’ruf.pdf", "O'Brien.pdf"]


def test_split_pdf_names_from_text_and_reports_unreadable(tmp_path):
    pdf = make_text_pdf([
        ["Diberikan kepada:", "Budi Santoso"],
        ["Tanpa frasa penanda"],
        ["D i b e r i k a n  k e p a d a :", "S i t i  A m i n a h"],
    ])
    zip_path = tmp_path / "out.zip"
    result = split_pdf(pdf, str(zip_path), name_from_text=True, text_anchor="Diberikan kepada")

    assert result.unreadable == ["TIDAK-TERBACA-002.pdf"]
    with zipfile.ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == [
            "Budi Santoso.pdf", "Siti Aminah.pdf", "TIDAK-TERBACA-002.pdf", UNREADABLE_REPORT,
        ]
        assert "TIDAK-TERBACA-002.pdf" in archive.read(UNREADABLE_REPORT).decode("utf-8")


def test_split_pdf_name_from_text_needs_text_layer(tmp_path):
    with pytest.raises(ValueError, match="lapisan teks"):
        split_pdf(make_pdf(2), str(tmp_path / "out.zip"), name_from_text=True)


def test_split_pdf_rejects_name_count_mismatch(tmp_path):
    with pytest.raises(ValueError, match="Jumlah nama"):
        split_pdf(make_pdf(3), str(tmp_path / "out.zip"), names=["A", "B"])


def test_split_pdf_rejects_uneven_pages(tmp_path):
    with pytest.raises(ValueError, match="tidak habis dibagi"):
        split_pdf(make_pdf(3), str(tmp_path / "out.zip"), pages_per_doc=2)
