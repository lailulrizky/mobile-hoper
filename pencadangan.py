"""Pencadangan database SQLite: aman saat aplikasi berjalan, diverifikasi, retensi bertingkat.

Nama berkas : penerimaan_YYYYmmdd_HHMMSS_<alasan>.db
Retensi     : semua cadangan 3 hari terakhir, lalu satu per hari (yang terbaru) sampai
              'simpan_hari'. Cadangan 'sebelum_upgrade' tidak pernah dihapus otomatis."""
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

POLA_NAMA = re.compile(r"^penerimaan_(\d{8}_\d{6})_([a-z_]+)\.db$")
FORMAT_WAKTU = "%Y%m%d_%H%M%S"


class Pencadangan:
    def __init__(self, db: Path, folder: Path, interval_jam: int = 4, simpan_hari: int = 60):
        self.db, self.folder = Path(db), Path(folder)
        self.interval_jam, self.simpan_hari = interval_jam, simpan_hari

    # ---- daftar & status
    def daftar(self) -> List[Path]:
        """Cadangan yang ada, terbaru dulu."""
        if not self.folder.exists():
            return []
        cocok = [p for p in self.folder.iterdir() if POLA_NAMA.match(p.name)]
        return sorted(cocok, key=lambda p: POLA_NAMA.match(p.name).group(1), reverse=True)

    @staticmethod
    def waktu_dari_nama(path: Path) -> datetime:
        return datetime.strptime(POLA_NAMA.match(path.name).group(1), FORMAT_WAKTU)

    def terakhir(self) -> Optional[datetime]:
        d = self.daftar()
        return self.waktu_dari_nama(d[0]) if d else None

    def perlu_cadangan(self, sekarang: Optional[datetime] = None) -> bool:
        t = self.terakhir()
        return t is None or (sekarang or datetime.now()) - t >= timedelta(hours=self.interval_jam)

    # ---- membuat cadangan
    def cadangkan(self, alasan: str = "otomatis") -> Path:
        """Buat cadangan yang konsisten (API backup SQLite), verifikasi, lalu simpan ke folder.
        Disalin lewat berkas sementara agar cadangan setengah jadi tidak pernah muncul."""
        if not self.db.exists():
            raise FileNotFoundError(f"Database tidak ditemukan: {self.db}")
        alasan = re.sub(r"[^a-z_]", "", alasan.lower()) or "otomatis"
        self.folder.mkdir(parents=True, exist_ok=True)
        akhir = self.folder / f"penerimaan_{datetime.now().strftime(FORMAT_WAKTU)}_{alasan}.db"
        kerja = Path(tempfile.mkdtemp(prefix="cadangan_"))
        try:
            lokal = kerja / "salinan.db"
            sumber = sqlite3.connect(self.db, timeout=30)
            try:
                tujuan = sqlite3.connect(lokal)
                try:
                    sumber.backup(tujuan)
                finally:
                    tujuan.close()
            finally:
                sumber.close()
            self.verifikasi(lokal)
            sementara = akhir.with_name(akhir.name + ".part")
            shutil.copy2(lokal, sementara)
            os.replace(sementara, akhir)
        finally:
            shutil.rmtree(kerja, ignore_errors=True)
        self.bersihkan()
        return akhir

    @staticmethod
    def verifikasi(path: Path):
        """Pastikan berkas cadangan utuh dan bisa dibuka."""
        con = sqlite3.connect(path)
        try:
            hasil = con.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            con.close()
        if hasil != "ok":
            raise RuntimeError(f"Cadangan gagal verifikasi: {hasil}")

    # ---- retensi
    def bersihkan(self, sekarang: Optional[datetime] = None) -> int:
        sekarang = sekarang or datetime.now()
        simpan, hari_terisi = set(), set()
        for p in self.daftar():                      # terbaru -> terlama
            t, alasan = self.waktu_dari_nama(p), POLA_NAMA.match(p.name).group(2)
            umur = sekarang - t
            if alasan == "sebelum_upgrade" or umur <= timedelta(days=3):
                simpan.add(p)
            elif umur <= timedelta(days=self.simpan_hari) and t.date() not in hari_terisi:
                hari_terisi.add(t.date())
                simpan.add(p)
        hapus = [p for p in self.daftar() if p not in simpan]
        for p in hapus:
            try:
                p.unlink()
            except OSError:
                pass
        return len(hapus)
