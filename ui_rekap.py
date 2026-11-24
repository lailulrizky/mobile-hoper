"""Rekap per shift: penerimaan, hoper digunakan, dan material reject.
Admin: lihat & ekspor.  Supervisor: lihat, setujui rekap, & ekspor."""
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget)

from database import Repository
from models import RekapShift, Shift
from theme import BIRU, HIJAU, MERAH, NAVY
from ui_common import (FORMAT_TANGGAL, BarisKpi, buat_tabel, bungkus_kartu, ekspor_tabel,
                       isi_tabel, tombol_aksi)

WARNA_DISETUJUI = "#ECFDF5"      # hijau muda
WARNA_BERUBAH = "#FEF3C7"        # kuning: data berubah sejak disetujui


class RekapPanel(QWidget):
    """Tabel rekap per (tanggal shift, shift) + rincian per jenis material."""

    def __init__(self, repo: Repository, boleh_setuju: bool = False):
        super().__init__()
        self.repo, self.data = repo, []

        self.pakai_tgl = QCheckBox("Rentang tanggal shift:")
        self.pakai_tgl.setChecked(True)
        self.dari = QDateEdit(QDate.currentDate().addDays(-6))
        self.sampai = QDateEdit(QDate.currentDate())
        for d in (self.dari, self.sampai):
            d.setDisplayFormat(FORMAT_TANGGAL)
            d.setCalendarPopup(True)
        self.shift = QComboBox()
        self.shift.addItems(["Semua shift"] + [s.label for s in Shift])

        self.kpi = BarisKpi([("HOPER DITERIMA", BIRU), ("HOPER DIGUNAKAN", NAVY),
                             ("MATERIAL REJECT", MERAH), ("REKAP DISETUJUI", HIJAU)])
        self.tabel = buat_tabel(RekapShift.KOLOM, multi=True)
        self.judul_detail = QLabel()
        self.judul_detail.setObjectName("muted")
        self.detail = buat_tabel(["Jenis Material", "Diterima (kg)", "Reject (kg)"])

        baris = QHBoxLayout()
        for w in (self.pakai_tgl, self.dari, QLabel("s/d"), self.sampai, self.shift):
            baris.addWidget(w)
        baris.addStretch()

        aksi = QHBoxLayout()
        if boleh_setuju:
            aksi.addWidget(tombol_aksi("Setujui Rekap Terpilih", self.setujui, "sukses"))
        aksi.addWidget(tombol_aksi("Ekspor Rekap", self.ekspor))
        aksi.addWidget(tombol_aksi("Ekspor per Jenis", self.ekspor_jenis))
        aksi.addStretch()

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(self.kpi)
        lay.addWidget(bungkus_kartu(baris))
        lay.addWidget(self.tabel, 3)
        lay.addWidget(self.judul_detail)
        lay.addWidget(self.detail, 2)
        lay.addLayout(aksi)

        self.pakai_tgl.toggled.connect(self._saat_tgl)
        for sinyal in (self.dari.dateChanged, self.sampai.dateChanged,
                       self.shift.currentIndexChanged):
            sinyal.connect(self.refresh)
        self.tabel.itemSelectionChanged.connect(self._isi_detail)
        self.refresh()

    def _saat_tgl(self, aktif: bool):
        self.dari.setEnabled(aktif)
        self.sampai.setEnabled(aktif)
        self.refresh()

    def _filter(self) -> dict:
        f = {"shift": self.shift.currentIndex() or None}
        if self.pakai_tgl.isChecked():
            f["dari"] = self.dari.date().toString(FORMAT_TANGGAL)
            f["sampai"] = self.sampai.date().toString(FORMAT_TANGGAL)
        return f

    def _info(self) -> str:
        f = self._filter()
        tgl = f"Tanggal shift {f['dari']} s/d {f['sampai']}" if "dari" in f else "Semua tanggal"
        return f"Filter: {tgl} | {self.shift.currentText()}"

    # ---- tampilan
    def refresh(self, *_):
        self.data = self.repo.rekap_shift(**self._filter())
        isi_tabel(self.tabel, [r.baris() for r in self.data], kanan=RekapShift.IDX_ANGKA,
                  latar=[WARNA_DISETUJUI if r.disetujui else
                         (WARNA_BERUBAH if r.berubah else None) for r in self.data])
        d = self.data
        self.kpi.set(0, sum(r.hoper_diterima for r in d),
                     f"{sum(r.berat_diterima for r in d):.2f} kg")
        self.kpi.set(1, sum(r.hoper_digunakan for r in d),
                     f"{sum(r.pemasangan for r in d)} pemasangan")
        self.kpi.set(2, f"{sum(r.berat_reject for r in d):.2f}",
                     f"kg  ({sum(r.reject_catatan for r in d)} catatan)")
        self.kpi.set(3, f"{sum(1 for r in d if r.disetujui)}/{len(d)}", "shift disetujui")
        self._isi_detail()

    def _baris_terpilih(self):
        return sorted({i.row() for i in self.tabel.selectionModel().selectedRows()})

    def _isi_detail(self, *_):
        """Rincian per jenis untuk baris terpilih (atau semua baris bila tidak ada pilihan)."""
        pilih = self._baris_terpilih()
        sumber = [self.data[i] for i in pilih] if pilih else self.data
        total = {}
        for rk in sumber:
            for jenis, (terima, reject) in rk.per_jenis.items():
                t = total.setdefault(jenis, [0.0, 0.0])
                t[0] += terima
                t[1] += reject
        self.judul_detail.setText(
            "Rincian per jenis material - " +
            (f"{len(pilih)} shift terpilih" if pilih else "semua shift yang tampil"))
        isi_tabel(self.detail, [[j, f"{v[0]:.2f}", f"{v[1]:.2f}"] for j, v in sorted(total.items())],
                  kanan=(1, 2))

    # ---- aksi
    def setujui(self):
        pilih = [self.data[i] for i in self._baris_terpilih()]
        if not pilih:
            return QMessageBox.information(self, "Pilih data",
                                           "Pilih satu atau beberapa baris rekap dulu.")
        belum = [r for r in pilih if not r.disetujui]
        if not belum:
            return QMessageBox.information(self, "Sudah disetujui",
                                           "Semua rekap yang dipilih sudah disetujui.")
        if QMessageBox.question(self, "Konfirmasi Approval Rekap",
                                f"Setujui {len(belum)} rekap shift?") != QMessageBox.Yes:
            return
        ok, gagal = 0, []
        for rk in belum:
            try:
                self.repo.setujui_rekap(rk.tgl_shift, rk.shift)
                ok += 1
            except PermissionError as e:
                return QMessageBox.warning(self, "Tidak diizinkan", str(e))
            except ValueError as e:
                gagal.append(f"{rk.tgl_shift} shift {rk.shift}: {str(e).splitlines()[0]}")
        self.refresh()
        pesan = f"{ok} rekap shift disetujui."
        if gagal:
            pesan += "\n\nBelum bisa disetujui:\n" + "\n".join(gagal)
        QMessageBox.information(self, "Approval Rekap", pesan)

    def ekspor(self):
        ekspor_tabel(self, self.repo, "Rekap Shift", RekapShift.KOLOM,
                     [r.baris() for r in self.data], self._info(), RekapShift.IDX_ANGKA)

    def ekspor_jenis(self):
        baris = [b for r in self.data for b in r.baris_jenis()]
        ekspor_tabel(self, self.repo, "Rekap per Jenis Material", RekapShift.KOLOM_JENIS,
                     baris, self._info(), (3, 4))
