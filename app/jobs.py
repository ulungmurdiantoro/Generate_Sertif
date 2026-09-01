from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

import pandas as pd

from .config import get_settings
from .models import TemplateConfig
from .renderer import cell_to_str, clean_filename, render_pages, save_pdf, unique_name


@dataclass
class Job:
    id: str
    template_id: str
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


def start_job(
    cfg: TemplateConfig,
    template_dir: str,
    df: pd.DataFrame,
    mapping: Dict[str, str],
    filename_field: str,
) -> Job:
    job = Job(id=uuid.uuid4().hex[:12], template_id=cfg.id, total=len(df))
    JOBS[job.id] = job
    worker = threading.Thread(
        target=_run,
        args=(job, cfg, template_dir, df, mapping, filename_field),
        daemon=True,
    )
    worker.start()
    return job


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
    """Hapus ZIP hasil & file data upload yang sudah lewat masa retensi."""
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

    if os.path.isdir(settings.tmp_dir):
        for name in os.listdir(settings.tmp_dir):
            path = os.path.join(settings.tmp_dir, name)
            try:
                if now - os.path.getmtime(path) > ttl:
                    os.remove(path)
            except OSError:
                pass
