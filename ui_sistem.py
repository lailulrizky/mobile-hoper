"""Panel admin: informasi sistem, pencadangan, dan catatan audit."""
from datetime import datetime

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout, QWidget)

from database import Repository
from sistem import Konteks
from theme import BIRU, HIJAU, KUNING, NAVY
from ui_common import (BarisKpi, buat_tabel, bungkus_kartu, ekspor_tabel, isi_tabel,
                       tombol_aksi)
from versi import VERSI_APLIKASI, VERSI_SKEMA


def _umur(t: datetime) -> str:
    detik = int((datetime.now() - t).total_seconds())
    if detik < 3600:
        return f"{max(detik // 60, 0)} menit lalu"
    if detik < 86400:
        return f"{detik // 3600} jam lalu"
    return f"{detik // 86400} hari lalu"


class PanelSistem(QWidget):
    KOLOM_AUDIT = ["Waktu", "Oleh", "Aksi", "Objek", "Detail"]

    def __init__(self, repo: Repository, ctx: Konteks):
        super().__init__()
        self.repo, self.ctx, self.data = repo, ctx, []
        cfg = ctx.cfg

        self.kpi = BarisKpi([("VERSI APLIKASI", BIRU), ("UKURAN DATABASE", NAVY),
                             ("CADANGAN TERAKHIR", HIJAU), ("JUMLAH CADANGAN", KUNING)])
        self.peringatan = QLabel()
        self.peringatan.setStyleSheet("color: #B91C1C; font-weight: 600;")
        self.peringatan.setWordWrap(True)

        info = QVBoxLayout()
        baris_info = [
            f"Database : {cfg.jalur_db}",
            f"Cadangan : {cfg.folder_cadangan}   (tiap {cfg.cadangan_tiap_jam} jam, "
            f"simpan {cfg.cadangan_simpan_hari} hari)",
            f"Log      : {cfg.folder_log}",
            f"Logout otomatis : " + (f"{cfg.logout_otomatis_menit} menit tanpa aktivitas"
                                     if cfg.logout_otomatis_menit else "nonaktif"),
            f"Pengaturan : {cfg.berkas}",
        ]
        for teks in baris_info:
            lbl = QLabel(teks)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            info.addWidget(lbl)
        info.addWidget(self.peringatan)

        aksi = QHBoxLayout()
        aksi.addWidget(tombol_aksi("Cadangkan Sekarang", self.cadangkan, "primer"))
        aksi.addWidget(tombol_aksi("Buka Folder Cadangan",
                                   lambda: self._buka(cfg.folder_cadangan)))
        aksi.addWidget(tombol_aksi("Buka Folder Log", lambda: self._buka(cfg.folder_log)))
        aksi.addStretch()
        info.addLayout(aksi)

        self.cari = QLineEdit()
        self.cari.setPlaceholderText("Cari di catatan audit (pengguna, aksi, objek, detail)...")
        self.cari.textChanged.connect(self.refresh)
        judul = QLabel("Catatan Audit  (login, perubahan master data & akun, approval rekap, backup)")
        judul.setObjectName("judul_kartu")
        self.tabel = buat_tabel(self.KOLOM_AUDIT)
        bawah = QHBoxLayout()
        bawah.addWidget(tombol_aksi("Ekspor Audit", self.ekspor))
        bawah.addStretch()

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(self.kpi)
        lay.addWidget(bungkus_kartu(info))
        lay.addWidget(judul)
        lay.addWidget(self.cari)
        lay.addWidget(self.tabel, 1)
        lay.addLayout(bawah)
        self.refresh()

    def refresh(self, *_):
        pc, cfg = self.ctx.pencadangan, self.ctx.cfg
        try:
            ukuran = cfg.jalur_db.stat().st_size / (1024 * 1024)
        except OSError:
            ukuran = 0.0
        daftar = pc.daftar()
        terakhir = pc.terakhir()
        self.kpi.set(0, f"v{VERSI_APLIKASI}", f"skema database {VERSI_SKEMA}")
        self.kpi.set(1, f"{ukuran:.2f}", "MB")
        if terakhir:
            self.kpi.set(2, terakhir.strftime("%H:%M"), f"{terakhir:%Y-%m-%d}  ({_umur(terakhir)})")
        else:
            self.kpi.set(2, "-", "belum ada cadangan")
        self.kpi.set(3, len(daftar), "berkas di folder cadangan")
        telat = terakhir is None or \
            (datetime.now() - terakhir).total_seconds() > 2 * cfg.cadangan_tiap_jam * 3600
        pesan = list(self.ctx.cfg.peringatan)
        if telat:
            pesan.append("PERHATIAN: cadangan terakhir sudah lebih dari 2x interval. "
                         "Periksa folder cadangan, lalu klik 'Cadangkan Sekarang'.")
        self.peringatan.setText("\n".join(pesan))

        self.data = [list(r) for r in self.repo.daftar_audit(self.cari.text().strip())]
        isi_tabel(self.tabel, self.data)

    def cadangkan(self):
        try:
            p = self.ctx.pencadangan.cadangkan("manual")
        except Exception as e:
            self.ctx.log.exception("Cadangan manual gagal")
            return QMessageBox.critical(
                self, "Cadangan gagal",
                f"{e}\n\nPeriksa 'folder_cadangan' di config.json dan hak akses foldernya.")
        self.repo.catat_audit("BACKUP_MANUAL", p.name)
        self.refresh()
        QMessageBox.information(self, "Cadangan dibuat", f"Cadangan tersimpan dan terverifikasi:\n{p}")

    @staticmethod
    def _buka(folder):
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def ekspor(self):
        ekspor_tabel(self, self.repo, "Catatan Audit", self.KOLOM_AUDIT, self.data,
                     f"Filter: {self.cari.text().strip() or 'semua'}")
