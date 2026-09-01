import pandas as pd
from pypdf import PdfReader, PdfWriter
import os
import re

# File
pdf_file = "SERTIF.pdf"
excel_file = "Sertif.xlsx"

# Folder output
output_dir = "hasil_sertifikat"
os.makedirs(output_dir, exist_ok=True)

# Baca PDF
reader = PdfReader(pdf_file)

# Baca Excel
df = pd.read_excel(excel_file)

# Validasi jumlah halaman
if len(reader.pages) != len(df):
    print(
        f"Jumlah halaman PDF ({len(reader.pages)}) "
        f"tidak sama dengan jumlah peserta ({len(df)})"
    )
    exit()

def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", str(name))

# Pisahkan PDF
for i, row in df.iterrows():
    nama = clean_filename(row['Nama'])

    writer = PdfWriter()
    writer.add_page(reader.pages[i])

    output_file = os.path.join(
        output_dir,
        f"{nama}.pdf"
    )

    with open(output_file, "wb") as f:
        writer.write(f)

    print(f"Berhasil: {nama}.pdf")

print("Selesai!")