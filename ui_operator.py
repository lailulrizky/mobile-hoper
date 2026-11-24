"""Halaman operator: penerimaan material, pemakaian (pasang / lepas), dan tabel hoper."""
from PySide6.QtCore import Qt, QDateTime, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QFrame,
    QHBoxLayout, QLineEdit, QMessageBox, QScrollArea, QTabWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

from database import Repository
from models import Status, Hoper
from theme import BIRU, HIJAU, KUNING, MERAH, NAVY
from ui_reject import FormReject, TabelReject
from ui_common import (BarisKpi, ambil_shift, buat_shift, buat_tabel, buat_waktu,
                       bungkus_kartu, ekspor_tabel, KartuForm, tombol_aksi, waktu_str)


# ------------------------------------------------------------------ Form
class FormPenerimaan(KartuForm):
    """Form input penerimaan material ke hoper."""
    disimpan = Signal()

    def __init__(self, repo: Repository):
        super().__init__("Penerimaan Material")
        self.repo = repo
        self.no_hoper = QComboBox()             # pilihan dari Master Data (hoper kosong)
        self.trace = QLineEdit()
        self.jenis = QComboBox()                # pilihan dari Master Data
        self.berat = QDoubleSpinBox()
        self.berat.setRange(0, 1_000_000)
        self.berat.setDecimals(2)
        self.berat.setSuffix(" kg")
        self.waktu = buat_waktu()
        self.shift = buat_shift()
        self.status = QComboBox()
        for s in Status:
            self.status.addItem(f"{s.value} - {s.keterangan}")
        self.status.setCurrentIndex(list(Status).index(Status.HOLD))
        self.catatan = QLineEdit()

        form = self.form
        form.addRow("No. Hoper", self.no_hoper)
        form.addRow("Kode Trace", self.trace)
        form.addRow("Jenis", self.jenis)
        form.addRow("Berat", self.berat)
        form.addRow("Waktu Terima", self.waktu)
        form.addRow("Shift Terima", self.shift)
        form.addRow("Status Awal", self.status)
        form.addRow("Catatan", self.catatan)
        form.addRow(tombol_aksi("Simpan", self.simpan, "primer"))
        self.muat_master()

    def muat_master(self):
        """Muat ulang pilihan dari Master Data: nomor hoper yang masih kosong + jenis."""
        self._isi(self.no_hoper, self.repo.daftar_hoper_tersedia())
        self._isi(self.jenis, self.repo.daftar_jenis())

    @staticmethod
    def _isi(combo, daftar):
        lama = combo.currentText()
        combo.clear()
        combo.addItems(daftar)
        i = combo.findText(lama)
        if i >= 0:
            combo.setCurrentIndex(i)

    def simpan(self):
        no, trace = self.no_hoper.currentText().strip(), self.trace.text().strip()
        jenis, berat = self.jenis.currentText().strip(), self.berat.value()
        if not (no and trace and jenis) or berat <= 0:
            return QMessageBox.warning(
                self, "Data belum lengkap",
                "No. hoper, kode trace, jenis, dan berat (> 0) wajib diisi.\n"
                "Jika pilihan hoper/jenis kosong, minta admin menambahkannya di Master Data.")
        shift = ambil_shift(self.shift)
        if shift is None:
            return QMessageBox.warning(self, "Shift belum dipilih",
                                       "Pilih shift penerimaan terlebih dahulu.")
        w = Hoper(no, trace, jenis, berat, waktu_str(self.waktu),
                  status=list(Status)[self.status.currentIndex()], shift_terima=shift)
        try:
            self.repo.tambah(w, self.catatan.text().strip())
        except ValueError as e:
            return QMessageBox.warning(self, "Tidak bisa disimpan", str(e))
        self.reset()
        self.disimpan.emit()

    def reset(self):
        for f in (self.trace, self.catatan):
            f.clear()
        self.berat.setValue(0)
        self.waktu.setDateTime(QDateTime.currentDateTime())
        self.shift.setCurrentIndex(0)
        self.muat_master()
        self.no_hoper.setFocus()


class FormPemakaian(KartuForm):
    """Form pemasangan hoper ke mesin sebagai supply bahan."""
    disimpan = Signal()

    def __init__(self, repo: Repository):
        super().__init__("Pemakaian Hoper (Pasang ke Mesin)")
        self.repo = repo
        self.pilihan = []                      # daftar Hoper sesuai isi combo
        self.hoper = QComboBox()
        self.mesin = QComboBox()                # pilihan dari Master Data (mesin kosong)
        self.operator = QLineEdit()
        self.waktu = buat_waktu()
        self.shift = buat_shift()
        self.catatan = QLineEdit()

        form = self.form
        form.addRow("Hoper (OK/standby)", self.hoper)
        form.addRow("Mesin", self.mesin)
        form.addRow("Operator", self.operator)
        form.addRow("Waktu Pasang", self.waktu)
        form.addRow("Shift Pasang", self.shift)
        form.addRow("Catatan", self.catatan)
        form.addRow(tombol_aksi("Pasang ke Mesin", self.pasang, "primer"))
        self.muat()

    @staticmethod
    def _label(w: Hoper) -> str:
        teks = f"{w.no_hoper} | {w.kode_trace} | {w.jenis} | {w.berat:.2f} kg"
        if w.mesin_terakhir:                     # pernah dipakai = standby (ada sisa)
            teks += f" | standby (bekas {w.mesin_terakhir})"
        return teks

    def muat(self):
        """Muat ulang hoper yang siap dipasang (status OK, belum terpasang)."""
        lama = self.hoper.currentText()
        self.pilihan = self.repo.daftar_siap_pakai()
        self.hoper.clear()
        self.hoper.addItems([self._label(w) for w in self.pilihan])
        i = self.hoper.findText(lama)
        if i >= 0:
            self.hoper.setCurrentIndex(i)
        mesin = self.mesin.currentText()
        self.mesin.clear()
        self.mesin.addItems(self.repo.daftar_mesin_kosong())
        i = self.mesin.findText(mesin)
        if i >= 0:
            self.mesin.setCurrentIndex(i)

    def pasang(self):
        i, mesin = self.hoper.currentIndex(), self.mesin.currentText().strip()
        if i < 0:
            return QMessageBox.warning(self, "Tidak ada hoper",
                                       "Tidak ada hoper berstatus OK yang siap dipasang.")
        if not mesin:
            return QMessageBox.warning(
                self, "Mesin belum tersedia",
                "Tidak ada mesin kosong yang terdaftar.\nLepas hoper dari mesin, atau minta admin "
                "menambah mesin di Master Data.")
        shift = ambil_shift(self.shift)
        if shift is None:
            return QMessageBox.warning(self, "Shift belum dipilih",
                                       "Pilih shift pemakaian terlebih dahulu.")
        try:
            self.repo.pasang(self.pilihan[i].id, mesin, self.operator.text().strip(),
                             waktu_str(self.waktu), shift, self.catatan.text().strip())
        except ValueError as e:
            return QMessageBox.warning(self, "Tidak bisa dipasang", str(e))
        self.catatan.clear()
        self.shift.setCurrentIndex(0)
        self.waktu.setDateTime(QDateTime.currentDateTime())
        self.disimpan.emit()


# ---------------------------------------------------------------- Dialog
class StatusDialog(QDialog):
    def __init__(self, w: Hoper, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Ubah Status - Hoper {w.no_hoper}")
        self.cb = QComboBox()
        for s in Status:
            self.cb.addItem(f"{s.value} - {s.keterangan}")
        self.cb.setCurrentIndex(list(Status).index(w.status))
        self.catatan = QLineEdit()
        tombol = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        tombol.accepted.connect(self.accept)
        tombol.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow("Status baru", self.cb)
        form.addRow("Catatan", self.catatan)
        form.addRow(tombol)

    def status(self) -> Status:
        return list(Status)[self.cb.currentIndex()]


class LepasDialog(QDialog):
    """Dialog melepas hoper dari mesin.
    Standby = masih ada isi, status tetap, bisa dipasang ke mesin lain.
    Kosong  = material habis / dikuras, hoper selesai dipakai."""

    def __init__(self, w: Hoper, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Lepas Hoper {w.no_hoper} dari Mesin {w.mesin}")
        self._berat = w.berat
        self.waktu = buat_waktu()
        self.shift = buat_shift()
        self.kondisi = QComboBox()
        self.kondisi.addItems(["Standby - masih ada isi (bisa dipasang ke mesin lain)",
                               "Kosong - material habis / dikuras"])
        self.sisa = QDoubleSpinBox()
        self.sisa.setRange(0, w.berat)
        self.sisa.setDecimals(2)
        self.sisa.setSuffix(" kg")
        self.sisa.setValue(w.berat)
        self.catatan = QLineEdit()
        self.kondisi.currentIndexChanged.connect(self._saat_kondisi)
        tombol = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        tombol.accepted.connect(self._cek)
        tombol.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow("Waktu lepas", self.waktu)
        form.addRow("Shift lepas", self.shift)
        form.addRow("Kondisi hoper", self.kondisi)
        form.addRow("Sisa berat", self.sisa)
        form.addRow("Catatan", self.catatan)
        form.addRow(tombol)

    @property
    def kosongkan(self) -> bool:
        return self.kondisi.currentIndex() == 1

    def _saat_kondisi(self):
        self.sisa.setEnabled(not self.kosongkan)
        self.sisa.setValue(0 if self.kosongkan else self._berat)

    def _cek(self):
        if ambil_shift(self.shift) is None:
            return QMessageBox.warning(self, "Shift belum dipilih",
                                       "Pilih shift pelepasan terlebih dahulu.")
        if not self.kosongkan and self.sisa.value() <= 0:
            return QMessageBox.warning(
                self, "Sisa belum diisi",
                "Hoper standby harus punya sisa lebih dari 0 kg.\n"
                "Pilih 'Kosong' jika material sudah habis.")
        self.accept()


class RiwayatDialog(QDialog):
    """Riwayat lengkap satu hoper (siapa melakukan apa, kapan)."""

    def __init__(self, judul: str, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle(judul)
        self.resize(760, 340)
        t = buat_tabel(["Waktu", "Status", "Oleh", "Catatan"])
        t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, v in enumerate(r):
                t.setItem(i, j, QTableWidgetItem(v or ""))
        t.resizeColumnsToContents()
        t.horizontalHeader().setStretchLastSection(True)
        QVBoxLayout(self).addWidget(t)


# ---------------------------------------------------------------- Tabel
class TabelHoper(QWidget):
    KOLOM = ["No. Hoper", "Kode Trace", "Jenis", "Berat (kg)", "Waktu Terima",
             "Shift Terima", "Status", "Mesin", "Shift Pasang", "Kondisi"]
    berubah = Signal()          # dipancarkan setiap data dimuat ulang

    def __init__(self, repo: Repository, boleh_ekspor: bool = False):
        super().__init__()
        self.repo = repo
        self.data = []

        self.cari = QLineEdit()
        self.cari.setPlaceholderText("Cari no. hoper / trace / jenis / mesin...")
        self.filter = QComboBox()
        self.filter.addItems(["Semua status"] + [s.value for s in Status])
        self.semua = QCheckBox("Tampilkan hoper kosong")
        for sinyal in (self.cari.textChanged, self.filter.currentIndexChanged,
                       self.semua.toggled):
            sinyal.connect(self.refresh)

        self.tabel = buat_tabel(self.KOLOM)
        self.kpi = BarisKpi([("HOPER OK", HIJAU), ("HOLD", KUNING), ("REJECT", MERAH),
                             ("STANDBY", BIRU), ("TERPASANG", NAVY)])

        bar = QHBoxLayout()
        bar.addWidget(self.cari, 1)
        bar.addWidget(self.filter)
        bar.addWidget(self.semua)

        aksi = QHBoxLayout()
        for teks, fn, varian in [("Ubah Status", self.ubah_status, ""),
                                 ("Lepas dari Mesin", self.lepas, ""),
                                 ("Kosongkan Hoper", self.kosongkan, "bahaya"),
                                 ("Riwayat", self.lihat_riwayat, "")] + (
                                     [("Ekspor Excel/PDF", self.ekspor, "")]
                                     if boleh_ekspor else []):
            aksi.addWidget(tombol_aksi(teks, fn, varian))
        aksi.addStretch()

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(self.kpi)
        lay.addWidget(bungkus_kartu(bar))
        lay.addWidget(self.tabel, 1)
        lay.addLayout(aksi)
        self.refresh()

    @staticmethod
    def _baris(w: Hoper):
        return [w.no_hoper, w.kode_trace, w.jenis, f"{w.berat:.2f}", w.waktu_terima,
                str(w.shift_terima or "-"), w.status.value, w.mesin or "-",
                str(w.shift_pasang or "-"), w.kondisi]

    def refresh(self, *_):
        idx = self.filter.currentIndex()
        status = list(Status)[idx - 1] if idx > 0 else None
        self.data = self.repo.daftar(status, self.cari.text().strip(), self.semua.isChecked())
        self.tabel.setRowCount(len(self.data))
        for i, w in enumerate(self.data):
            for j, v in enumerate(self._baris(w)):
                item = QTableWidgetItem(v)
                if j == 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setBackground(QColor(w.status.warna if w.aktif else "#F1F5F9"))
                if not w.aktif:
                    item.setForeground(QColor("#94A3B8"))
                elif j == 6:                      # kolom Status: tebal & berwarna
                    item.setForeground(QColor(w.status.warna_teks))
                else:
                    item.setForeground(QColor("#0F172A"))
                if w.aktif and j in (0, 6):
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.tabel.setItem(i, j, item)
        self.tabel.resizeColumnsToContents()
        self.tabel.horizontalHeader().setStretchLastSection(True)
        self._hitung_ringkasan()
        self.berubah.emit()

    def _hitung_ringkasan(self):
        berisi = [w for w in self.data if w.aktif]
        kelompok = [[w for w in berisi if w.status == s] for s in Status]   # OK, HOLD, REJECT
        kelompok.append([w for w in berisi if not w.mesin])                 # standby
        kelompok.append([w for w in berisi if w.mesin])                     # terpasang
        for n, sub in enumerate(kelompok):
            self.kpi.set(n, len(sub), f"{sum(w.berat for w in sub):.2f} kg")

    def terpilih(self):
        r = self.tabel.currentRow()
        if r < 0:
            QMessageBox.information(self, "Pilih data", "Pilih satu hoper di tabel dulu.")
            return None
        return self.data[r]

    def ubah_status(self):
        w = self.terpilih()
        if not w:
            return
        if not w.aktif:
            return QMessageBox.information(self, "Hoper kosong",
                                           "Hoper ini sudah dikosongkan.")
        dlg = StatusDialog(w, self)
        if dlg.exec():
            self.repo.ubah_status(w.id, dlg.status(), dlg.catatan.text().strip())
            self.refresh()

    def lepas(self):
        w = self.terpilih()
        if not w:
            return
        if not w.mesin:
            return QMessageBox.information(self, "Tidak terpasang",
                                           "Hoper ini tidak sedang terpasang di mesin.")
        dlg = LepasDialog(w, self)
        if dlg.exec():
            try:
                self.repo.lepas(w.pemakaian_id, waktu_str(dlg.waktu), ambil_shift(dlg.shift),
                                dlg.sisa.value(), dlg.kosongkan, dlg.catatan.text().strip())
            except ValueError as e:
                QMessageBox.warning(self, "Gagal", str(e))
            self.refresh()

    def kosongkan(self):
        w = self.terpilih()
        if not w or not w.aktif:
            return
        jawab = QMessageBox.question(
            self, "Konfirmasi",
            f"Kosongkan hoper {w.no_hoper} (trace {w.kode_trace})?\n"
            "Hoper bisa dipakai menerima material baru.")
        if jawab == QMessageBox.Yes:
            try:
                self.repo.kosongkan(w.id)
            except ValueError as e:
                QMessageBox.warning(self, "Tidak bisa dikosongkan", str(e))
            self.refresh()

    def lihat_riwayat(self):
        w = self.terpilih()
        if w:
            RiwayatDialog(f"Riwayat Hoper {w.no_hoper} - Trace {w.kode_trace}",
                          self.repo.riwayat(w.id), self).exec()

    def ekspor(self):
        info = "Filter: " + self.filter.currentText() + \
               (" | termasuk hoper kosong" if self.semua.isChecked() else "")
        ekspor_tabel(self, self.repo, "Data Hoper", self.KOLOM,
                     [self._baris(w) for w in self.data], info, angka=(3,))


# ----------------------------------------------------------------- Halaman
class HalamanOperator(QWidget):
    """Halaman kerja operator: form penerimaan, pemakaian, dan material reject di kiri;
    tabel hoper & tabel reject (tab) di kanan."""

    def __init__(self, repo: Repository, boleh_ekspor: bool = False):
        super().__init__()
        self.form_terima = FormPenerimaan(repo)
        self.form_pakai = FormPemakaian(repo)
        self.form_reject = FormReject(repo)
        self.tabel = TabelHoper(repo, boleh_ekspor)
        self.tabel_reject = TabelReject(repo)
        for f in (self.form_terima, self.form_pakai, self.form_reject):
            f.setFixedWidth(340)
        for f in (self.form_terima, self.form_pakai):
            f.disimpan.connect(self.tabel.refresh)
            f.disimpan.connect(self._tampil_hoper)
        self.form_reject.disimpan.connect(self.tabel_reject.refresh)
        self.form_reject.disimpan.connect(self._tampil_reject)
        self.tabel.berubah.connect(self.form_pakai.muat)
        self.tabel.berubah.connect(self.form_terima.muat_master)
        self.tabel.berubah.connect(self.form_reject.muat_master)
        self.form_pakai.muat()

        self.tab = QTabWidget()
        self.tab.addTab(self.tabel, "Data Hoper")
        self.tab.addTab(self.tabel_reject, "Material Reject")

        # Kolom form bisa digulir: di layar pendek / skala tampilan besar, form tidak
        # dipaksa mengecil (yang membuat isian bertumpuk), melainkan muncul scrollbar.
        kolom = QWidget()
        kiri = QVBoxLayout(kolom)
        kiri.setContentsMargins(0, 0, 8, 0)
        kiri.setSpacing(12)
        kiri.addWidget(self.form_terima)
        kiri.addWidget(self.form_pakai)      # form pemakaian di bawah form penerimaan
        kiri.addWidget(self.form_reject)     # form material reject di bawah pemakaian
        kiri.addStretch()
        gulung = QScrollArea()
        gulung.setWidgetResizable(True)
        gulung.setFrameShape(QFrame.Shape.NoFrame)
        gulung.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        gulung.setFixedWidth(372)
        gulung.setWidget(kolom)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(gulung)
        lay.addWidget(self.tab, 1)

    def _tampil_hoper(self):
        self.tab.setCurrentWidget(self.tabel)

    def _tampil_reject(self):
        self.tab.setCurrentWidget(self.tabel_reject)

    def refresh(self):
        self.tabel.refresh()
        self.tabel_reject.refresh()
