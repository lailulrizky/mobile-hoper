"""Panel admin: kelola pengguna (tambah operator/supervisor, reset password, nonaktifkan)."""
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QInputDialog, QLineEdit, QMessageBox,
    QVBoxLayout, QWidget)

from models import Role, User
from ui_common import KartuForm, buat_tabel, isi_tabel, tombol_aksi
from users import MIN_PASSWORD, UserRepository


class PanelPengguna(QWidget):
    KOLOM = ["Username", "Nama", "Peran", "Status", "Wajib ganti password"]
    PERAN_BARU = [Role.OPERATOR, Role.SUPERVISOR]

    def __init__(self, users: UserRepository, pengguna: User):
        super().__init__()
        self.users, self.pengguna, self.data = users, pengguna, []

        self.username, self.nama, self.password = QLineEdit(), QLineEdit(), QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.peran = QComboBox()
        self.peran.addItems([r.label for r in self.PERAN_BARU])
        kotak = KartuForm("Tambah Pengguna")
        form = kotak.form
        form.addRow("Username", self.username)
        form.addRow("Nama lengkap", self.nama)
        form.addRow("Peran", self.peran)
        form.addRow(f"Password awal (min. {MIN_PASSWORD})", self.password)
        form.addRow(tombol_aksi("Tambah", self.tambah, "primer"))
        kotak.setFixedWidth(340)

        self.tabel = buat_tabel(self.KOLOM)
        aksi = QHBoxLayout()
        for teks, fn in [("Reset Password", self.reset_password),
                         ("Aktifkan / Nonaktifkan", self.ganti_aktif)]:
            aksi.addWidget(tombol_aksi(teks, fn))
        aksi.addStretch()
        kanan = QVBoxLayout()
        kanan.addWidget(self.tabel)
        kanan.addLayout(aksi)

        kiri = QVBoxLayout()
        kiri.addWidget(kotak)
        kiri.addStretch()
        lay = QHBoxLayout(self)
        lay.addLayout(kiri)
        lay.addLayout(kanan, 1)
        self.refresh()

    def refresh(self, *_):
        self.data = self.users.daftar()
        isi_tabel(self.tabel,
                  [[u.username, u.nama, u.role.label, "Aktif" if u.aktif else "Nonaktif",
                    "Ya" if u.wajib_ganti else "Tidak"] for u in self.data],
                  latar=[None if u.aktif else "#E2E8F0" for u in self.data])

    def tambah(self):
        try:
            self.users.tambah(self.username.text(), self.nama.text(),
                              self.PERAN_BARU[self.peran.currentIndex()], self.password.text())
        except ValueError as e:
            return QMessageBox.warning(self, "Gagal", str(e))
        for f in (self.username, self.nama, self.password):
            f.clear()
        self.refresh()

    def _terpilih(self):
        r = self.tabel.currentRow()
        if r < 0:
            QMessageBox.information(self, "Pilih pengguna", "Pilih satu pengguna di tabel dulu.")
            return None
        return self.data[r]

    def reset_password(self):
        u = self._terpilih()
        if not u:
            return
        teks, ok = QInputDialog.getText(
            self, "Reset Password", f"Password sementara untuk {u.username}:",
            QLineEdit.Password)
        if not ok:
            return
        try:
            self.users.reset_password(u.id, teks)
        except ValueError as e:
            return QMessageBox.warning(self, "Gagal", str(e))
        self.refresh()
        QMessageBox.information(self, "Berhasil",
                                f"Password {u.username} direset. Wajib diganti saat login.")

    def ganti_aktif(self):
        u = self._terpilih()
        if not u:
            return
        if u.id == self.pengguna.id:
            return QMessageBox.warning(self, "Tidak bisa", "Anda tidak bisa menonaktifkan akun sendiri.")
        try:
            self.users.set_aktif(u.id, not u.aktif)
        except ValueError as e:
            return QMessageBox.warning(self, "Gagal", str(e))
        self.refresh()
