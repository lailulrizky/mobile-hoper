"""Aplikasi Penerimaan & Pemakaian Material (PySide6) - dengan login berbasis peran.
Jalankan: python app.py   |   Install: pip install -r requirements.txt

Peran:
  operator    -> halaman penerimaan, pemakaian & reject (tanpa ekspor)
  admin       -> riwayat, koreksi, rekap, master data, kelola pengguna, sistem & audit
  supervisor  -> approval aktivitas & rekap per shift, riwayat, ekspor
"""
import platform
import sys
from datetime import datetime

from PySide6.QtCore import QEvent, QLockFile, QObject, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QTabWidget,
    QVBoxLayout, QWidget)

from config import lokasi_app, muat_konfigurasi
from database import Repository
from models import Role, User
from pencadangan import Pencadangan
from sistem import DatabaseBermasalah, Konteks, pasang_excepthook, siapkan_database, siapkan_log
from theme import terapkan_tema
from ui_common import tombol_aksi
from ui_login import GantiPasswordDialog, LoginDialog
from ui_master import PanelMaster
from ui_operator import HalamanOperator, TabelHoper
from ui_pengguna import PanelPengguna
from ui_rekap import RekapPanel
from ui_riwayat import RiwayatPanel
from ui_sistem import PanelSistem
from ui_supervisor import HalamanApproval
from users import UserRepository
from versi import VERSI_APLIKASI


HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


class _PengamatAktivitas(QObject):
    """Setiap klik / ketikan / gerakan mouse menyegarkan timer logout otomatis."""

    def __init__(self, timer: QTimer):
        super().__init__()
        self.timer = timer
        self.jenis = (QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress,
                      QEvent.Type.MouseMove, QEvent.Type.Wheel)

    def eventFilter(self, obj, ev):
        if ev.type() in self.jenis:
            self.timer.start()
        return False


class MainWindow(QMainWindow):
    def __init__(self, repo: Repository, users: UserRepository, pengguna: User, ctx: Konteks):
        super().__init__()
        self.repo, self.users, self.pengguna, self.ctx = repo, users, pengguna, ctx
        self.keluar_akun = False
        self.setWindowTitle(f"Penerimaan & Pemakaian Material - "
                            f"{pengguna.nama} ({pengguna.role.label})")
        self._ukuran_awal()
        pusat = QWidget()                       # bilah atas (logout) + halaman sesuai peran
        lay = QVBoxLayout(pusat)
        lay.setContentsMargins(12, 12, 12, 8)
        lay.setSpacing(10)
        lay.addWidget(self._header())
        lay.addWidget(self._halaman(), 1)
        self.setCentralWidget(pusat)
        self._menu()
        self.statusBar().showMessage(
            f"Masuk sebagai {pengguna.username} - {pengguna.role.label}   |   v{VERSI_APLIKASI}")
        if ctx.cfg.logout_otomatis_menit > 0:
            self._pasang_logout_otomatis(ctx.cfg.logout_otomatis_menit)

    def _ukuran_awal(self):
        """Ukuran awal menyesuaikan layar. Sengaja TIDAK memakai setMinimumSize: batas
        minimum paksa membuat isi jendela terjepit dan komponen saling bertumpuk."""
        layar = self.screen()
        if layar is None:
            return self.resize(1280, 720)
        g = layar.availableGeometry()
        self.resize(min(1360, g.width() - 40), min(800, g.height() - 60))

    def _halaman(self):
        role = self.pengguna.role
        if role == Role.OPERATOR:
            return HalamanOperator(self.repo, boleh_ekspor=False)
        tab = QTabWidget()
        if role == Role.ADMIN:
            tab.addTab(RiwayatPanel(self.repo, boleh_koreksi=True), "Riwayat & Koreksi")
            tab.addTab(RekapPanel(self.repo, boleh_setuju=False), "Rekap Shift")
            tab.addTab(PanelMaster(self.repo), "Master Data")
            tab.addTab(TabelHoper(self.repo, boleh_ekspor=True), "Data Hoper")
            tab.addTab(PanelPengguna(self.users, self.pengguna), "Pengguna")
            tab.addTab(PanelSistem(self.repo, self.ctx), "Sistem")
        else:  # supervisor
            tab.addTab(HalamanApproval(self.repo), "Approval Shift")
            tab.addTab(RekapPanel(self.repo, boleh_setuju=True), "Rekap Shift")
            tab.addTab(RiwayatPanel(self.repo, boleh_koreksi=False), "Riwayat & Ekspor")
        tab.currentChanged.connect(lambda _: self._segarkan(tab))
        return tab

    @staticmethod
    def _segarkan(tab: QTabWidget):
        halaman = tab.currentWidget()
        if hasattr(halaman, "refresh"):
            halaman.refresh()

    def _menu(self):
        menu = self.menuBar().addMenu("Akun")
        for teks, fn, pintas in [#("Ganti Password", self.ganti_password, None),
                                 ("Logout", self.logout, "Ctrl+L")]:
            aksi = QAction(teks, self)
            if pintas:
                aksi.setShortcut(pintas)
            aksi.triggered.connect(fn)
            menu.addAction(aksi)

    def _header(self) -> QFrame:
        """Bilah atas untuk semua peran: merek, tanggal/jam, identitas pengguna, Logout."""
        p = self.pengguna
        bar = QFrame()
        bar.setObjectName("header")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 10, 14, 10)
        lay.setSpacing(12)

        merek = QLabel("PENERIMAAN & PEMAKAIAN HOPER")
        merek.setObjectName("brand")
        self.lbl_jam = QLabel()
        self.lbl_jam.setObjectName("jam")

        inisial = "".join(k[0] for k in p.nama.split()[:2]).upper() or p.username[:1].upper()
        avatar = QLabel(inisial)
        avatar.setObjectName("avatar")
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setFixedSize(38, 38)
        nama = QLabel(p.nama)
        nama.setObjectName("user_nama")
        peran = QLabel(p.role.label.upper())
        peran.setObjectName("user_peran")
        identitas = QVBoxLayout()
        identitas.setSpacing(0)
        identitas.addWidget(nama)
        identitas.addWidget(peran)

        tombol = tombol_aksi("Logout", self.logout, "header")
        tombol.setToolTip("Keluar dari akun tanpa menutup aplikasi (Ctrl+L)")

        lay.addWidget(merek)
        lay.addStretch()
        lay.addWidget(self.lbl_jam)
        lay.addSpacing(14)
        lay.addWidget(avatar)
        lay.addLayout(identitas)
        lay.addSpacing(10)
        lay.addWidget(tombol)

        self._timer = QTimer(self)               # perbarui tanggal/jam tiap 30 detik
        self._timer.timeout.connect(self._perbarui_jam)
        self._timer.start(30_000)
        self._perbarui_jam()
        return bar

    def _perbarui_jam(self):
        n = datetime.now()
        self.lbl_jam.setText(f"{HARI[n.weekday()]}, {n.day} {BULAN[n.month - 1]} {n.year}"
                             f"   {n:%H:%M}")

    def ganti_password(self):
        GantiPasswordDialog(self.users, self.pengguna).exec()

    def _pasang_logout_otomatis(self, menit: int):
        """Opsional (config.json: logout_otomatis_menit > 0)."""
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.setInterval(menit * 60_000)
        self._idle.timeout.connect(self._logout_idle)
        self._pengamat = _PengamatAktivitas(self._idle)
        QApplication.instance().installEventFilter(self._pengamat)
        self._idle.start()

    def _logout_idle(self):
        self.ctx.log.info("Logout otomatis (tanpa aktivitas %s menit): %s",
                          self.ctx.cfg.logout_otomatis_menit, self.pengguna.username)
        self.keluar_akun = True
        QApplication.closeAllWindows()

    def closeEvent(self, event):
        if hasattr(self, "_pengamat"):
            QApplication.instance().removeEventFilter(self._pengamat)
        super().closeEvent(event)

    def logout(self):
        """Kembali ke layar login tanpa menutup aplikasi."""
        jawab = QMessageBox.question(self, "Logout",
                                     f"Keluar dari akun {self.pengguna.username}?")
        if jawab != QMessageBox.Yes:
            return
        self.keluar_akun = True
        self.close()


def tampilkan_error(pesan: str, berkas_log: str):
    QMessageBox.critical(
        None, "Terjadi kesalahan",
        "Terjadi kesalahan tak terduga pada aplikasi.\n\n"
        f"{pesan}\n\nRincian lengkap tersimpan di:\n{berkas_log}\n\n"
        "Catat jam kejadiannya dan hubungi admin. Data yang sudah disimpan tetap aman.")


def selftest() -> int:
    """Uji mandiri:  PenerimaanHoper.exe --selftest   (dipakai build_exe.bat).
    Membuat semua halaman, ekspor Excel & PDF, dan cadangan di folder sementara, lalu keluar.
    Hasil ditulis ke %TEMP%\\penerimaan_hoper_selftest.txt. Kode keluar: 0 = berhasil."""
    import logging
    import tempfile
    import traceback
    from pathlib import Path

    import export
    berkas = Path(tempfile.gettempdir()) / "penerimaan_hoper_selftest.txt"
    try:
        app = QApplication(sys.argv)
        terapkan_tema(app)
        folder = Path(tempfile.mkdtemp(prefix="hoper_selftest_"))
        cfg = muat_konfigurasi(folder / "config.json")
        cfg.folder_data, cfg.folder_cadangan, cfg.folder_log = \
            folder, folder / "cad", folder / "log"
        repo = Repository(str(cfg.jalur_db))
        users = UserRepository(repo.db)
        pengguna = users.login("admin", "admin123")
        repo.pengguna = pengguna
        ctx = Konteks(cfg, Pencadangan(cfg.jalur_db, cfg.folder_cadangan),
                      logging.getLogger("hoper"), [])
        MainWindow(repo, users, pengguna, ctx)          # membangun halaman admin + tema
        export.ekspor(str(folder / "uji.xlsx"), "Uji", ["A", "B"], [["1", "2"]])
        export.ekspor(str(folder / "uji.pdf"), "Uji", ["A", "B"], [["1", "2"]])
        Pencadangan(cfg.jalur_db, folder / "cad2").cadangkan("manual")
        for nama in ("uji.xlsx", "uji.pdf"):
            if not (folder / nama).stat().st_size:
                raise RuntimeError(f"{nama} kosong")
        berkas.write_text("OK", encoding="utf-8")
        return 0
    except Exception:
        berkas.write_text(traceback.format_exc(), encoding="utf-8")
        return 3


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    app = QApplication(sys.argv)
    terapkan_tema(app)
    cfg = muat_konfigurasi()
    log = siapkan_log(cfg.folder_log)
    pasang_excepthook(log, tampilkan_error, cfg.folder_log / "aplikasi.log")
    log.info("=== Aplikasi mulai: v%s | Python %s | folder aplikasi: %s",
             VERSI_APLIKASI, platform.python_version(), lokasi_app())

    kunci = None                                   # cegah aplikasi dibuka dua kali
    if cfg.satu_instans:
        cfg.folder_data.mkdir(parents=True, exist_ok=True)
        kunci = QLockFile(str(cfg.folder_data / "aplikasi.lock"))
        if not kunci.tryLock(200):
            QMessageBox.warning(None, "Sudah berjalan",
                                "Aplikasi sudah terbuka di komputer ini.\n"
                                "Gunakan jendela yang sudah ada.")
            return 1

    pencadangan = Pencadangan(cfg.jalur_db, cfg.folder_cadangan,
                              cfg.cadangan_tiap_jam, cfg.cadangan_simpan_hari)
    ctx = Konteks(cfg, pencadangan, log, list(cfg.peringatan))
    try:
        _, catatan = siapkan_database(cfg, pencadangan, log)
        ctx.catatan_awal += catatan
    except DatabaseBermasalah as e:
        log.critical("Database bermasalah: %s", e)
        QMessageBox.critical(None, "Database tidak bisa dibuka", str(e))
        return 1

    repo = Repository(str(cfg.jalur_db))
    users = UserRepository(repo.db)
    users.audit = repo.catat_audit
    for pesan in ctx.catatan_awal:
        QMessageBox.information(None, "Informasi", pesan)

    def cadangkan_bila_perlu():
        try:
            if pencadangan.perlu_cadangan():
                log.info("Cadangan otomatis: %s", pencadangan.cadangkan("otomatis").name)
        except Exception:
            log.exception("Cadangan otomatis gagal")

    cadangkan_bila_perlu()
    timer_cadangan = QTimer(app)                   # cek tiap 15 menit selama aplikasi terbuka
    timer_cadangan.timeout.connect(cadangkan_bila_perlu)
    timer_cadangan.start(15 * 60 * 1000)

    while True:
        pengguna = LoginDialog.masuk(users)
        if pengguna is None:
            break
        log.info("Login: %s (%s)", pengguna.username, pengguna.role.label)
        repo.pengguna = pengguna
        win = MainWindow(repo, users, pengguna, ctx)
        win.show()
        app.exec()
        users.catat_logout(pengguna.username)
        log.info("Logout: %s", pengguna.username)
        repo.pengguna = None
        if not win.keluar_akun:          # ditutup lewat tombol X -> keluar aplikasi
            break                        # (Logout -> kembali ke layar login)

    try:
        pencadangan.cadangkan("keluar")
    except Exception:
        log.exception("Cadangan saat keluar gagal")
    log.info("=== Aplikasi selesai")
    if kunci:
        kunci.unlock()
    return 0


if __name__ == "__main__":
    sys.exit(main())
