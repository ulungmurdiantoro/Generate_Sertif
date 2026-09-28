from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from pypdf import PdfReader, PdfWriter

from .renderer import clean_filename, unique_name

# Fitur turunan dari split_sertifikat.py:
#   * pecah 1 PDF gabungan menjadi banyak PDF (1 berkas per peserta),
#   * penamaan berkas: nomor urut / kolom Excel-CSV / TEKS di dalam PDF,
#   * dukung >1 halaman per dokumen (mis. sertifikat 2 halaman),
#   * anti-bentrok nama berkas + validasi jumlah halaman vs jumlah nama.

_DEFAULT_ANCHOR = "diberikan kepada"
_STRIP_CHARS = " :\t\r\n-–—.·"
_WORD_GAP_RE = re.compile(r" {2,}")


def _degap(text: str) -> str:
    """Rapikan teks yang hurufnya terpisah spasi akibat letter-spacing lebar.

    Sejumlah desain sertifikat (Canva/Figma/dll) memakai letter-spacing lebar
    pada judul/nama, sehingga pypdf mengekstraknya sbg "T H I S  C E R T I F I C A T E"
    -- tiap huruf dipisah 1 spasi, sedangkan antar-kata dipisah 2+ spasi.
    Gabungkan lagi tiap kelompok huruf-tunggal itu supaya anchor/regex yang
    ditulis dgn ejaan normal tetap bisa cocok.
    """
    lines = []
    for line in text.splitlines():
        groups = _WORD_GAP_RE.split(line)
        merged = []
        for group in groups:
            tokens = group.split(" ")
            if len(tokens) > 1 and all(len(t) <= 1 for t in tokens):
                merged.append("".join(tokens))
            else:
                merged.append(group)
        lines.append(" ".join(merged))
    return "\n".join(lines)


@dataclass
class SplitOutput:
    files: List[Tuple[str, bytes]] = field(default_factory=list)
    unreadable: List[str] = field(default_factory=list)  # nama berkas yang gagal dibaca


def count_pages(pdf_bytes: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


def _page_text(page) -> str:
    try:
        text = page.extract_text() or ""
    except Exception:  # noqa: BLE001 - pypdf bisa lempar macam-macam untuk PDF rusak
        return ""
    return _degap(text)


def pdf_has_text_layer(pdf_bytes: bytes, sample: int = 8) -> bool:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    for page in reader.pages[:sample]:
        if _page_text(page).strip():
            return True
    return False


def extract_name(text: str, anchor: str = "", regex: str = "") -> str:
    """Ambil nama dari teks 1 dokumen.

    - `regex` (bila diisi): pakai grup tangkap pertama, atau seluruh kecocokan.
    - `anchor`: ambil teks sesudah frasa penanda (sisa baris, atau baris
      berikutnya yang tidak kosong).
    """
    text = text or ""

    if regex:
        try:
            match = re.search(regex, text, re.IGNORECASE | re.DOTALL)
        except re.error as exc:
            raise ValueError(f"Regex tidak valid: {exc}")
        if not match:
            return ""
        value = match.group(1) if match.groups() else match.group(0)
        return " ".join(value.split()).strip(_STRIP_CHARS)

    anchor = (anchor or _DEFAULT_ANCHOR).strip()
    lowered = text.lower()
    pos = lowered.find(anchor.lower())
    if pos == -1:
        return ""
    after = text[pos + len(anchor):]
    for line in after.splitlines():
        cleaned = " ".join(line.split()).strip(_STRIP_CHARS)
        if cleaned:
            return cleaned
    return ""


def _doc_text(reader: PdfReader, start: int, stop: int) -> str:
    return "\n".join(_page_text(reader.pages[p]) for p in range(start, stop))


def preview_names(
    pdf_bytes: bytes,
    pages_per_doc: int = 1,
    anchor: str = "",
    regex: str = "",
    filename_prefix: str = "",
    start_number: int = 1,
    limit: int = 8,
) -> dict:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total = len(reader.pages)
    ppd = max(1, int(pages_per_doc or 1))
    doc_count = total // ppd if ppd else 0
    rows = []
    for index in range(min(limit, doc_count)):
        chunk = _doc_text(reader, index * ppd, (index + 1) * ppd)
        name = extract_name(chunk, anchor, regex)
        rows.append({
            "doc": index + 1,
            "name": name,
            "filename": f"{filename_prefix}{name}" if name
            else f"{filename_prefix}(tidak terbaca #{start_number + index:03d})",
        })
    return {
        "has_text_layer": pdf_has_text_layer(pdf_bytes),
        "doc_count": doc_count,
        "rows": rows,
    }


def split_pdf(
    pdf_bytes: bytes,
    names: Optional[Sequence[str]] = None,
    pages_per_doc: int = 1,
    filename_prefix: str = "",
    start_number: int = 1,
    name_from_text: bool = False,
    text_anchor: str = "",
    text_regex: str = "",
) -> SplitOutput:
    pages_per_doc = int(pages_per_doc or 1)
    if pages_per_doc < 1:
        raise ValueError("Halaman per dokumen minimal 1.")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)
    if total_pages == 0:
        raise ValueError("PDF tidak punya halaman.")
    if total_pages % pages_per_doc != 0:
        raise ValueError(
            f"Jumlah halaman PDF ({total_pages}) tidak habis dibagi "
            f"{pages_per_doc} halaman/dokumen."
        )

    doc_count = total_pages // pages_per_doc

    clean_names: Optional[List[str]] = None
    if names is not None and not name_from_text:
        clean_names = [str(n).strip() for n in names]
        if len(clean_names) != doc_count:
            raise ValueError(
                f"Jumlah nama ({len(clean_names)}) tidak sama dengan jumlah dokumen "
                f"({doc_count}) = {total_pages} halaman / {pages_per_doc} halaman."
            )

    if name_from_text and not pdf_has_text_layer(pdf_bytes):
        raise ValueError(
            "PDF ini tidak punya lapisan teks yang bisa dibaca. Gunakan daftar "
            "nama (Excel/CSV) atau penomoran urut."
        )

    prefix = filename_prefix or ""
    used: set = set()
    out = SplitOutput()

    for index in range(doc_count):
        number = start_number + index

        if name_from_text:
            chunk = _doc_text(reader, index * pages_per_doc, (index + 1) * pages_per_doc)
            label = extract_name(chunk, text_anchor, text_regex)
        elif clean_names is not None:
            label = clean_names[index]
        else:
            label = ""

        readable = bool(label) and label.lower() != "nan"
        if readable:
            stem = f"{prefix}{label}"
        elif name_from_text:
            stem = f"{prefix}TIDAK-TERBACA-{number:03d}"
        else:
            stem = f"{prefix}{number:03d}"
        stem = clean_filename(stem) or f"dokumen_{number}"
        name = unique_name(stem, used)

        writer = PdfWriter()
        for page in range(index * pages_per_doc, (index + 1) * pages_per_doc):
            writer.add_page(reader.pages[page])
        buffer = io.BytesIO()
        writer.write(buffer)

        filename = f"{name}.pdf"
        out.files.append((filename, buffer.getvalue()))
        if name_from_text and not readable:
            out.unreadable.append(filename)

    return out


def build_zip(files: Sequence[Tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, data in files:
            archive.writestr(filename, data)
    return buffer.getvalue()
