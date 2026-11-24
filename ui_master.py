"""Panel admin: Master Data (nomor hoper, nomor mesin, jenis material).
Operator hanya memilih dari daftar ini, tidak mengetik manual."""
import re

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QSpinBox, QVBoxLayout, QWidget)

from database import Repository
from models import Kategori
from ui_common import buat_tabel, isi_tabel, tombol_aksi

PETUNJUK = {
    Kategori.HOPER: "Nomor hoper yang bisa dipilih operator saat menerima material.",
    Kategori.MESIN: "Nomor / nama mesin tempat hoper dipasang sebagai supply bahan.",
    Kategori.JENIS: "Jenis material yang bisa dipilih operator saat penerimaan.",
}


class DialogBerurutan(QDialog):
    """Buat banyak nama bernomor urut sekaligus, mis. H-01 ... H-20."""
    BATAS = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Buat Berurutan")
        self.setMinimumWidth(380)
        self.awalan = QLineEdit()
        self.awalan.setPlaceholderText("mis. H-  atau  MESIN-")
        self.dari = QSpinBox()
        self.dari.setRange(0, 99999)
        self.dari.setValue(1)
        self.sampai = QSpinBox()
        self.sampai.setRange(0, 99999)
        self.sampai.setValue(10)
        self.digit = QSpinBox()
        self.digit.setRange(1, 6)
        self.digit.setValue(2)
        self.pratinjau = QLabel()
        self.pratinjau.setObjectName("muted")
        self.pratinjau.setWordWrap(True)
        for w in (self.dari, self.sampai, self.digit):
            w.valueChanged.connect(self._pratinjau)
        self.awalan.textChanged.connect(self._pratinjau)
        tombol = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        tombol.accepted.connect(self._cek)
        tombol.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow("Awalan", self.awalan)
        form.addRow("Dari nomor", self.dari)
        form.addRow("Sampai nomor", self.sampai)
        form.addRow("Jumlah digit", self.digit)
        form.addRow("Hasil", self.pratinjau)
        form.addRow(tombol)
        self._pratinjau()

    def daftar(self):
        a, d = self.awalan.text().strip(), self.digit.value()
        return [f"{a}{i:0{d}d}" for i in range(self.dari.value(), self.sampai.value() + 1)]

    def _pratinjau(self, *_):
        n = self.daftar()
        if not n:
            self.pratinjau.setText("Rentang tidak valid: 'Sampai' harus >= 'Dari'.")
        elif len(n) == 1:
            self.pratinjau.setText(n[0])
        else:
            self.pratinjau.setText(f"{n[0]}  ...  {n[-1]}   ({len(n)} nama)")

    def _cek(self):
        n = self.daftar()
        if not n:
            return QMessageBox.warning(self, "Tidak valid", "'Sampai' harus >= 'Dari'.")
        if len(n) > self.BATAS:
            return QMessageBox.warning(self, "Terlalu banyak",
                                       f"Maksimal {self.BATAS} nama sekali buat.")
        self.accept()


class KartuMaster(QFrame):
    """Satu kolom master data: daftar + tambah + aktif/nonaktif + hapus."""

    def __init__(self, repo: Repository, kategori: Kategori):
        super().__init__()
        self.setObjectName("panel")
        self.repo, self.kategori, self.data = repo, kategori, []

        judul = QLabel(kategori.label)
        judul.setObjectName("judul_kartu")
        ket = QLabel(PETUNJUK[kategori])
        ket.setObjectName("muted")
        ket.setWordWrap(True)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Ketik lalu Enter (banyak: pisahkan koma)")
        self.input.returnPressed.connect(self.tambah)
        baris = QHBoxLayout()
        baris.addWidget(self.input, 1)
        baris.addWidget(tombol_aksi("Tambah", self.tambah, "primer"))

        self.tabel = buat_tabel(["Nama", "Status", "Dipakai"])

        aksi = QHBoxLayout()
        if kategori != Kategori.JENIS:
            aksi.addWidget(tombol_aksi("Berurutan...", self.berurutan))
        aksi.addWidget(tombol_aksi("Aktif / Nonaktif", self.ganti_aktif))
        aksi.addWidget(tombol_aksi("Hapus", self.hapus, "bahaya"))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(10)
        lay.addWidget(judul)
        lay.addWidget(ket)
        lay.addLayout(baris)
        lay.addWidget(self.tabel, 1)
        lay.addLayout(aksi)
        self.refresh()

    def refresh(self, *_):
        self.data = self.repo.master_daftar(self.kategori)
        isi_tabel(self.tabel,
                  [[m.nama, "Aktif" if m.aktif else "Nonaktif", m.dipakai] for m in self.data],
                  kanan=(2,), latar=[None if m.aktif else "#E2E8F0" for m in self.data])

    # ---- aksi
    def tambah(self):
        nama = [x.strip() for x in re.split(r"[,;\n]", self.input.text()) if x.strip()]
        if not nama:
            return QMessageBox.information(self, "Kosong", "Ketik nama yang ingin ditambahkan.")
        if self._simpan(nama):
            self.input.clear()

    def berurutan(self):
        dlg = DialogBerurutan(self)
        if dlg.exec():
            self._simpan(dlg.daftar())

    def _simpan(self, daftar) -> bool:
        try:
            n, lewat = self.repo.master_tambah(self.kategori, daftar)
        except (ValueError, PermissionError) as e:
            QMessageBox.warning(self, "Gagal", str(e))
            return False
        self.refresh()
        if lewat:
            contoh = ", ".join(lewat[:5]) + (" ..." if len(lewat) > 5 else "")
            QMessageBox.information(
                self, "Sebagian dilewati",
                f"{n} ditambahkan.\n{len(lewat)} dilewati karena sudah ada: {contoh}")
        return True

    def _terpilih(self):
        r = self.tabel.currentRow()
        if r < 0:
            QMessageBox.information(self, "Pilih data", "Pilih satu baris di tabel dulu.")
            return None
        return self.data[r]

    def ganti_aktif(self):
        m = self._terpilih()
        if not m:
            return
        try:
            self.repo.master_set_aktif(m.id, not m.aktif)
        except PermissionError as e:
            return QMessageBox.warning(self, "Tidak diizinkan", str(e))
        self.refresh()

    def hapus(self):
        m = self._terpilih()
        if not m:
            return
        if QMessageBox.question(self, "Hapus", f"Hapus '{m.nama}' dari {self.kategori.label}?") \
                != QMessageBox.Yes:
            return
        try:
            self.repo.master_hapus(m.id)
        except (ValueError, PermissionError) as e:
            return QMessageBox.warning(self, "Tidak bisa dihapus", str(e))
        self.refresh()


class PanelMaster(QWidget):
    """Tab admin: tiga kolom master data berdampingan."""

    def __init__(self, repo: Repository):
        super().__init__()
        self.kartu = [KartuMaster(repo, k) for k in Kategori]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(12)
        for k in self.kartu:
            lay.addWidget(k, 1)

    def refresh(self, *_):
        for k in self.kartu:
            k.refresh()
