"""Konfigurasi (config.json di samping aplikasi) dan pencarian lokasi berkas.
Semua lokasi dihitung dari folder APLIKASI, bukan folder kerja, sehingga database tidak
'berpindah' bila aplikasi dibuka dari shortcut yang berbeda."""
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


def lokasi_app() -> Path:
    """Folder .exe bila sudah dipaketkan, atau folder kode bila dijalankan lewat Python."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def cari_aset(nama: str) -> str:
    """Cari assets/<nama>: di samping aplikasi dulu (logo bisa diganti tanpa build ulang),
    lalu di dalam paket."""
    kandidat = [lokasi_app() / "assets" / nama]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        kandidat.append(Path(meipass) / "assets" / nama)
    kandidat.append(Path(__file__).resolve().parent / "assets" / nama)
    for k in kandidat:
        if k.exists():
            return str(k)
    return str(kandidat[0])


BAWAAN = {
    "folder_data": "data",
    "folder_cadangan": "backup",
    "folder_log": "log",
    "cadangan_tiap_jam": 4,
    "cadangan_simpan_hari": 60,
    "logout_otomatis_menit": 0,
    "satu_instans": True,
}


@dataclass
class Konfigurasi:
    folder_data: Path
    folder_cadangan: Path
    folder_log: Path
    cadangan_tiap_jam: int = 4
    cadangan_simpan_hari: int = 60
    logout_otomatis_menit: int = 0           # 0 = nonaktif
    satu_instans: bool = True
    berkas: Optional[Path] = None
    peringatan: List[str] = field(default_factory=list)

    @property
    def jalur_db(self) -> Path:
        return self.folder_data / "penerimaan.db"


def _jalur(nilai, dasar: Path) -> Path:
    p = Path(str(nilai)).expanduser()
    return p if p.is_absolute() else dasar / p


def muat_konfigurasi(berkas: Optional[Path] = None) -> Konfigurasi:
    """Baca config.json (dibuat dengan nilai bawaan bila belum ada). Nilai yang tidak valid
    diganti nilai bawaan dan dicatat di Konfigurasi.peringatan."""
    dasar = lokasi_app()
    berkas = Path(berkas) if berkas else dasar / "config.json"
    data, peringatan = dict(BAWAAN), []
    if berkas.exists():
        try:
            isi = json.loads(berkas.read_text(encoding="utf-8"))
            if not isinstance(isi, dict):
                raise ValueError("isi harus berupa objek JSON { ... }")
            data.update(isi)
        except (OSError, ValueError) as e:
            peringatan.append(f"config.json tidak bisa dibaca ({e}); memakai pengaturan bawaan.")
    else:
        try:
            berkas.write_text(json.dumps(BAWAAN, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def angka(kunci: str, minimal: int, maksimal: int) -> int:
        try:
            n = int(data[kunci])
            if minimal <= n <= maksimal:
                return n
        except (TypeError, ValueError):
            pass
        peringatan.append(f"'{kunci}' harus angka {minimal}-{maksimal}; dipakai nilai bawaan "
                          f"({BAWAAN[kunci]}).")
        return BAWAAN[kunci]

    return Konfigurasi(
        folder_data=_jalur(data["folder_data"], dasar),
        folder_cadangan=_jalur(data["folder_cadangan"], dasar),
        folder_log=_jalur(data["folder_log"], dasar),
        cadangan_tiap_jam=angka("cadangan_tiap_jam", 1, 168),
        cadangan_simpan_hari=angka("cadangan_simpan_hari", 7, 3650),
        logout_otomatis_menit=angka("logout_otomatis_menit", 0, 1440),
        satu_instans=bool(data["satu_instans"]),
        berkas=berkas, peringatan=peringatan)
