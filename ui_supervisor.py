"""Halaman supervisor: approval penerimaan / pemasangan / pelepasan per shift."""
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget)

from database import Repository
from models import Aktivitas, Shift
from theme import BIRU, HIJAU, KUNING
from ui_common import (FORMAT_TANGGAL, BarisKpi, ambil_shift, buat_shift, buat_tabel,
                       bungkus_kartu, ekspor_tabel, isi_tabel, tombol_aksi)
from ui_operator import RiwayatDialog


class HalamanApproval(QWidget):
    """Pilih tanggal shift + shift, tinjau aktivitasnya, lalu setujui."""

    def __init__(self, repo: Repository):
        super().__init__()
        self.repo, self.data = repo, []
        self.tanggal = QDateEdit(QDate.currentDate())
        self.tanggal.setDisplayFormat(FORMAT_TANGGAL)
        self.tanggal.setCalendarPopup(True)
        self.shift = buat_shift()
        self.tabel = buat_tabel(Aktivitas.KOLOM, multi=True)
        self.ringkasan = QLabel()           # keterangan tanggal & shift yang dipilih
        self.ringkasan.setObjectName("muted")
        self.kpi = BarisKpi([("TOTAL AKTIVITAS", BIRU), ("PENDING", KUNING),
                             ("DISETUJUI", HIJAU)])
        self.lbl_rekap = QLabel()           # ringkasan rekap shift + tombol approval rekap
        self.lbl_rekap.setWordWrap(True)
        rekap_lay = QHBoxLayout()
        rekap_lay.addWidget(self.lbl_rekap, 1)
        rekap_lay.addWidget(tombol_aksi("Setujui Rekap Shift Ini", self.setujui_rekap, "primer"))

        atas = QHBoxLayout()
        atas.addWidget(QLabel("Tanggal shift:"))
        atas.addWidget(self.tanggal)
        atas.addWidget(QLabel("Shift:"))
        atas.addWidget(self.shift)
        atas.addStretch()

        aksi = QHBoxLayout()
        for teks, fn, varian in [("Setujui Terpilih", self.setujui_terpilih, "sukses"),
                                 ("Setujui Semua Pending (shift ini)", self.setujui_semua,
                                  "primer"),
                                 ("Riwayat Detail", self.lihat_hoper, ""),
                                 ("Ekspor Excel/PDF", self.ekspor, "")]:
            aksi.addWidget(tombol_aksi(teks, fn, varian))
        aksi.addStretch()

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(self.kpi)
        lay.addWidget(bungkus_kartu(atas))
        lay.addWidget(self.ringkasan)
        lay.addWidget(bungkus_kartu(rekap_lay))
        lay.addWidget(self.tabel, 1)
        lay.addLayout(aksi)

        self.tanggal.dateChanged.connect(self.refresh)
        self.shift.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def _konteks(self) -> str:
        shift = ambil_shift(self.shift)
        label = Shift(shift).label if shift else "-"
        return f"{self.tanggal.date().toString(FORMAT_TANGGAL)}, {label}"

    def refresh(self, *_):
        shift = ambil_shift(self.shift)
        if shift is None:
            self.data = []
            isi_tabel(self.tabel, [])
            for n in range(3):
                self.kpi.set(n, 0)
            self.ringkasan.setText("Pilih tanggal shift dan shift untuk menampilkan data.")
            self.lbl_rekap.setText("Rekap shift: pilih tanggal shift dan shift.")
            return
        tgl = self.tanggal.date().toString(FORMAT_TANGGAL)
        self.data = self.repo.aktivitas(dari=tgl, sampai=tgl, shift=shift)
        isi_tabel(self.tabel, [a.baris() for a in self.data], kanan=Aktivitas.IDX_ANGKA,
                  latar=["#ECFDF5" if a.disetujui else None for a in self.data])
        pending = sum(1 for a in self.data if not a.disetujui)
        self.kpi.set(0, len(self.data))
        self.kpi.set(1, pending)
        self.kpi.set(2, len(self.data) - pending)
        self.ringkasan.setText(f"Menampilkan: {self._konteks()}")
        self._isi_rekap(tgl, shift)

    def _isi_rekap(self, tgl: str, shift: int):
        hasil = self.repo.rekap_shift(tgl, tgl, shift)
        if not hasil:
            self.lbl_rekap.setText("Rekap shift: belum ada aktivitas pada shift ini.")
            return
        rk = hasil[0]
        self.lbl_rekap.setText(
            f"Rekap shift  |  Diterima: {rk.hoper_diterima} hoper ({rk.berat_diterima:.2f} kg)"
            f"  |  Hoper digunakan: {rk.hoper_digunakan}"
            f"  |  Reject: {rk.berat_reject:.2f} kg ({rk.reject_catatan} catatan)"
            f"  |  Status: {rk.status}")

    def setujui_rekap(self):
        shift = ambil_shift(self.shift)
        if shift is None:
            return QMessageBox.information(self, "Pilih shift",
                                           "Pilih tanggal shift dan shift dulu.")
        if QMessageBox.question(self, "Konfirmasi Approval Rekap",
                                f"Setujui rekap shift {self._konteks()}?") != QMessageBox.Yes:
            return
        try:
            self.repo.setujui_rekap(self.tanggal.date().toString(FORMAT_TANGGAL), shift)
        except (ValueError, PermissionError) as e:
            return QMessageBox.warning(self, "Rekap belum bisa disetujui", str(e))
        self.refresh()
        QMessageBox.information(self, "Approval", "Rekap shift disetujui.")

    def _terpilih(self):
        baris = sorted({i.row() for i in self.tabel.selectionModel().selectedRows()})
        return [self.data[r] for r in baris]

    def setujui_terpilih(self):
        items = self._terpilih()
        if not items:
            return QMessageBox.information(self, "Pilih data",
                                           "Pilih satu atau beberapa baris dulu.")
        self._setujui(items)

    def setujui_semua(self):
        if ambil_shift(self.shift) is None:
            return QMessageBox.information(self, "Pilih shift",
                                           "Pilih tanggal shift dan shift dulu.")
        self._setujui(self.data)

    def _setujui(self, items):
        pending = [a for a in items if not a.disetujui]
        if not pending:
            return QMessageBox.information(self, "Tidak ada yang pending",
                                           "Semua aktivitas yang dipilih sudah disetujui.")
        jawab = QMessageBox.question(
            self, "Konfirmasi Approval",
            f"Setujui {len(pending)} aktivitas pada {self._konteks()}?")
        if jawab != QMessageBox.Yes:
            return
        try:
            n = self.repo.setujui(pending)
        except PermissionError as e:
            return QMessageBox.warning(self, "Tidak diizinkan", str(e))
        self.refresh()
        QMessageBox.information(self, "Approval", f"{n} aktivitas disetujui.")

    def lihat_hoper(self):
        r = self.tabel.currentRow()
        if r < 0:
            return QMessageBox.information(self, "Pilih data", "Pilih satu baris dulu.")
        a = self.data[r]
        RiwayatDialog(a.judul_riwayat, self.repo.riwayat_aktivitas(a), self).exec()

    def ekspor(self):
        ekspor_tabel(self, self.repo, "Approval Shift", Aktivitas.KOLOM,
                     [a.baris() for a in self.data], f"Shift: {self._konteks()}",
                     Aktivitas.IDX_ANGKA)
