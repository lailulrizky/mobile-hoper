"""Dialog login (tampilan kartu) dan ganti password.
Logo opsional: taruh file di  assets/company_logo.png  (di samping file ini)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout)

from config import cari_aset
from models import User
from users import MIN_PASSWORD, UserRepository
from versi import VERSI_APLIKASI

NAMA_APLIKASI = "PENERIMAAN & PEMAKAIAN HOPER"
LOGO = cari_aset("company_logo.png")

GAYA = """
    QDialog {
        background-color: #F1F5F9;
        font-family: Segoe UI;
    }
    QFrame#login_card {
        background-color: white;
        border-radius: 14px;
    }
    QLabel#title {
        font-size: 22px;
        font-weight: bold;
        color: #17365D;
    }
    QLabel#subtitle {
        font-size: 12px;
        color: #64748B;
    }
    QLabel#field {
        font-size: 11px;
        font-weight: bold;
        color: #475569;
    }
    QLineEdit {
        background-color: #F8FAFC;
        border: 1px solid #CBD5E1;
        border-radius: 7px;
        padding: 11px;
        font-size: 13px;
    }
    QLineEdit:focus {
        border: 1px solid #2563EB;
    }
    QPushButton {
        background-color: #E2E8F0;
        border: none;
        border-radius: 7px;
        padding: 8px 14px;
    }
    QPushButton:hover {
        background-color: #CBD5E1;
    }
    QPushButton#login_button {
        background-color: #2563EB;
        color: white;
        font-weight: bold;
        padding: 12px;
    }
    QPushButton#login_button:hover {
        background-color: #1D4ED8;
    }
"""


def _label_field(teks: str) -> QLabel:
    lbl = QLabel(teks)
    lbl.setObjectName("field")
    return lbl


class LoginDialog(QDialog):
    def __init__(self, users: UserRepository):
        super().__init__()
        self.users = users
        self.pengguna = None
        self.setWindowTitle("Login - " + NAMA_APLIKASI.title())
        self.resize(560, 620)
        self.setMinimumSize(440, 520)
        self.setStyleSheet(GAYA)
        self._buat_antarmuka()

    def _buat_antarmuka(self):
        utama = QVBoxLayout(self)
        utama.setContentsMargins(25, 25, 25, 25)
        utama.addStretch()

        kartu = QFrame()
        kartu.setObjectName("login_card")
        kartu.setMaximumWidth(440)
        lay = QVBoxLayout(kartu)
        lay.setContentsMargins(35, 30, 35, 30)
        lay.setSpacing(12)

        # logo perusahaan (dilewati bila file tidak ada)
        pix = QPixmap(LOGO)
        if not pix.isNull():
            logo = QLabel()
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setPixmap(pix.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
            lay.addWidget(logo)

        judul = QLabel(NAMA_APLIKASI)
        judul.setObjectName("title")
        judul.setAlignment(Qt.AlignmentFlag.AlignCenter)
        judul.setWordWrap(True)
        sub = QLabel("LOGIN SISTEM")
        sub.setObjectName("subtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(judul)
        lay.addWidget(sub)
        lay.addSpacing(15)

        lay.addWidget(_label_field("USERNAME"))
        self.username = QLineEdit()
        self.username.setPlaceholderText("Masukkan username")
        lay.addWidget(self.username)

        lay.addWidget(_label_field("PASSWORD"))
        baris = QHBoxLayout()
        self.password = QLineEdit()
        self.password.setPlaceholderText("Masukkan password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.returnPressed.connect(self._masuk)
        self.username.returnPressed.connect(self.password.setFocus)
        self.tampil = QPushButton("Tampil")
        self.tampil.setCheckable(True)
        self.tampil.setMinimumWidth(75)
        self.tampil.clicked.connect(self._toggle_password)
        baris.addWidget(self.password)
        baris.addWidget(self.tampil)
        lay.addLayout(baris)

        tombol = QPushButton("MASUK")
        tombol.setObjectName("login_button")
        tombol.setMinimumHeight(42)
        tombol.setDefault(True)
        tombol.clicked.connect(self._masuk)
        lay.addSpacing(10)
        lay.addWidget(tombol)

        footer = QLabel(f"Sistem Pencatatan Mobilitas Material  |  v{VERSI_APLIKASI}")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("color: #94A3B8; font-size: 10px;")
        lay.addWidget(footer)

        utama.addWidget(kartu, alignment=Qt.AlignmentFlag.AlignCenter)
        utama.addStretch()

    def _toggle_password(self, dicentang: bool):
        self.password.setEchoMode(QLineEdit.EchoMode.Normal if dicentang
                                  else QLineEdit.EchoMode.Password)
        self.tampil.setText("Sembunyi" if dicentang else "Tampil")

    def _masuk(self):
        username, password = self.username.text().strip(), self.password.text()
        if not username or not password:
            return QMessageBox.warning(self, "Peringatan",
                                       "Masukkan username dan password.")
        u = self.users.login(username, password)
        self.users.catat_login(username, u is not None)
        if u is None:
            QMessageBox.warning(self, "Login Gagal",
                                "Username atau password salah, atau akun nonaktif.")
            self.password.clear()
            self.password.setFocus()
            return
        self.pengguna = u
        self.accept()

    @staticmethod
    def masuk(users: UserRepository):
        """Tampilkan login. Kembalikan User, atau None bila dibatalkan."""
        dlg = LoginDialog(users)
        if not dlg.exec():
            return None
        u = dlg.pengguna
        if u.wajib_ganti:                      # akun baru / password direset admin
            gp = GantiPasswordDialog(users, u, wajib=True)
            if not gp.exec():
                return None
            u.wajib_ganti = False
        return u


class GantiPasswordDialog(QDialog):
    def __init__(self, users: UserRepository, pengguna: User, wajib: bool = False):
        super().__init__()
        self.users, self.pengguna, self.wajib = users, pengguna, wajib
        self.setWindowTitle("Ganti Password" + (" (wajib)" if wajib else ""))
        self.setMinimumWidth(380)
        self.setStyleSheet(GAYA)
        self.lama, self.baru, self.ulang = QLineEdit(), QLineEdit(), QLineEdit()
        for e in (self.lama, self.baru, self.ulang):
            e.setEchoMode(QLineEdit.EchoMode.Password)
        form = QFormLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(10)
        if wajib:
            form.addRow(QLabel("Anda harus mengganti password sebelum melanjutkan."))
        else:
            form.addRow("Password lama", self.lama)
        form.addRow(f"Password baru (min. {MIN_PASSWORD})", self.baru)
        form.addRow("Ulangi password baru", self.ulang)
        tombol = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        tombol.accepted.connect(self._cek)
        tombol.rejected.connect(self.reject)
        form.addRow(tombol)

    def _cek(self):
        u = self.pengguna.username
        if not self.wajib and self.users.login(u, self.lama.text()) is None:
            return QMessageBox.warning(self, "Gagal", "Password lama salah.")
        if self.baru.text() != self.ulang.text():
            return QMessageBox.warning(self, "Gagal", "Konfirmasi password tidak sama.")
        if self.users.login(u, self.baru.text()) is not None:
            return QMessageBox.warning(self, "Gagal",
                                       "Password baru tidak boleh sama dengan yang lama.")
        try:
            self.users.ganti_password(self.pengguna.id, self.baru.text())
        except ValueError as e:
            return QMessageBox.warning(self, "Gagal", str(e))
        self.accept()
