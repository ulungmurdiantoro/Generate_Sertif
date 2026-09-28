from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Set

import pandas as pd

from .config import get_settings
from .models import TemplateConfig
from .renderer import cell_to_str, clean_filename, render_pages, save_pdf, unique_name
from .splitter import split_pdf


@dataclass
class Job:
    id: str
    download_name: str
    status: str = "queued"  # queued | running | done | error
    total: int = 0
    done: int = 0
    message: str = ""
    zip_path: Optional[str] = None
    created: float = field(default_factory=time.time)
    finished: Optional[float] = None

    def public(self) -> dict:
        percent = round(self.done / self.total * 100, 1) if self.total else 0.0
        return {
            "id": self.id,
            "status": self.status,
            "total": self.total,
            "done": self.done,
            "percent": percent,
            "message": self.message,
            "download_url": f"/api/jobs/{self.id}/download" if self.status == "done" else None,
        }


JOBS: Dict[str, Job] = {}
_LOCK = threading.Lock()


def get_job(job_id: str) -> Optional[Job]:
    return JOBS.get(job_id)


def _spawn(prefix: str, target: Callable[..., None], *args: Any, total: int = 0) -> Job:
    job_id = uuid.uuid4().hex[:12]
    job = Job(id=job_id, download_name=f"{prefix}_{job_id}.zip", total=total)
    JOBS[job.id] = job
    threading.Thread(target=target, args=(job, *args), daemon=True).start()
    return job


def start_job(
    cfg: TemplateConfig,
    template_dir: str,
    df: pd.DataFrame,
    mapping: Dict[str, str],
    filename_field: str,
) -> Job:
    return _spawn(
        "sertifikat", _run, cfg, template_dir, df, mapping, filename_field, total=len(df)
    )


def start_split_job(pdf_path: str, split_kwargs: Dict[str, Any]) -> Job:
    return _spawn("split", _run_split, pdf_path, split_kwargs)


def _run_split(job: Job, pdf_path: str, split_kwargs: Dict[str, Any]) -> None:
    zip_path = os.path.join(get_settings().output_dir, f"{job.id}.zip")

    def progress(done: int, total: int) -> None:
        job.done, job.total = done, total

    try:
        job.status = "running"
        with open(pdf_path, "rb") as handle:
            pdf_bytes = handle.read()
        result = split_pdf(pdf_bytes, zip_path, progress=progress, **split_kwargs)
        if result.unreadable:
            job.message = (
                f"{len(result.unreadable)} berkas namanya tidak terbaca — "
                "lihat _TIDAK-TERBACA.txt di dalam ZIP."
            )
        job.zip_path = zip_path
        job.status = "done"
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.message = str(exc)
        try:
            os.remove(zip_path)
        except OSError:
            pass
    finally:
        job.finished = time.time()


def _run(
    job: Job,
    cfg: TemplateConfig,
    template_dir: str,
    df: pd.DataFrame,
    mapping: Dict[str, str],
    filename_field: str,
) -> None:
    settings = get_settings()
    work_dir = os.path.join(settings.output_dir, job.id)
    os.makedirs(work_dir, exist_ok=True)
    used: Set[str] = set()

    try:
        job.status = "running"
        rows = list(enumerate(row for _, row in df.iterrows()))

        def process(item) -> None:
            index, row = item
            values = {key: cell_to_str(row.get(col)) for key, col in mapping.items()}
            source = values.get(filename_field) or f"sertifikat_{index + 1}"
            base = clean_filename(source) or f"sertifikat_{index + 1}"
            with _LOCK:
                name = unique_name(base, used)
            pages = render_pages(cfg, values, template_dir)
            save_pdf(pages, os.path.join(work_dir, f"{name}.pdf"), cfg.resolution)

        workers = max(1, int(settings.render_workers))
        if workers == 1:
            for item in rows:
                process(item)
                job.done += 1
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for _ in pool.map(process, rows):
                    job.done += 1

        if job.done == 0:
            raise RuntimeError("Tidak ada baris data yang bisa diproses.")

        job.zip_path = shutil.make_archive(
            os.path.join(settings.output_dir, job.id), "zip", work_dir
        )
        job.status = "done"
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.message = str(exc)
    finally:
        job.finished = time.time()
        shutil.rmtree(work_dir, ignore_errors=True)


def cleanup_old_jobs() -> None:
    """Hapus ZIP hasil & file upload yang sudah lewat masa retensi.

    File di output_dir juga disapu berdasar umur, supaya ZIP dari job yang
    hilang dari memori (mis. setelah restart) tidak menumpuk selamanya.
    """
    settings = get_settings()
    ttl = settings.job_retention_min * 60
    now = time.time()

    for job_id, job in list(JOBS.items()):
        reference = job.finished or job.created
        if now - reference > ttl:
            if job.zip_path and os.path.isfile(job.zip_path):
                try:
                    os.remove(job.zip_path)
                except OSError:
                    pass
            JOBS.pop(job_id, None)

    for directory in (settings.tmp_dir, settings.output_dir):
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            try:
                if os.path.isfile(path) and now - os.path.getmtime(path) > ttl:
                    os.remove(path)
            except OSError:
                pass
