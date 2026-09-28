from __future__ import annotations

from typing import Annotated, Dict, List, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator

ALIGNMENTS = ("left", "center", "right")

# Token upload selalu dibuat server via secrets.token_hex(16); format lain
# (mis. "../") ditolak agar tidak bisa dipakai menunjuk file di luar tmp_dir.
Token = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
CanvasSize = Annotated[float, Field(ge=10, le=20000)]
FontSize = Annotated[float, Field(gt=0, le=1000)]
Resolution = Annotated[float, Field(ge=36, le=1200)]


class TextField(BaseModel):
    """Satu potongan teks dinamis yang dicetak di atas background.

    Semua ukuran & koordinat memakai satuan kanvas (mis. pt di Canva).
    Saat render, nilainya diskalakan mengikuti lebar PNG background.
    """

    key: str = Field(..., description="Nama field, dipakai untuk mapping kolom data")
    label: str = ""
    pages: List[int] = Field(default_factory=lambda: [1])
    x: Optional[float] = Field(
        default=None, description="Koordinat X kanvas. Kosong = auto (tengah untuk align center)"
    )
    y: float = 0.0
    align: str = "left"
    font: str = Field(default="", description="Nama file font di folder template. Kosong = fallback")
    font_size: FontSize = 24.0
    font_size_min: Optional[FontSize] = Field(default=None, description="Batas kecil untuk auto-shrink")
    max_width: Optional[float] = Field(default=None, description="Lebar maks sebelum font mengecil")
    color: str = "#191919"
    sample: str = ""

    @field_validator("key")
    @classmethod
    def _clean_key(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("key wajib diisi")
        return value

    @field_validator("align")
    @classmethod
    def _check_align(cls, value: str) -> str:
        value = (value or "left").lower()
        if value not in ALIGNMENTS:
            raise ValueError(f"align harus salah satu dari {ALIGNMENTS}")
        return value

    @field_validator("pages")
    @classmethod
    def _check_pages(cls, value: List[int]) -> List[int]:
        cleaned = sorted({int(p) for p in value if int(p) in (1, 2)})
        return cleaned or [1]


class TemplateConfig(BaseModel):
    id: str
    name: str = "Template Baru"
    canvas_width: CanvasSize = 842.0
    canvas_height: CanvasSize = 595.0
    resolution: Resolution = 150.0
    bg_front: Optional[str] = None
    bg_back: Optional[str] = None
    fonts: List[str] = Field(default_factory=list)
    fields: List[TextField] = Field(default_factory=list)


class TemplateMeta(BaseModel):
    """Payload create/update metadata + fields (tanpa aset biner)."""

    name: Optional[str] = None
    canvas_width: Optional[CanvasSize] = None
    canvas_height: Optional[CanvasSize] = None
    resolution: Optional[Resolution] = None
    fields: Optional[List[TextField]] = None


class GenerateRequest(BaseModel):
    data_token: Token
    mapping: Dict[str, str]
    filename_field: Optional[str] = None


class SplitRequest(BaseModel):
    token: Token
    # "sequence" | "data" | "pdf_text". None = tebak otomatis (data bila ada, else sequence)
    name_source: Optional[str] = None
    name_column: Optional[str] = None
    text_anchor: str = ""
    text_regex: str = ""
    pages_per_doc: int = 1
    filename_prefix: str = ""
    start_number: int = 1


class SplitPreviewRequest(BaseModel):
    token: Token
    text_anchor: str = ""
    text_regex: str = ""
    pages_per_doc: int = 1
    filename_prefix: str = ""
    start_number: int = 1
    limit: int = 8
