"""Material reject (tidak layak pakai): form pencatatan dan tabel catatan untuk operator."""
from PySide6.QtCore import QDateTime, Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLineEdit, QMessageBox, QVBoxLayout, QWidget)

from database import Repository
from models import Shift
from theme import MERAH, NAVY
from ui_common import (BarisKpi, KartuForm, ambil_shift, buat_shift, buat_tabel, buat_waktu,
                       bungkus_kartu, isi_tabel, tombol_aksi, waktu_str)


class FormReject(KartuForm):
    """Form pencatatan material reject: tanggal/waktu, shift, operator, jenis, berat, catatan."""
    disimpan = Signal()

    def __init__(self, repo: Repository):
        super().__init__("Material Reject")
        self.repo = repo
        self.waktu = buat_waktu()
        self.shift = buat_shift()
        self.operator = QLineEdit(repo.pengguna.nama if repo.pengguna else "")
        self.jenis = QComboBox()                 # pilihan dari Master Data
        self.berat = QDoubleSpinBox()
        self.berat.setRange(0, 1_000_000)
        self.berat.setDecimals(2)
        self.berat.setSuffix(" kg")
        self.catatan = QLineEdit()
        self.catatan.setPlaceholderText("mis. kemasan bocor, kontaminasi")

        form = self.form
        form.addRow("Tanggal / Waktu", self.waktu)
        form.addRow("Shift", self.shift)
        form.addRow("Operator", self.operator)
        form.addRow("Jenis Material", self.jenis)
        form.addRow("Berat", self.berat)
        form.addRow("Catatan", self.catatan)
        form.addRow(tombol_aksi("Simpan Reject", self.simpan, "bahaya"))
        self.muat_master()

    def muat_master(self):
        """Muat ulang pilihan jenis material dari Master Data (pilihan terakhir dipertahankan)."""
        lama = self.jenis.currentText()
        self.jenis.clear()
        self.jenis.addItems(self.repo.daftar_jenis())
        i = self.jenis.findText(lama)
        if i >= 0:
            self.jenis.setCurrentIndex(i)

    def simpan(self):
        shift, berat, jenis = ambil_shift(self.shift), self.berat.value(), \
            self.jenis.currentText().strip()
        if shift is None:
            return QMessageBox.warning(self, "Shift belum dipilih",
                                       "Pilih shift terlebih dahulu.")
        if not jenis:
            return QMessageBox.warning(
                self, "Jenis belum dipilih",
                "Pilih jenis material.\nJika pilihan kosong, minta admin menambahkannya "
                "di Master Data.")
        if berat <= 0:
            return QMessageBox.warning(self, "Berat belum diisi",
                                       "Berat reject harus lebih dari 0 kg.")
        try:
            self.repo.tambah_reject(waktu_str(self.waktu), shift, self.operator.text(),
                                    berat, jenis, self.catatan.text())
        except ValueError as e:
            return QMessageBox.warning(self, "Tidak bisa disimpan", str(e))
        self.reset()
        self.disimpan.emit()

    def reset(self):
        self.waktu.setDateTime(QDateTime.currentDateTime())
        self.shift.setCurrentIndex(0)           # shift selalu dipilih manual
        self.berat.setValue(0)
        self.catatan.clear()
        self.berat.setFocus()


class TabelReject(QWidget):
    """Daftar catatan material reject (hanya lihat). Koreksi & ekspor ada di dashboard admin."""
    KOLOM = ["Waktu", "Shift", "Operator", "Jenis Material", "Berat (kg)", "Catatan",
             "Approval"]

    def __init__(self, repo: Repository):
        super().__init__()
        self.repo, self.data = repo, []
        self.kpi = BarisKpi([("CATATAN REJECT", MERAH), ("TOTAL BERAT", NAVY)])
        self.cari = QLineEdit()
        self.cari.setPlaceholderText("Cari jenis / operator / catatan...")
        self.shift = QComboBox()
        self.shift.addItems(["Semua shift"] + [s.label for s in Shift])
        self.tabel = buat_tabel(self.KOLOM)

        bar = QHBoxLayout()
        bar.addWidget(self.cari, 1)
        bar.addWidget(self.shift)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(self.kpi)
        lay.addWidget(bungkus_kartu(bar))
        lay.addWidget(self.tabel, 1)

        self.cari.textChanged.connect(self.refresh)
        self.shift.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self, *_):
        self.data = self.repo.aktivitas(tipe="REJECT", shift=self.shift.currentIndex() or None,
                                        cari=self.cari.text().strip())
        isi_tabel(self.tabel,
                  [[a.waktu, str(a.shift or "-"), a.operator or "", a.jenis,
                    f"{a.berat or 0:.2f}", a.catatan or "", a.status_approval]
                   for a in self.data],
                  kanan=(4,), latar=["#ECFDF5" if a.disetujui else None for a in self.data])
        self.kpi.set(0, len(self.data))
        self.kpi.set(1, f"{sum(a.berat or 0 for a in self.data):.2f}", "kg")
