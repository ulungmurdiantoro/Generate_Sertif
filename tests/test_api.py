import io
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from conftest import make_pdf, make_text_pdf

client = TestClient(app)


def _wait(job: dict) -> dict:
    for _ in range(100):
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
        job = client.get(f"/api/jobs/{job['id']}").json()
    raise AssertionError("job tidak selesai")


@pytest.fixture
def template_id():
    return client.post("/api/templates").json()["id"]


# ------------------------------------------------------------- keamanan


@pytest.mark.parametrize("token", [
    "../templates/x/fonts/evil",
    "..%2F..%2Fetc",
    "ABCDEF0123456789ABCDEF0123456789",
    "0" * 31,
])
def test_path_like_tokens_are_rejected(token):
    assert client.post("/api/split/preview-names", json={"token": token}).status_code == 422
    assert client.post("/api/split/run", json={"token": token}).status_code == 422
    body = {"data_token": token, "mapping": {"nama": "nama"}}
    assert client.post("/api/templates/abc/generate", json=body).status_code == 422


def test_font_upload_rejects_non_font(template_id):
    url = f"/api/templates/{template_id}/assets"
    res = client.post(url, data={"kind": "font"}, files={"file": ("evil.pkl", b"x")})
    assert res.status_code == 400
    res = client.post(url, data={"kind": "font"}, files={"file": ("fake.ttf", b"not a font")})
    assert res.status_code == 400


def test_font_upload_accepts_real_font(template_id, font_factory):
    font = font_factory("abc")
    res = client.post(
        f"/api/templates/{template_id}/assets",
        data={"kind": "font"},
        files={"file": ("real.ttf", font.read_bytes())},
    )
    assert res.status_code == 200
    assert "real.ttf" in res.json()["fonts"]


def test_template_rejects_absurd_canvas(template_id):
    res = client.put(f"/api/templates/{template_id}", json={"canvas_width": 0.001})
    assert res.status_code == 422


# ------------------------------------------------------------- data upload


@pytest.mark.parametrize("encoding", ["cp1252", "utf-8-sig", "utf-8"])
def test_csv_apostrophe_survives_excel_encodings(template_id, encoding):
    csv = "nama,nilai\nMa’ruf Amin,90\nO'Brien,85.0\n".encode(encoding)
    res = client.post(
        f"/api/templates/{template_id}/data", files={"file": ("peserta.csv", csv)}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["columns"] == ["nama", "nilai"]
    assert body["sample"][0]["nama"] == "Ma’ruf Amin"
    assert body["sample"][1] == {"nama": "O'Brien", "nilai": "85"}


# ------------------------------------------------------------- split


def test_split_runs_as_job_and_downloads_zip():
    pdf = make_text_pdf([["Diberikan kepada:", "Budi"], ["Diberikan kepada:", "Siti"]])
    up = client.post("/api/split/upload", files={"pdf": ("gabungan.pdf", pdf)}).json()

    job = client.post(
        "/api/split/run",
        json={"token": up["token"], "name_source": "pdf_text", "text_anchor": "Diberikan kepada"},
    ).json()
    job = _wait(job)
    assert job["status"] == "done", job

    res = client.get(job["download_url"])
    assert res.status_code == 200
    with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
        assert sorted(archive.namelist()) == ["Budi.pdf", "Siti.pdf"]


def test_split_with_name_list_from_csv():
    csv = "nama\nMa’ruf\nO'Brien\n".encode("cp1252")
    up = client.post(
        "/api/split/upload",
        files={"pdf": ("g.pdf", make_pdf(2)), "data": ("n.csv", csv)},
    ).json()
    job = _wait(client.post(
        "/api/split/run",
        json={"token": up["token"], "name_source": "data", "name_column": "nama"},
    ).json())
    assert job["status"] == "done", job
    with zipfile.ZipFile(io.BytesIO(client.get(job["download_url"]).content)) as archive:
        assert sorted(archive.namelist()) == ["Ma’ruf.pdf", "O'Brien.pdf"]


def test_split_error_is_reported_on_job():
    up = client.post("/api/split/upload", files={"pdf": ("g.pdf", make_pdf(3))}).json()
    job = _wait(client.post("/api/split/run", json={"token": up["token"], "pages_per_doc": 2}).json())
    assert job["status"] == "error"
    assert "tidak habis dibagi" in job["message"]
