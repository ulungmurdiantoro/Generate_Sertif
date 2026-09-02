# Panduan Deploy ke VPS

Target setup: **Debian 13 + Docker sudah terpasang + akses lewat domain + HTTPS**.
Kode diambil lewat **git clone dari GitHub**.

Stack yang dijalankan `docker compose`:

```
Internet ──▶ caddy (port 80/443, HTTPS otomatis) ──▶ app (FastAPI, port 8000) ──▶ /data (volume)
```

---

## Bagian A — Naikkan kode ke GitHub (dari komputer Windows ini)

Repo git lokal sudah siap (branch `main`, semua file ter-commit). Tinggal buat
repo kosong di GitHub lalu push.

1. Buka <https://github.com/new>
   - **Repository name:** `generator-sertifikat` (bebas)
   - **Visibility:** *Private* (disarankan) atau *Public*
   - **JANGAN** centang "Add a README / .gitignore / license" (biarkan kosong)
   - Klik **Create repository**

2. Di PowerShell, dari folder proyek:

   ```powershell
   cd c:\Users\umurd\Downloads\Generate_Sertif
   git remote add origin https://github.com/<USERNAME>/generator-sertifikat.git
   git push -u origin main
   ```

   Saat diminta login, akan muncul jendela browser GitHub (Git Credential
   Manager) — login sekali, selesai. (Kalau diminta password manual: buat
   **Personal Access Token** di <https://github.com/settings/tokens> dengan
   scope `repo`, lalu tempel token itu sebagai password.)

3. Cek: refresh halaman repo di GitHub, semua file harus muncul.

> **Aman?** `.env`, folder `data/`, dan `.venv/` sudah masuk `.gitignore` — tidak
> ikut ter-push. Password Basic Auth kamu isi nanti langsung di VPS.

**Update ke depannya:** tiap ada perubahan → `git add -A && git commit -m "..." && git push`.

---

## Bagian B — Siapkan VPS

### B1. Arahkan domain ke VPS (lakukan lebih dulu — perlu waktu propagasi)

Di panel DNS domainmu, buat **A record**:

| Type | Name | Value |
|---|---|---|
| A | `sertif` (atau `@` untuk domain utama) | `<IP-PUBLIK-VPS>` |

Cek dari komputer: `nslookup sertif.sistemedu.com` harus mengembalikan IP VPS.
Biasanya 1–30 menit. HTTPS **tidak akan terbit** sebelum DNS benar.

### B2. Login ke VPS & cek prasyarat

```bash
ssh user@<IP-VPS>

docker --version
docker compose version          # harus v2.x
```

### B3. Buka firewall & pastikan port 80/443 kosong

```bash
# Pastikan tidak ada Apache/nginx lain yang memakai port 80/443:
sudo ss -tlnp | grep -E ':80|:443' || echo "port 80/443 bebas — bagus"

# Kalau ada apache2/nginx bawaan, matikan:
# sudo systemctl disable --now apache2 nginx

# Firewall (kalau pakai ufw):
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status
```

> Kalau VPS pakai firewall dari panel provider (Security Group), buka juga
> port **80** dan **443** di sana.

### B4. Clone kode

```bash
cd ~
git clone https://github.com/<USERNAME>/generator-sertifikat.git
cd generator-sertifikat
```

(Repo private → login sama seperti Bagian A, atau pakai deploy key / PAT.)

### B5. Konfigurasi `.env`

```bash
cp .env.example .env
nano .env
```

Isi minimal:

```ini
DOMAIN=sertif.sistemedu.com          # domain dari B1 — HTTPS otomatis
BASIC_AUTH_USER=admin               # ganti
BASIC_AUTH_PASS=passwordKuatDisini  # ganti — ini gerbang aplikasi
RENDER_WORKERS=2                    # kira-kira sebanyak vCPU
MAX_UPLOAD_MB=25
MAX_ROWS=5000
JOB_RETENTION_MIN=120
```

Simpan: `Ctrl+O`, `Enter`, `Ctrl+X`.

### B6. Jalankan

```bash
docker compose up -d --build
```

Pertama kali agak lama (build image + tarik Caddy). Lalu:

```bash
docker compose ps                   # app & caddy harus "running"/"healthy"
docker compose logs -f caddy        # lihat proses ambil sertifikat SSL
```

Di log Caddy cari baris seperti `certificate obtained successfully` untuk
domainmu. `Ctrl+C` untuk berhenti melihat log (container tetap jalan).

### B7. Tes

Buka `https://sertif.sistemedu.com` di browser → muncul prompt login
(Basic Auth) → masukkan `BASIC_AUTH_USER` / `BASIC_AUTH_PASS` → halaman
**Generate** tampil. Selesai. 🎉

Cek gembok HTTPS di address bar. `http://` otomatis dialihkan ke `https://`.

---

## Bagian C — Operasional harian

| Tugas | Perintah (dari folder `generator-sertifikat` di VPS) |
|---|---|
| Lihat status | `docker compose ps` |
| Lihat log aplikasi | `docker compose logs -f app` |
| Restart | `docker compose restart` |
| Berhenti (data aman) | `docker compose down` |
| Nyalakan lagi | `docker compose up -d` |
| **Update ke versi terbaru** | `git pull && docker compose up -d --build` |
| Bersihkan image lama | `docker image prune -f` |

### Backup

Yang perlu dibackup hanya folder **`data/`** (semua template, background, font).

```bash
tar czf ~/backup-sertif-$(date +%F).tar.gz -C ~/generator-sertifikat data
```

Restore: hentikan stack, ekstrak `data/` kembali ke folder proyek, `up -d` lagi.

Sertifikat HTTPS ada di volume Docker `generator-sertifikat_caddy_data` — tidak
wajib dibackup (Caddy akan minta ulang otomatis).

---

## Bagian D — Kalau bermasalah

**HTTPS gagal / "your connection is not private"**
- DNS belum mengarah ke IP VPS → cek `dig sertif.sistemedu.com +short`.
- Port 80 tertutup / dipakai proses lain → cek B3. Caddy butuh port 80 untuk
  verifikasi Let's Encrypt.
- Terlalu sering coba → kena rate-limit Let's Encrypt (tunggu ~1 jam).
- Lihat detail: `docker compose logs caddy | tail -50`.

**502 / 503 Bad Gateway**
- Container `app` belum siap atau crash → `docker compose logs app`.
- Setelah `git pull` besar, rebuild: `docker compose up -d --build`.

**Upload ditolak / "Request Entity Too Large"**
- Naikkan `MAX_UPLOAD_MB` di `.env` **dan** angka `max_size` di `Caddyfile`,
  lalu `docker compose up -d`.

**Generate lama / timeout untuk ratusan peserta**
- Naikkan `RENDER_WORKERS` di `.env` sesuai jumlah vCPU, `docker compose up -d`.
- Proses Generate memang berjalan sebagai job dengan progress bar; biarkan
  tab terbuka sampai tombol **Unduh ZIP** muncul.

**Permission denied menulis `/data`**
- Sudah ditangani entrypoint (`chown` otomatis). Kalau masih terjadi:
  `sudo chown -R 1000:1000 ~/generator-sertifikat/data && docker compose restart`.

**Disk penuh**
- `docker system df` untuk melihat pemakaian; `docker image prune -a -f`.
- Hasil ZIP & upload sementara auto-terhapus tiap `JOB_RETENTION_MIN` menit.

---

## Catatan keamanan

- **Selalu isi `BASIC_AUTH_USER` / `BASIC_AUTH_PASS`** — tanpa itu siapa pun yang
  tahu URL bisa memakai (dan membebani) server.
- Jalankan aplikasi sebagai user biasa + `sudo`, jangan login root harian.
- Update berkala: `git pull && docker compose up -d --build` lalu
  `docker image prune -f`.
