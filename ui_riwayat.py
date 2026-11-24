"""Panel riwayat aktivitas (filter, ekspor) + dialog koreksi data oleh admin."""
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout, QWidget)

from database import Repository
from models import Aktivitas, Shift
from theme import BIRU, HIJAU, KUNING
from ui_common import (FORMAT_TANGGAL, BarisKpi, ambil_shift, buat_shift, buat_tabel,
                       buat_waktu, bungkus_kartu, ekspor_tabel, isi_tabel, ke_qdatetime,
                       tombol_aksi, waktu_str)
from ui_operator import RiwayatDialog

TIPE = [None, "TERIMA", "PASANG", "LEPAS", "REJECT"]
APPROVAL = [None, "pending", "approved"]


class KoreksiDialog(QDialog):
    """Admin memperbaiki kekeliruan pengisian. Alasan wajib; perubahan tercatat di riwayat
    dan approval aktivitas tersebut direset (harus disetujui ulang)."""

    def __init__(self, a: Aktivitas, repo: Repository, parent=None):
        super().__init__(parent)
        self.a, self.repo = a, repo
        self.setWindowTitle(f"Koreksi {a.label} - {a.objek}")
        self.setMinimumWidth(380)
        self.waktu = buat_waktu()
        self.waktu.setDateTime(ke_qdatetime(a.waktu))
        self.shift = buat_shift()
        self.shift.setCurrentIndex(a.shift or 0)
        self.alasan = QLineEdit()
        form = QFormLayout(self)
        if a.aktivitas == "TERIMA":
            self.no_hoper = self._pilihan(repo.daftar_hoper(), a.no_hoper)
            self.trace = QLineEdit(a.kode_trace)
            self.jenis = self._pilihan(repo.daftar_jenis(), a.jenis)
            self.berat = self._spin(a.berat or 0)
            form.addRow("No. Hoper", self.no_hoper)
            form.addRow("Kode Trace", self.trace)
            form.addRow("Jenis", self.jenis)
            form.addRow("Berat diterima", self.berat)
            form.addRow("Waktu terima", self.waktu)
            form.addRow("Shift terima", self.shift)
        elif a.aktivitas == "PASANG":
            self.mesin = self._pilihan(repo.daftar_mesin(), a.mesin or "")
            self.operator = QLineEdit(a.operator or "")
            self.catatan = QLineEdit(a.catatan or "")
            form.addRow("Mesin", self.mesin)
            form.addRow("Operator", self.operator)
            form.addRow("Waktu pasang", self.waktu)
            form.addRow("Shift pasang", self.shift)
            form.addRow("Catatan", self.catatan)
        elif a.aktivitas == "REJECT":
            self.operator = QLineEdit(a.operator or "")
            self.jenis = self._pilihan(repo.daftar_jenis(), a.jenis)
            self.berat = self._spin(a.berat or 0)
            self.catatan = QLineEdit(a.catatan or "")
            form.addRow("Waktu", self.waktu)
            form.addRow("Shift", self.shift)
            form.addRow("Operator", self.operator)
            form.addRow("Jenis material", self.jenis)
            form.addRow("Berat", self.berat)
            form.addRow("Catatan", self.catatan)
        else:
            self.sisa = self._spin(a.berat or 0)
            form.addRow("Waktu lepas", self.waktu)
            form.addRow("Shift lepas", self.shift)
            form.addRow("Sisa berat", self.sisa)
        form.addRow("Alasan koreksi *", self.alasan)
        tombol = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        tombol.accepted.connect(self._simpan)
        tombol.rejected.connect(self.reject)
        form.addRow(tombol)

    @staticmethod
    def _pilihan(daftar, saat_ini: str) -> QComboBox:
        """Combo dari Master Data; nilai saat ini selalu ada walau sudah nonaktif."""
        cb = QComboBox()
        cb.addItems(daftar)
        if saat_ini and cb.findText(saat_ini) < 0:
            cb.addItem(saat_ini)
        cb.setCurrentText(saat_ini)
        return cb

    @staticmethod
    def _spin(nilai: float) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(0, 1_000_000)
        s.setDecimals(2)
        s.setSuffix(" kg")
        s.setValue(nilai)
        return s

    def _simpan(self):
        a, shift, waktu, alasan = self.a, ambil_shift(self.shift), waktu_str(self.waktu), \
            self.alasan.text()
        try:
            if a.aktivitas == "TERIMA":
                self.repo.koreksi_terima(a.hoper_id, self.no_hoper.currentText(), self.trace.text(),
                                         self.jenis.currentText(), self.berat.value(),
                                         waktu, shift, alasan)
            elif a.aktivitas == "PASANG":
                self.repo.koreksi_pasang(a.ref_id, self.mesin.currentText(),
                                         self.operator.text(), waktu, shift,
                                         self.catatan.text(), alasan)
            elif a.aktivitas == "REJECT":
                self.repo.koreksi_reject(a.ref_id, waktu, shift, self.operator.text(),
                                         self.berat.value(), self.jenis.currentText(),
                                         self.catatan.text(), alasan)
            else:
                self.repo.koreksi_lepas(a.ref_id, waktu, shift, self.sisa.value(), alasan)
        except (ValueError, PermissionError) as e:
            return QMessageBox.warning(self, "Koreksi gagal", str(e))
        self.accept()


class RiwayatPanel(QWidget):
    """Daftar semua aktivitas dengan filter (tanggal shift, shift, aktivitas, approval, cari).
    Tombol ekspor mengekspor persis data yang sedang tampil."""

    def __init__(self, repo: Repository, boleh_koreksi: bool = False):
        super().__init__()
        self.repo, self.data = repo, []

        self.pakai_tgl = QCheckBox("Rentang tanggal shift:")
        self.dari = QDateEdit(QDate.currentDate().addDays(-7))
        self.sampai = QDateEdit(QDate.currentDate())
        for d in (self.dari, self.sampai):
            d.setDisplayFormat(FORMAT_TANGGAL)
            d.setCalendarPopup(True)
            d.setEnabled(False)
        self.shift = QComboBox()
        self.shift.addItems(["Semua shift"] + [s.label for s in Shift])
        self.tipe = QComboBox()
        self.tipe.addItems(["Semua aktivitas", "Penerimaan", "Pemasangan", "Pelepasan",
                            "Material Reject"])
        self.approval = QComboBox()
        self.approval.addItems(["Semua approval", "Pending", "Disetujui"])
        self.cari = QLineEdit()
        self.cari.setPlaceholderText("Cari hoper / trace / jenis / mesin / operator...")

        self.tabel = buat_tabel(Aktivitas.KOLOM)
        self.kpi = BarisKpi([("TOTAL AKTIVITAS", BIRU), ("PENDING", KUNING),
                             ("DISETUJUI", HIJAU)])

        baris1 = QHBoxLayout()
        for w in (self.pakai_tgl, self.dari, QLabel("s/d"), self.sampai):
            baris1.addWidget(w)
        baris1.addStretch()
        baris2 = QHBoxLayout()
        for w in (self.shift, self.tipe, self.approval):
            baris2.addWidget(w)
        baris2.addWidget(self.cari, 1)

        aksi = QHBoxLayout()
        tombol = [("Riwayat Detail", self.lihat_hoper, "")]
        if boleh_koreksi:
            tombol.insert(0, ("Koreksi Data", self.koreksi, "primer"))
        tombol.append(("Ekspor Excel/PDF", self.ekspor, ""))
        for teks, fn, varian in tombol:
            aksi.addWidget(tombol_aksi(teks, fn, varian))
        aksi.addStretch()

        filter_lay = QVBoxLayout()
        filter_lay.addLayout(baris1)
        filter_lay.addLayout(baris2)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(self.kpi)
        lay.addWidget(bungkus_kartu(filter_lay))
        lay.addWidget(self.tabel, 1)
        lay.addLayout(aksi)

        self.pakai_tgl.toggled.connect(self._saat_tgl)
        for sinyal in (self.dari.dateChanged, self.sampai.dateChanged,
                       self.shift.currentIndexChanged, self.tipe.currentIndexChanged,
                       self.approval.currentIndexChanged, self.cari.textChanged):
            sinyal.connect(self.refresh)
        self.refresh()

    def _saat_tgl(self, aktif: bool):
        self.dari.setEnabled(aktif)
        self.sampai.setEnabled(aktif)
        self.refresh()

    def _filter(self) -> dict:
        f = {"shift": self.shift.currentIndex() or None,
             "tipe": TIPE[self.tipe.currentIndex()],
             "approval": APPROVAL[self.approval.currentIndex()],
             "cari": self.cari.text().strip()}
        if self.pakai_tgl.isChecked():
            f["dari"] = self.dari.date().toString(FORMAT_TANGGAL)
            f["sampai"] = self.sampai.date().toString(FORMAT_TANGGAL)
        return f

    def _info(self) -> str:
        f = self._filter()
        bagian = []
        if "dari" in f:
            bagian.append(f"Tanggal shift {f['dari']} s/d {f['sampai']}")
        bagian += [self.shift.currentText(), self.tipe.currentText(),
                   self.approval.currentText()]
        if f["cari"]:
            bagian.append(f'Cari: "{f["cari"]}"')
        return "Filter: " + " | ".join(bagian)

    def refresh(self, *_):
        self.data = self.repo.aktivitas(**self._filter())
        isi_tabel(self.tabel, [a.baris() for a in self.data], kanan=Aktivitas.IDX_ANGKA,
                  latar=["#ECFDF5" if a.disetujui else None for a in self.data])
        pending = sum(1 for a in self.data if not a.disetujui)
        self.kpi.set(0, len(self.data))
        self.kpi.set(1, pending)
        self.kpi.set(2, len(self.data) - pending)

    def terpilih(self):
        r = self.tabel.currentRow()
        if r < 0:
            QMessageBox.information(self, "Pilih data", "Pilih satu baris di tabel dulu.")
            return None
        return self.data[r]

    def koreksi(self):
        a = self.terpilih()
        if a and KoreksiDialog(a, self.repo, self).exec():
            self.refresh()

    def lihat_hoper(self):
        a = self.terpilih()
        if a:
            RiwayatDialog(a.judul_riwayat, self.repo.riwayat_aktivitas(a), self).exec()

    def ekspor(self):
        ekspor_tabel(self, self.repo, "Riwayat Aktivitas", Aktivitas.KOLOM,
                     [a.baris() for a in self.data], self._info(), Aktivitas.IDX_ANGKA)
