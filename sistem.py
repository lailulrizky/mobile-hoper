"""Fungsi sistem: log berkas, penangkap error tak terduga, persiapan database saat startup."""
import logging
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, List, Tuple

from config import Konfigurasi, lokasi_app
from pencadangan import Pencadangan
from versi import VERSI_SKEMA


class DatabaseBermasalah(Exception):
    """Database tidak aman dibuka (rusak, atau dibuat oleh versi aplikasi yang lebih baru)."""


@dataclass
class Konteks:
    """Objek bersama: pengaturan, pencadangan, dan logger."""
    cfg: Konfigurasi
    pencadangan: Pencadangan
    log: logging.Logger
    catatan_awal: List[str] = field(default_factory=list)


def siapkan_log(folder: Path) -> logging.Logger:
    log = logging.getLogger("hoper")
    log.setLevel(logging.INFO)
    if log.handlers:
        return log
    try:
        folder.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(folder / "aplikasi.log", maxBytes=1_000_000, backupCount=5,
                                encoding="utf-8")
    except OSError:                       # mis. folder log tidak bisa ditulis
        h = logging.StreamHandler() if sys.stderr else logging.NullHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    return log


def pasang_excepthook(log: logging.Logger, tampilkan: Callable[[str, str], None],
                      berkas_log: Path):
    """Error tak terduga: dicatat lengkap di log, pengguna melihat pesan ramah, aplikasi
    tidak mati diam-diam."""
    status = {"sibuk": False}

    def hook(tipe, nilai, tb):
        if issubclass(tipe, KeyboardInterrupt):
            return sys.__excepthook__(tipe, nilai, tb)
        log.critical("Error tak tertangani", exc_info=(tipe, nilai, tb))
        if status["sibuk"]:
            return                               # cegah tumpukan dialog berulang
        status["sibuk"] = True
        try:
            tampilkan(f"{tipe.__name__}: {nilai}", str(berkas_log))
        except Exception:
            log.exception("Gagal menampilkan pesan error")
        finally:
            status["sibuk"] = False

    sys.excepthook = hook


def siapkan_database(cfg: Konfigurasi, pencadangan: Pencadangan,
                     log: logging.Logger) -> Tuple[Path, List[str]]:
    """Dipanggil sebelum database dibuka:
    1) pindahkan database lama (penerimaan.db di folder aplikasi) ke folder data,
    2) periksa integritas, 3) tolak database dari versi lebih baru,
    4) buat cadangan otomatis sebelum upgrade skema."""
    catatan = []
    cfg.folder_data.mkdir(parents=True, exist_ok=True)
    db = cfg.jalur_db
    lama = lokasi_app() / "penerimaan.db"
    if not db.exists() and lama.exists() and lama.resolve() != db.resolve():
        shutil.copy2(lama, db)
        lama.rename(lama.with_name("penerimaan_sudah_dipindahkan.db"))
        pesan = (f"Database lama dipindahkan ke folder data:\n{db}\n"
                 "(berkas asli diganti nama menjadi penerimaan_sudah_dipindahkan.db)")
        log.warning(pesan.replace("\n", " "))
        catatan.append(pesan)
    if db.exists():
        con = sqlite3.connect(db)
        try:
            hasil = con.execute("PRAGMA quick_check").fetchone()[0]
            versi = con.execute("PRAGMA user_version").fetchone()[0]
        except sqlite3.DatabaseError as e:
            raise DatabaseBermasalah(f"Berkas database tidak bisa dibaca ({e}).\n"
                                     f"Pulihkan dari folder cadangan:\n{cfg.folder_cadangan}")
        finally:
            con.close()
        if hasil != "ok":
            log.critical("quick_check gagal: %s", hasil)
            raise DatabaseBermasalah("Pemeriksaan integritas database GAGAL "
                                     f"({hasil}).\nPulihkan dari folder cadangan:\n"
                                     f"{cfg.folder_cadangan}")
        if versi > VERSI_SKEMA:
            raise DatabaseBermasalah(
                f"Database ini dibuat oleh versi aplikasi yang lebih baru (skema {versi}, "
                f"aplikasi ini mendukung sampai {VERSI_SKEMA}).\nPerbarui aplikasi dulu agar "
                "data tidak rusak.")
        if versi < VERSI_SKEMA:
            p = pencadangan.cadangkan("sebelum_upgrade")
            log.info("Cadangan sebelum upgrade skema %s -> %s: %s", versi, VERSI_SKEMA, p)
    return db, catatan
