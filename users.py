"""Pengguna & autentikasi. Password disimpan sebagai hash PBKDF2 + salt (bukan teks asli)."""
import hashlib
import hmac
import os
import sqlite3
from typing import List, Optional

from models import Role, User

ITERASI = 200_000
MIN_PASSWORD = 6
ADMIN_AWAL = ("admin", "Administrator", "admin123")   # dibuat otomatis saat pertama jalan


def hash_password(password: str, salt: Optional[bytes] = None):
    salt = salt or os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERASI)
    return salt.hex(), h.hex()


class UserRepository:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.audit = None          # diisi aplikasi: fungsi(aksi, objek, detail, oleh)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT NOT NULL UNIQUE COLLATE NOCASE,
                nama        TEXT NOT NULL,
                role        TEXT NOT NULL,
                salt        TEXT NOT NULL,
                hash        TEXT NOT NULL,
                aktif       INTEGER NOT NULL DEFAULT 1,
                wajib_ganti INTEGER NOT NULL DEFAULT 1
            )""")
        self.db.commit()
        if not self.db.execute("SELECT 1 FROM users").fetchone():
            username, nama, password = ADMIN_AWAL
            self.tambah(username, nama, Role.ADMIN, password)

    def _audit(self, aksi: str, objek: str = "", detail: str = "", oleh=None):
        if self.audit:
            self.audit(aksi, objek, detail, oleh)

    def catat_login(self, username: str, berhasil: bool):
        """Catat percobaan login ke audit. Username yang tidak dikenal TIDAK disimpan apa
        adanya (operator kadang tak sengaja mengetik password di kolom username)."""
        nama = username.strip().lower()
        ada = self.db.execute("SELECT 1 FROM users WHERE username=?", (nama,)).fetchone()
        if berhasil:
            self._audit("LOGIN", nama, "", oleh=nama)
        else:
            self._audit("LOGIN_GAGAL", nama if ada else "(tidak dikenal)", "",
                        oleh=nama if ada else "-")

    def catat_logout(self, username: str):
        self._audit("LOGOUT", username, "", oleh=username)

    # ---- autentikasi
    def login(self, username: str, password: str) -> Optional[User]:
        r = self.db.execute("SELECT * FROM users WHERE username=? AND aktif=1",
                            (username.strip().lower(),)).fetchone()
        if r is None:
            hash_password(password)          # samakan waktu proses
            return None
        _, h = hash_password(password, bytes.fromhex(r["salt"]))
        return self._ke_user(r) if hmac.compare_digest(h, r["hash"]) else None

    # ---- kelola
    def daftar(self) -> List[User]:
        return [self._ke_user(r) for r in
                self.db.execute("SELECT * FROM users ORDER BY role, username")]

    def tambah(self, username: str, nama: str, role: Role, password: str,
               wajib_ganti: bool = True):
        username = username.strip().lower()
        if not username or not nama.strip():
            raise ValueError("Username dan nama wajib diisi.")
        if " " in username:
            raise ValueError("Username tidak boleh mengandung spasi.")
        self._cek_password(password)
        salt, h = hash_password(password)
        try:
            with self.db:
                self.db.execute(
                    "INSERT INTO users (username,nama,role,salt,hash,wajib_ganti) "
                    "VALUES (?,?,?,?,?,?)",
                    (username, nama.strip(), role.value, salt, h, int(wajib_ganti)))
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{username}' sudah dipakai.")
        self._audit("USER_TAMBAH", username, f"peran {role.label}")

    def reset_password(self, user_id: int, password: str):
        """Dipakai admin: password sementara, pengguna wajib menggantinya saat login."""
        self._set_password(user_id, password, wajib_ganti=True)

    def ganti_password(self, user_id: int, password: str):
        self._set_password(user_id, password, wajib_ganti=False)

    def set_aktif(self, user_id: int, aktif: bool):
        r = self.db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if r is None:
            raise ValueError("Pengguna tidak ditemukan.")
        if not aktif and r["role"] == Role.ADMIN.value:
            lain = self.db.execute(
                "SELECT COUNT(*) FROM users WHERE role=? AND aktif=1 AND id<>?",
                (Role.ADMIN.value, user_id)).fetchone()[0]
            if lain == 0:
                raise ValueError("Tidak bisa menonaktifkan admin terakhir.")
        with self.db:
            self.db.execute("UPDATE users SET aktif=? WHERE id=?", (int(aktif), user_id))
        self._audit("USER_AKTIF" if aktif else "USER_NONAKTIF", r["username"])

    # ---- internal
    def _set_password(self, user_id: int, password: str, wajib_ganti: bool):
        self._cek_password(password)
        salt, h = hash_password(password)
        with self.db:
            self.db.execute("UPDATE users SET salt=?, hash=?, wajib_ganti=? WHERE id=?",
                            (salt, h, int(wajib_ganti), user_id))
        baris = self.db.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
        nama = baris["username"] if baris else str(user_id)
        if wajib_ganti:                      # reset oleh admin
            self._audit("USER_RESET_PASSWORD", nama)
        else:                                # pengguna mengganti passwordnya sendiri
            self._audit("USER_GANTI_PASSWORD", nama, oleh=nama)

    @staticmethod
    def _cek_password(password: str):
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"Password minimal {MIN_PASSWORD} karakter.")

    @staticmethod
    def _ke_user(r) -> User:
        return User(id=r["id"], username=r["username"], nama=r["nama"],
                    role=Role(r["role"]), aktif=bool(r["aktif"]),
                    wajib_ganti=bool(r["wajib_ganti"]))
