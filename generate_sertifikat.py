import os
import re
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm

# ==========================================
# KONFIGURASI FILE & FOLDER
# ==========================================
EXCEL_FILE = "Book2.xlsx"          # File data peserta
BG_DEPAN = "depan-1.png"             # Background halaman 1
BG_BELAKANG = "belakang-1.png"       # Background halaman 2
OUTPUT_DIR = "25-28 agustus 2026"  # Folder output PDF per peserta

# Kolom Excel yang digunakan
COL_NAMA = "Nama Peserta"
COL_NOMOR = "Nomor sertif"

# ==========================================
# KONFIGURASI FONT (Garet & RoxboroughCF)
# ==========================================
# 1. Font Nama Peserta: RoxboroughCF
FONT_NAMA_PRIMARY = "fonts/RoxboroughCF-Regular.ttf"
FONT_NAMA_FALLBACK = os.path.expandvars("%LOCALAPPDATA%/Microsoft/Windows/Fonts/Roxborough CF.ttf")

# 2. Font Nomor Sertifikat: Garet
FONT_NOMOR_PRIMARY = "fonts/Garet-Book.otf"
FONT_NOMOR_FALLBACK = "C:/Windows/Fonts/calibri.ttf"

# ==========================================
# UKURAN & POSISI SESUAI CANVA (Satuan: pt)
# ==========================================
# Lebar standar kanvas Canva A4 Landscape (842 x 595 pt)
CANVA_PAGE_WIDTH = 842.0

# Ukuran Font di Canva (pt)
FONT_SIZE_NOMOR_CANVA = 12       # Ukuran font nomor di Canva (12 pt)
FONT_SIZE_NAMA_CANVA = 36        # Ukuran font nama di Canva (36 pt)
FONT_SIZE_NAMA_MIN_CANVA = 29    # Batas ukuran font nama minimal (29 pt)

# Posisi Koordinat di Canva (pt)
# 1. Nomor Sertifikat (Halaman 1 & 2)
CANVA_POS_NOMOR_X = 122          # Posisi X setelah teks "Nomor: "
CANVA_POS_NOMOR_Y = 75           # Posisi Y nomor

# 2. Nama Peserta (Halaman 1)
CANVA_POS_NAMA_Y = 258           # Posisi vertikal nama (di atas garis tengah)
CANVA_MAX_NAMA_WIDTH = 550       # Lebar maksimal area nama sebelum font mengecil (pt)

# Warna Teks (R, G, B)
COLOR_TEXT = (25, 25, 25)        # Hitam pekat elegan

# ==========================================
# FUNGSI HELPER
# ==========================================
def clean_filename(text):
    """Menghapus karakter yang tidak diperbolehkan pada nama file di Windows"""
    return re.sub(r'[\\/*?:"<>|]', "", str(text)).strip()

def resolve_font_path(primary, fallback):
    """Memilih path font yang tersedia"""
    if os.path.exists(primary):
        return primary
    elif os.path.exists(fallback):
        return fallback
    return "C:/Windows/Fonts/arial.ttf"

def get_fitted_font(draw, text, font_path, max_size_pt, min_size_pt, max_width_px, scale):
    """Menghitung ukuran font agar teks pas di area sertifikat"""
    size_pt = max_size_pt
    size_px = int(round(size_pt * scale))
    font = ImageFont.truetype(font_path, size_px)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    
    while text_width > max_width_px and size_pt > min_size_pt:
        size_pt -= 1
        size_px = int(round(size_pt * scale))
        font = ImageFont.truetype(font_path, size_px)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        
    return font, text_width

# ==========================================
# PROSES UTAMA GENERATE SERTIFIKAT
# ==========================================
def generate_certificates():
    # 1. Validasi keberadaan file background & excel
    for f in [EXCEL_FILE, BG_DEPAN, BG_BELAKANG]:
        if not os.path.exists(f):
            print(f"[ERROR] File '{f}' tidak ditemukan!")
            return

    # Tentukan path font yang digunakan
    font_nama_file = resolve_font_path(FONT_NAMA_PRIMARY, FONT_NAMA_FALLBACK)
    font_nomor_file = resolve_font_path(FONT_NOMOR_PRIMARY, FONT_NOMOR_FALLBACK)

    print(f"[*] Font Nama Peserta : {os.path.basename(font_nama_file)} ({FONT_SIZE_NAMA_CANVA} pt Canva)")
    print(f"[*] Font No Sertifikat: {os.path.basename(font_nomor_file)} ({FONT_SIZE_NOMOR_CANVA} pt Canva)")

    # 2. Buat folder output
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 3. Baca Data Excel
    df = pd.read_excel(EXCEL_FILE)
    
    col_nama = COL_NAMA if COL_NAMA in df.columns else df.columns[0]
    col_nomor = COL_NOMOR if COL_NOMOR in df.columns else df.columns[1]

    print(f"[*] Menemukan {len(df)} data peserta.")
    print(f"[*] Kolom Nama : '{col_nama}'")
    print(f"[*] Kolom Nomor: '{col_nomor}'")
    print(f"[*] Memulai generate sertifikat ke folder '{OUTPUT_DIR}'...\n")

    # 4. Loop setiap peserta
    sukses = 0
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Proses Generate"):
        nama = str(row[col_nama]).strip()
        nomor = str(row[col_nomor]).strip()

        if not nama or nama.lower() == 'nan':
            continue

        # --- HALAMAN 1 (DEPAN) ---
        img1 = Image.open(BG_DEPAN).convert("RGB")
        draw1 = ImageDraw.Draw(img1)
        img_w, _ = img1.size

        # Hitung faktor skala dari Canva (pt) ke gambar PNG (px)
        scale = img_w / CANVA_PAGE_WIDTH
        
        # Font & posisi nomor sertifikat
        px_font_nomor = int(round(FONT_SIZE_NOMOR_CANVA * scale))
        font_nomor = ImageFont.truetype(font_nomor_file, px_font_nomor)
        pos_nomor_x = int(round(CANVA_POS_NOMOR_X * scale))
        pos_nomor_y = int(round(CANVA_POS_NOMOR_Y * scale))

        # Tulis Nomor Sertifikat di Halaman 1 (Garet)
        draw1.text((pos_nomor_x, pos_nomor_y), nomor, fill=COLOR_TEXT, font=font_nomor)

        # Tulis Nama Peserta (RoxboroughCF, Maks 36 pt, Min 29 pt Canva, Rata Tengah Horizontal)
        max_nama_width_px = CANVA_MAX_NAMA_WIDTH * scale
        font_nama, text_width = get_fitted_font(
            draw1, nama, font_nama_file, 
            FONT_SIZE_NAMA_CANVA, FONT_SIZE_NAMA_MIN_CANVA, max_nama_width_px, scale
        )
        pos_nama_x = (img_w - text_width) / 2
        pos_nama_y = int(round(CANVA_POS_NAMA_Y * scale))
        draw1.text((pos_nama_x, pos_nama_y), nama, fill=COLOR_TEXT, font=font_nama)

        # --- HALAMAN 2 (BELAKANG) ---
        img2 = Image.open(BG_BELAKANG).convert("RGB")
        draw2 = ImageDraw.Draw(img2)

        # Tulis Nomor Sertifikat di Halaman 2 (Garet)
        draw2.text((pos_nomor_x, pos_nomor_y), nomor, fill=COLOR_TEXT, font=font_nomor)

        # --- SIMPAN SEBAGAI PDF 2 HALAMAN ---
        nama_file_bersih = clean_filename(nama)
        output_pdf_path = os.path.join(OUTPUT_DIR, f"{nama_file_bersih}.pdf")

        img1.save(
            output_pdf_path,
            "PDF",
            resolution=150.0,
            save_all=True,
            append_images=[img2]
        )
        sukses += 1

    print(f"\n[SELESAI] Berhasil membuat {sukses} file sertifikat PDF di folder '{OUTPUT_DIR}'.")

if __name__ == "__main__":
    generate_certificates()
