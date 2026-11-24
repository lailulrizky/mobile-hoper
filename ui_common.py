"""Helper UI yang dipakai bersama oleh semua halaman."""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QDateTime
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateTimeEdit, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import export
from models import Shift

FORMAT_WAKTU = "yyyy-MM-dd HH:mm"
FORMAT_TANGGAL = "yyyy-MM-dd"


def buat_tabel(kolom, multi=False):
    t = QTableWidget(0, len(kolom))
    t.setHorizontalHeaderLabels(kolom)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.ExtendedSelection if multi
                       else QAbstractItemView.SingleSelection)
    t.horizontalHeader().setStretchLastSection(True)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(32)
    t.horizontalHeader().setHighlightSections(False)
    t.horizontalHeader().setDefaultAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return t


def tombol_aksi(teks: str, fn=None, varian: str = "") -> QPushButton:
    """Tombol bergaya tema. varian: '' (biasa) | primer | sukses | bahaya | header."""
    b = QPushButton(teks)
    if varian:
        b.setProperty("varian", varian)
    if fn is not None:
        b.clicked.connect(fn)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def bungkus_kartu(layout) -> QFrame:
    """Bungkus sebuah layout dalam panel putih bersudut membulat."""
    k = QFrame()
    k.setObjectName("panel")
    k.setLayout(layout)
    layout.setContentsMargins(14, 10, 14, 10)
    return k


class KartuForm(QFrame):
    """Kartu putih berjudul dengan QFormLayout di dalamnya. Dipakai sebagai pengganti
    QGroupBox: tinggi minimumnya dihitung murni dari layout sehingga isinya tidak bertumpuk."""

    def __init__(self, judul: str):
        super().__init__()
        self.setObjectName("panel")
        utama = QVBoxLayout(self)
        utama.setContentsMargins(16, 14, 16, 16)
        utama.setSpacing(12)
        lbl = QLabel(judul)
        lbl.setObjectName("judul_kartu")
        utama.addWidget(lbl)
        self.form = QFormLayout()
        self.form.setVerticalSpacing(10)
        self.form.setHorizontalSpacing(12)
        utama.addLayout(self.form)


class KartuKpi(QFrame):
    """Kartu angka ringkasan bergaya dashboard: judul kecil, angka besar, keterangan."""

    def __init__(self, judul: str, warna: str):
        super().__init__()
        self.setObjectName("kpi")
        self.setStyleSheet(
            f"QFrame#kpi {{ background: white; border: 1px solid #E2E8F0; "
            f"border-left: 5px solid {warna}; border-radius: 10px; }}")
        self.lbl_judul = QLabel(judul)
        self.lbl_judul.setObjectName("kpi_judul")
        self.lbl_nilai = QLabel("0")
        self.lbl_nilai.setObjectName("kpi_nilai")
        self.lbl_nilai.setStyleSheet(f"color: {warna};")
        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("kpi_sub")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(0)
        for w in (self.lbl_judul, self.lbl_nilai, self.lbl_sub):
            lay.addWidget(w)

    def set(self, nilai, sub: str = ""):
        self.lbl_nilai.setText(str(nilai))
        self.lbl_sub.setText(sub)


class BarisKpi(QWidget):
    """Deretan kartu KPI. daftar = [(judul, warna), ...]; isi lewat set(indeks, nilai, sub)."""

    def __init__(self, daftar):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.kartu = [KartuKpi(judul, warna) for judul, warna in daftar]
        for k in self.kartu:
            lay.addWidget(k, 1)

    def set(self, indeks: int, nilai, sub: str = ""):
        self.kartu[indeks].set(nilai, sub)


def isi_tabel(tabel, baris, kanan=(), latar=None):
    """Isi tabel dari list baris (list of list). latar = warna per baris (atau None)."""
    tabel.setRowCount(len(baris))
    for i, row in enumerate(baris):
        for j, v in enumerate(row):
            item = QTableWidgetItem(str(v))
            if j in kanan:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if latar and latar[i]:
                item.setBackground(QColor(latar[i]))
                item.setForeground(QColor("#0F172A"))
            tabel.setItem(i, j, item)
    tabel.resizeColumnsToContents()
    tabel.horizontalHeader().setStretchLastSection(True)


def buat_waktu() -> QDateTimeEdit:
    w = QDateTimeEdit(QDateTime.currentDateTime())
    w.setDisplayFormat(FORMAT_WAKTU)
    w.setCalendarPopup(True)
    return w


def waktu_str(editor: QDateTimeEdit) -> str:
    return editor.dateTime().toString(FORMAT_WAKTU)


def ke_qdatetime(teks: str) -> QDateTime:
    d = QDateTime.fromString(teks, FORMAT_WAKTU)
    return d if d.isValid() else QDateTime.currentDateTime()


def buat_shift() -> QComboBox:
    """Combo shift diisi manual: sengaja tanpa nilai awal (tidak diambil dari jam)."""
    cb = QComboBox()
    cb.addItem("- pilih shift -")
    for s in Shift:
        cb.addItem(s.label)
    return cb


def ambil_shift(cb: QComboBox):
    """Kembalikan 1/2/3, atau None bila belum dipilih (indeks 0)."""
    return cb.currentIndex() or None


def ekspor_tabel(parent, repo, judul, kolom, baris, info="", angka=()):
    """Dialog simpan + ekspor ke Excel/PDF/CSV. Hanya untuk peran yang diizinkan."""
    if not repo.boleh_ekspor():
        return QMessageBox.warning(parent, "Tidak diizinkan",
                                   "Akun Anda tidak memiliki izin ekspor data.")
    nama = judul.lower().replace(" ", "_") + datetime.now().strftime("_%Y%m%d_%H%M")
    path, filt = QFileDialog.getSaveFileName(
        parent, "Ekspor Data", nama, "Excel (*.xlsx);;PDF (*.pdf);;CSV (*.csv)")
    if not path:
        return
    if Path(path).suffix.lower() not in (".xlsx", ".pdf", ".csv"):
        path += ".pdf" if "PDF" in filt else ".csv" if "CSV" in filt else ".xlsx"
    info = f"{info}   |   Diekspor oleh {repo.oleh} pada " \
           f"{datetime.now().strftime('%Y-%m-%d %H:%M')}".strip(" |")
    try:
        export.ekspor(path, judul, kolom, baris, info, angka)
    except ImportError as e:
        return QMessageBox.critical(
            parent, "Pustaka belum terpasang",
            f"Jalankan:  pip install openpyxl reportlab\n\n{e}")
    except OSError as e:
        return QMessageBox.critical(
            parent, "Gagal menyimpan", f"{e}\n\nPastikan file tidak sedang dibuka di aplikasi lain.")
    QMessageBox.information(parent, "Ekspor", f"{len(baris)} baris disimpan ke:\n{path}")
