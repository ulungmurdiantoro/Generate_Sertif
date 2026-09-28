# Generator Sertifikat (versi web / VPS)

Versi web dari `generate_sertifikat.py` **dan** `split_sertifikat.py`. Kedua skrip
asli tetap ada dan tidak diubah — dipakai sebagai **acuan logika**.

Dua menu:

| Menu | Acuan | Fungsi |
|---|---|---|
| **Generate** | `generate_sertifikat.py` | Cetak nama + nomor dll ke atas background (Pillow + skala Canva), hasil ZIP berisi 1 PDF per peserta. |
| **Split PDF** | `split_sertifikat.py` | Pecah 1 PDF gabungan menjadi banyak PDF, 1 berkas per peserta. |

---

## Fitur

### Menu Generate

- **Multi-template** — simpan banyak desain sertifikat, tiap template punya
  background depan (wajib), background belakang (opsional), font, dan daftar
  field teks.
- **Atur posisi lewat UI** — tiap field: key, halaman (1/2), perataan, posisi
  X/Y (satuan pt seperti di Canva), ukuran font, ukuran minimum + lebar maks
  (auto-mengecil bila teks kepanjangan, sama seperti skrip asli), warna, contoh
  nilai.
- **Pratinjau langsung** — render halaman 1 / 2 dengan nilai contoh.
- **Upload data** `.xlsx` / `.xls` / `.csv`, pemetaan kolom otomatis (bisa
  dikoreksi manual), dan pilih kolom untuk nama file PDF.
- **Progress bar** saat generate, lalu unduh ZIP.

### Menu Split PDF

- Upload 1 **PDF gabungan** + (opsional) daftar nama `.xlsx` / `.xls` / `.csv`.
- **Halaman per dokumen** bisa >1 (mis. sertifikat 2 halaman) — pengembangan
  dari skrip asli yang hanya 1 halaman/peserta.
- **Sumber nama berkas** (3 pilihan):
  1. **Nomor urut** — `001.pdf`, `002.pdf`, … (tanpa perlu Excel).
  2. **Kolom Excel/CSV** — pilih kolom mana pun (bukan hanya `Nama`).
  3. **Teks di dalam PDF** — ambil nama yang sudah tercetak di tiap halaman,
     **tanpa Excel**. Cocok bila teks PDF bisa diseleksi/di-copy (mis. hasil
     mail-merge Word). Nama diambil dari teks setelah **frasa penanda**
     (default: `Diberikan kepada`) atau lewat **regex**. Tombol *Coba baca
     nama* menampilkan pratinjau 10 dokumen pertama untuk mengecek sebelum
     dijalankan. Halaman yang gagal dibaca dinamai `TIDAK-TERBACA-00n.pdf` dan
     didaftar di `_TIDAK-TERBACA.txt` di dalam ZIP.
     > PDF berupa gambar (scan / export Canva / hasil menu Generate) **tidak
     > punya teks** — mode ini akan ditolak dengan pesan jelas; pakai Excel
     > atau nomor urut.
- **Awalan nama berkas** opsional (mis. `Sertifikat - `).
- Validasi otomatis: jumlah halaman harus habis dibagi, dan cocok dengan jumlah
  nama. Nama berkas bentrok diberi ` (2)`, ` (3)`, … (skrip asli menimpa diam-diam).

### Umum

- **Basic Auth opsional** untuk melindungi endpoint di VPS publik.
- **Auto cleanup** — ZIP hasil & file upload dihapus otomatis setelah
  `JOB_RETENTION_MIN` menit.

---

## Struktur proyek

```
Generate_Sertif/
├─ generate_sertifikat.py     # skrip CLI asli (acuan menu Generate)
├─ split_sertifikat.py        # skrip CLI asli (acuan menu Split PDF)
├─ app/
│  ├─ main.py                 # FastAPI: routing + API
│  ├─ config.py               # setting via .env
│  ├─ models.py               # skema TemplateConfig / TextField / SplitRequest
│  ├─ storage.py              # simpan template + aset ke folder data/
│  ├─ renderer.py             # inti render (porting generate_sertifikat.py)
│  ├─ jobs.py                 # job generate + zip + cleanup
│  ├─ splitter.py             # inti split PDF (porting split_sertifikat.py)
│  ├─ templates/              # HTML (Jinja2): index, editor, generate, split
│  └─ static/                 # app.css, app.js
├─ data/                      # runtime (template, tmp, output) — dibuat otomatis
├─ requirements.txt
├─ Dockerfile
├─ docker-compose.yml       # app + Caddy (reverse proxy + HTTPS otomatis)
├─ Caddyfile
├─ nginx/nginx.conf         # opsional — kalau sudah punya reverse proxy sendiri
├─ DEPLOY.md                # runbook deploy ke VPS (Debian + Docker + domain)
└─ .env.example
```

Pemetaan dari skrip asli:

| Di `generate_sertifikat.py` | Di menu **Generate** |
|---|---|
| `EXCEL_FILE` | Upload file di halaman Generate |
| `BG_DEPAN` / `BG_BELAKANG` | Upload aset di Editor |
| `FONT_NAMA_*` / `FONT_NOMOR_*` | Upload font di Editor, pilih per field |
| `CANVA_POS_*`, `FONT_SIZE_*_CANVA`, `CANVA_MAX_NAMA_WIDTH` | Kolom X/Y, Ukuran Font, Ukuran Min, Lebar Maks per field |
| `COLOR_TEXT` | Kolom Warna per field |
| `OUTPUT_DIR` | Otomatis jadi ZIP yang bisa diunduh |

| Di `split_sertifikat.py` | Di menu **Split PDF** |
|---|---|
| `pdf_file = "SERTIF.pdf"` | Upload "PDF gabungan" |
| `excel_file = "Sertif.xlsx"` | Upload "Daftar nama" (opsional — bisa dilewati) |
| `row['Nama']` | "Sumber nama berkas": nomor urut / kolom bebas / **teks di dalam PDF** |
| cek `len(pages) != len(df)` lalu `exit()` | Validasi di UI + pesan error jelas, plus opsi **halaman per dokumen** |
| `clean_filename` | Sama, + anti-bentrok ` (2)`, ` (3)`, … |
| `output_dir` | Otomatis jadi ZIP yang bisa diunduh |

---

## Jalankan lokal (untuk uji coba)

Butuh Python 3.11+.

```powershell
cd c:\Users\umurd\Downloads\Generate_Sertif
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Buka <http://127.0.0.1:8000>.

Menjalankan test:

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

---

## Deploy ke VPS dengan Docker (disarankan)

**Panduan lengkap langkah demi langkah ada di [`DEPLOY.md`](DEPLOY.md).** Ringkasnya:

Prasyarat di VPS (Ubuntu/Debian): Docker Engine + plugin Docker Compose.

```bash
# 1. Ambil kode
git clone <URL-REPO-GITHUB> generator-sertifikat
cd generator-sertifikat

# 2. Siapkan konfigurasi
cp .env.example .env
nano .env
#   - WAJIB isi BASIC_AUTH_USER + BASIC_AUTH_PASS untuk server publik
#   - DOMAIN=sertif.contoh.com  (HTTPS otomatis)  ATAU  DOMAIN=:80  (akses via IP)
#   - RENDER_WORKERS ≈ jumlah vCPU

# 3. Build & jalankan
docker compose up -d --build

# 4. Cek
docker compose ps
docker compose logs -f
```

Stack yang jalan: **app** (FastAPI, port internal 8000) + **caddy** (reverse proxy,
port 80/443, HTTPS Let's Encrypt otomatis bila `DOMAIN` berupa nama domain).

**Update versi:**

```bash
git pull
docker compose up -d --build
```

**Backup:** arsipkan folder `data/` (semua template + aset). Sertifikat HTTPS
tersimpan di volume `caddy_data`. `docker compose down` tidak menghapus keduanya.

---

## Deploy native tanpa Docker (alternatif)

```bash
python3 -m venv /opt/gensertif/venv
/opt/gensertif/venv/bin/pip install -r requirements.txt
```

`/etc/systemd/system/gensertif.service`:

```ini
[Unit]
Description=Generator Sertifikat
After=network.target

[Service]
WorkingDirectory=/opt/gensertif
EnvironmentFile=/opt/gensertif/.env
ExecStart=/opt/gensertif/venv/bin/gunicorn -k uvicorn.workers.UvicornWorker \
          -w 1 -b 127.0.0.1:8000 --timeout 600 app.main:app
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable --now gensertif
```

Lalu reverse proxy nginx di host (`proxy_pass http://127.0.0.1:8000;`,
`client_max_body_size 30m;`, `proxy_read_timeout 600s;`).

> Jalankan **1 worker** saja (`-w 1`). Status job disimpan di memori proses;
> banyak worker butuh Redis/broker (di luar cakupan). Untuk mempercepat render,
> naikkan `RENDER_WORKERS` (thread di dalam worker).

---

## Cara pakai (alur di UI)

### Menu Generate

1. **Generate → + Template Baru.** Template contoh sudah berisi 2 field:
   `nama` (rata tengah, 36→29 pt, lebar maks 550) dan `nomor` (kiri, 12 pt,
   halaman 1 & 2) — persis default skrip asli.
2. **Editor:**
   - Set *Lebar Kanvas* = lebar desain Canva (A4 landscape → 842).
   - Upload *Background Depan* (dan *Belakang* bila 2 halaman) di bagian **Aset**.
   - Di tiap **Field Teks**, upload font lewat kolom *Upload font baru*
     (`RoxboroughCF-Regular.ttf`, `Garet-Book.otf`, dst.) — font otomatis
     terpilih untuk field itu dan tersedia juga di dropdown *Font* field lain.
     Daftar font terpasang + tombol hapus ada di foldout *Font terpasang di
     template*.
   - Rapikan X/Y/ukuran, tekan **↻** untuk pratinjau (kartu pratinjau kini lebih
     besar). **Simpan.**
3. **Generate:**
   - Upload Excel/CSV peserta.
   - Cek pemetaan kolom (mis. `nama → "Nama Peserta"`, `nomor → "Nomor sertif"`).
   - Pilih kolom nama file PDF (default: field pertama).
   - **Generate & Buat ZIP** → tunggu progress → **Unduh ZIP.**

### Menu Split PDF

1. Buka **Split PDF**.
2. **Upload Berkas:** pilih PDF gabungan; (opsional) pilih Excel/CSV daftar nama.
   Klik **Periksa** → muncul jumlah halaman & jumlah baris.
3. **Opsi:**
   - *Halaman per dokumen* — 1 untuk sertifikat 1 halaman, 2 untuk 2 halaman, dst.
   - *Sumber nama berkas* — **Nomor urut** / **Kolom Excel/CSV** / **Teks di
     dalam PDF**.
   - *Kolom nama berkas* — muncul bila sumber = kolom Excel/CSV.
   - *Frasa penanda* / *Regex* + tombol *Coba baca nama* — muncul bila sumber =
     teks di dalam PDF.
   - *Awalan nama berkas* — opsional, mis. `Sertifikat - `.
   - *Mulai nomor urut dari* — dipakai untuk mode nomor urut / penanda gagal baca.
   - Baris info akan menandai bila jumlah **tidak cocok**.
4. **Pisahkan & Unduh ZIP.**

> **Tanpa Excel tapi ingin nama file = nama di sertifikat:** pilih sumber
> **Teks di dalam PDF**, pastikan *Frasa penanda* sesuai kalimat sebelum nama
> di sertifikatmu (mis. `Diberikan kepada`, `Diberikan kepada:`), klik
> *Coba baca nama* untuk memverifikasi, lalu jalankan.

---

## Konfigurasi (.env)

| Variabel | Default | Keterangan |
|---|---|---|
| `APP_NAME` | Generator Sertifikat | Judul di UI |
| `DATA_DIR` | `./data` | Folder data (Docker memaksa `/data`) |
| `MAX_UPLOAD_MB` | `300` | Batas ukuran tiap upload |
| `MAX_ROWS` | `5000` | Batas baris peserta per generate |
| `RENDER_WORKERS` | `4` | Thread render paralel |
| `JOB_RETENTION_MIN` | `120` | Umur simpan ZIP hasil & data upload |
| `BASIC_AUTH_USER` / `BASIC_AUTH_PASS` | kosong | Proteksi Basic Auth (isi untuk VPS publik) |
| `DOMAIN` | `:80` | Domain untuk Caddy. Nama domain → HTTPS otomatis; `:80` → HTTP saja |
| `FALLBACK_FONTS` | kosong | Path font fallback tambahan (dipisah koma) |

---

## Catatan teknis

- Render mengikuti skrip asli: `scale = lebar_png / canvas_width`, semua ukuran
  pt dikali `scale`. Pastikan rasio PNG background = rasio kanvas agar posisi
  vertikal pas.
- Endpoint utama: `GET /` (menu Generate), `GET /split` (menu Split PDF),
  `GET /docs` (OpenAPI), `GET /healthz` (tanpa auth).
- Split PDF berjalan sebagai job di background (sama seperti Generate): hasilnya
  ditulis langsung ke ZIP di `data/output/`, lalu dipantau lewat `GET /api/jobs/{id}`.
  PDF yang di-upload disimpan sementara di `data/tmp/`; keduanya ikut dibersihkan
  oleh auto-cleanup.
- Mode "Teks di dalam PDF" memakai `pypdf.extract_text()` — hanya untuk PDF
  yang punya lapisan teks (bukan hasil scan/gambar). Tidak ada OCR. Teks dengan
  letter-spacing lebar (`T H I S  C E R T ...`) otomatis dirapikan dulu.
  Regex tidak memakai DOTALL: `(.+)` berhenti di akhir baris.
  Endpoint: `POST /api/split/preview-names` (pratinjau), `POST /api/split/run`.
- Karakter yang tidak ada glyph-nya di font (mis. apostrof ’ dari Excel pada font
  dekoratif) diganti padanan ASCII-nya (`'`) supaya tidak tercetak kotak.
- CSV dibaca sebagai UTF-8 (dengan/tanpa BOM), lalu cp1252 (CSV bawaan Excel Windows).
- Format PDF Generate: 1 halaman bila hanya ada background depan, 2 halaman bila
  ada background belakang.
