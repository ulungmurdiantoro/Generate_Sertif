from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import (Depends, FastAPI, File, Form, HTTPException, Request,
                     Response, UploadFile)
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageFont

from . import storage
from .config import get_settings
from .jobs import cleanup_old_jobs, get_job, start_job, start_split_job
from .models import (GenerateRequest, SplitPreviewRequest, SplitRequest,
                     TemplateMeta)
from .renderer import cell_to_str, render_preview_png
from .splitter import count_pages, preview_names

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
FONT_EXTS = (".ttf", ".otf", ".ttc")
# utf-8-sig: CSV "UTF-8" dari Excel diawali BOM. cp1252: CSV biasa dari Excel
# Windows (apostrof ’ = byte 0x92; latin-1 salah membacanya jadi karakter kontrol).
CSV_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")

BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()
security = HTTPBasic(auto_error=False)


def require_auth(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
) -> None:
    if request.url.path == "/healthz":
        return
    user, password = settings.basic_auth_user, settings.basic_auth_pass
    if not user or not password:
        return  # auth dinonaktifkan
    ok = (
        credentials is not None
        and secrets.compare_digest(credentials.username, user)
        and secrets.compare_digest(credentials.password, password)
    )
    if not ok:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    async def sweeper() -> None:
        while True:
            await asyncio.sleep(600)
            try:
                cleanup_old_jobs()
            except Exception:  # noqa: BLE001
                pass

    task = asyncio.create_task(sweeper())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title=settings.app_name,
    dependencies=[Depends(require_auth)],
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
jinja = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ?v=<hash isi file>: tiap deploy yang mengubah JS/CSS otomatis membatalkan
# cache browser, supaya JS lama tidak dipakai bersama API yang sudah berubah.
_STATIC_VERSIONS = {
    path.name: hashlib.sha256(path.read_bytes()).hexdigest()[:10]
    for path in (BASE_DIR / "static").iterdir()
    if path.is_file()
}


def static_url(name: str) -> str:
    return f"/static/{name}?v={_STATIC_VERSIONS.get(name, '0')}"


jinja.env.globals["static_url"] = static_url


# ----------------------------- helpers ------------------------------


def _load(template_id: str):
    try:
        return storage.load_template(template_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Template tidak ditemukan.")


def _check_size(content: bytes) -> None:
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File melebihi batas {settings.max_upload_mb} MB.",
        )


def _read_dataframe(filename: str, content: bytes) -> pd.DataFrame:
    name = (filename or "").lower()
    buffer = io.BytesIO(content)
    try:
        if name.endswith((".csv", ".txt")):
            for encoding in CSV_ENCODINGS:
                buffer.seek(0)
                try:
                    return pd.read_csv(buffer, encoding=encoding)
                except UnicodeDecodeError:
                    continue
        return pd.read_excel(buffer)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Gagal membaca file data: {exc}")


def _ingest_table(upload: UploadFile, content: bytes) -> pd.DataFrame:
    """Baca Excel/CSV, validasi, dan ubah semua sel jadi string rapi."""
    df = _read_dataframe(upload.filename or "", content)
    df.columns = [str(col) for col in df.columns]
    if len(df) == 0:
        raise HTTPException(status_code=400, detail="File data tidak punya baris.")
    if len(df) > settings.max_rows:
        raise HTTPException(
            status_code=400,
            detail=f"Jumlah baris {len(df)} melebihi batas {settings.max_rows}.",
        )
    return df.map(cell_to_str)


# Data upload disimpan sbg JSON, bukan pickle: memuat pickle = menjalankan kode.
def _save_table(path: str, df: pd.DataFrame) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {"columns": list(df.columns), "rows": df.values.tolist()},
            handle,
            ensure_ascii=False,
        )


def _load_table(path: str) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return pd.DataFrame(payload["rows"], columns=payload["columns"])


def _table_summary(df: pd.DataFrame) -> dict:
    return {
        "columns": list(df.columns),
        "rows": int(len(df)),
        "sample": df.head(5).to_dict(orient="records"),
    }


# ----------------------------- halaman HTML -------------------------


@app.get("/", response_class=HTMLResponse)
def page_index(request: Request):
    return jinja.TemplateResponse(request, "index.html", {"settings": settings})


@app.get("/templates/{template_id}", response_class=HTMLResponse)
def page_editor(request: Request, template_id: str):
    _load(template_id)
    return jinja.TemplateResponse(
        request, "editor.html", {"settings": settings, "template_id": template_id}
    )


@app.get("/templates/{template_id}/generate", response_class=HTMLResponse)
def page_generate(request: Request, template_id: str):
    _load(template_id)
    return jinja.TemplateResponse(
        request, "generate.html", {"settings": settings, "template_id": template_id}
    )


@app.get("/split", response_class=HTMLResponse)
def page_split(request: Request):
    return jinja.TemplateResponse(request, "split.html", {"settings": settings})


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ----------------------------- template CRUD -----------------------


@app.get("/api/templates")
def api_list_templates():
    return [cfg.model_dump() for cfg in storage.list_templates()]


@app.post("/api/templates")
def api_create_template(payload: TemplateMeta = TemplateMeta()):
    cfg = storage.create_template(payload.name or "Template Baru")
    return cfg.model_dump()


@app.get("/api/templates/{template_id}")
def api_get_template(template_id: str):
    return _load(template_id).model_dump()


@app.put("/api/templates/{template_id}")
def api_update_template(template_id: str, meta: TemplateMeta):
    cfg = _load(template_id)
    if meta.name is not None:
        cfg.name = meta.name
    if meta.canvas_width:
        cfg.canvas_width = meta.canvas_width
    if meta.canvas_height:
        cfg.canvas_height = meta.canvas_height
    if meta.resolution:
        cfg.resolution = meta.resolution
    if meta.fields is not None:
        cfg.fields = meta.fields
    storage.save_template(cfg)
    return cfg.model_dump()


@app.delete("/api/templates/{template_id}")
def api_delete_template(template_id: str):
    _load(template_id)
    storage.delete_template(template_id)
    return {"ok": True}


@app.post("/api/templates/{template_id}/assets")
async def api_upload_asset(
    template_id: str,
    kind: str = Form(...),
    file: UploadFile = File(...),
):
    _load(template_id)
    if kind not in ("bg_front", "bg_back", "font"):
        raise HTTPException(status_code=400, detail="kind tidak valid.")
    content = await file.read()
    _check_size(content)
    filename = (file.filename or "").lower()
    if kind in ("bg_front", "bg_back"):
        if not filename.endswith(IMAGE_EXTS):
            raise HTTPException(status_code=400, detail="Background harus PNG/JPG/WEBP.")
        try:
            Image.open(io.BytesIO(content)).verify()
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="File bukan gambar yang valid.")
    else:
        if not filename.endswith(FONT_EXTS):
            raise HTTPException(status_code=400, detail="Font harus .ttf / .otf / .ttc.")
        try:
            ImageFont.truetype(io.BytesIO(content), 12)
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="File bukan font yang valid.")
    cfg = storage.save_asset(template_id, kind, file.filename or kind, content)
    return cfg.model_dump()


@app.delete("/api/templates/{template_id}/fonts/{name}")
def api_delete_font(template_id: str, name: str):
    _load(template_id)
    return storage.delete_font(template_id, name).model_dump()


@app.get("/api/templates/{template_id}/preview")
def api_preview(template_id: str, page: int = 1):
    cfg = _load(template_id)
    try:
        png = render_preview_png(cfg, storage.template_dir(template_id), page=page)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        content=png, media_type="image/png", headers={"Cache-Control": "no-store"}
    )


# ----------------------------- data + generate --------------------


@app.post("/api/templates/{template_id}/data")
async def api_upload_data(template_id: str, file: UploadFile = File(...)):
    _load(template_id)
    content = await file.read()
    _check_size(content)
    df = _ingest_table(file, content)

    token = secrets.token_hex(16)
    _save_table(os.path.join(settings.tmp_dir, f"{token}.json"), df)
    return {"data_token": token, **_table_summary(df)}


@app.post("/api/templates/{template_id}/generate")
def api_generate(template_id: str, req: GenerateRequest):
    cfg = _load(template_id)
    if not cfg.bg_front:
        raise HTTPException(
            status_code=400, detail="Template belum punya background halaman depan."
        )

    data_path = os.path.join(settings.tmp_dir, f"{req.data_token}.json")
    if not os.path.isfile(data_path):
        raise HTTPException(
            status_code=400, detail="Data kedaluwarsa / tidak ditemukan. Upload ulang."
        )
    df = _load_table(data_path)

    keys = {f.key for f in cfg.fields}
    mapping = {k: v for k, v in req.mapping.items() if k in keys and v}
    if not mapping:
        raise HTTPException(status_code=400, detail="Mapping kolom kosong.")

    unknown = sorted({v for v in mapping.values() if v not in df.columns})
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Kolom tidak ada di file data: {', '.join(unknown)}",
        )

    filename_field = (
        req.filename_field if req.filename_field in mapping else next(iter(mapping))
    )
    job = start_job(cfg, storage.template_dir(template_id), df, mapping, filename_field)
    return job.public()


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")
    return job.public()


@app.get("/api/jobs/{job_id}/download")
def api_job_download(job_id: str):
    job = get_job(job_id)
    if (
        not job
        or job.status != "done"
        or not job.zip_path
        or not os.path.isfile(job.zip_path)
    ):
        raise HTTPException(status_code=404, detail="File belum siap.")
    return FileResponse(
        job.zip_path,
        media_type="application/zip",
        filename=job.download_name,
    )


# ----------------------------- split PDF --------------------------


@app.post("/api/split/upload")
async def api_split_upload(
    pdf: UploadFile = File(...),
    data: Optional[UploadFile] = File(None),
):
    pdf_bytes = await pdf.read()
    _check_size(pdf_bytes)
    if not (pdf.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Berkas utama harus PDF.")
    try:
        pages = count_pages(pdf_bytes)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"PDF tidak bisa dibaca: {exc}")
    if pages == 0:
        raise HTTPException(status_code=400, detail="PDF tidak punya halaman.")

    token = secrets.token_hex(16)
    with open(os.path.join(settings.tmp_dir, f"{token}.pdf"), "wb") as handle:
        handle.write(pdf_bytes)

    result = {
        "token": token,
        "pdf_pages": pages,
        "data_rows": None,
        "data_columns": [],
        "data_sample": [],
    }

    if data is not None and (data.filename or "").strip():
        raw = await data.read()
        _check_size(raw)
        df = _ingest_table(data, raw)
        _save_table(os.path.join(settings.tmp_dir, f"{token}.data.json"), df)
        summary = _table_summary(df)
        result["data_rows"] = summary["rows"]
        result["data_columns"] = summary["columns"]
        result["data_sample"] = summary["sample"]

    return result


def _split_pdf_path(token: str) -> str:
    path = os.path.join(settings.tmp_dir, f"{token}.pdf")
    if not os.path.isfile(path):
        raise HTTPException(
            status_code=400, detail="Berkas PDF kedaluwarsa / tidak ditemukan. Upload ulang."
        )
    return path


@app.post("/api/split/preview-names")
def api_split_preview_names(req: SplitPreviewRequest):
    with open(_split_pdf_path(req.token), "rb") as handle:
        pdf_bytes = handle.read()
    try:
        return preview_names(
            pdf_bytes,
            req.pages_per_doc,
            req.text_anchor,
            req.text_regex,
            req.filename_prefix or "",
            req.start_number,
            max(1, min(req.limit, 50)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/split/run")
def api_split_run(req: SplitRequest):
    pdf_path = _split_pdf_path(req.token)
    data_path = os.path.join(settings.tmp_dir, f"{req.token}.data.json")
    has_data = os.path.isfile(data_path)

    source = req.name_source or ("data" if (has_data and req.name_column) else "sequence")

    names = None
    name_from_text = False
    if source == "data":
        if not has_data:
            raise HTTPException(status_code=400, detail="Daftar nama (Excel/CSV) belum diunggah.")
        df = _load_table(data_path)
        column = req.name_column
        if not column or column not in df.columns:
            raise HTTPException(
                status_code=400, detail="Kolom nama belum dipilih / tidak ada di file."
            )
        names = [cell_to_str(value) for value in df[column].tolist()]
    elif source == "pdf_text":
        name_from_text = True
    elif source != "sequence":
        raise HTTPException(status_code=400, detail=f"Sumber nama tidak dikenal: {source}")

    job = start_split_job(
        pdf_path,
        {
            "names": names,
            "pages_per_doc": req.pages_per_doc,
            "filename_prefix": req.filename_prefix or "",  # spasi di akhir sengaja dipertahankan
            "start_number": req.start_number,
            "name_from_text": name_from_text,
            "text_anchor": req.text_anchor,
            "text_regex": req.text_regex,
        },
    )
    return job.public()
