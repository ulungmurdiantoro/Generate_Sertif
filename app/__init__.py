"""Generator Sertifikat - versi web (FastAPI).

Logika render diambil dari `generate_sertifikat.py` (skrip acuan) lalu
digeneralisasi supaya:
  * template (background + font + posisi teks) bisa diatur lewat UI,
  * data peserta di-upload (xlsx/xls/csv),
  * hasil di-download sebagai satu file ZIP berisi PDF per peserta.
"""

__all__ = ["__version__"]
__version__ = "1.0.0"
