"""Akses data (SQLite). Semua query & aturan bisnis ada di sini, UI tidak menyentuh SQL."""
import re
import sqlite3
from datetime import datetime
from typing import List, Optional

from versi import VERSI_SKEMA
from models import Aktivitas, Hoper, ItemMaster, Kategori, RekapShift, Role, Status, User

SKEMA = """
CREATE TABLE IF NOT EXISTS hoper (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    no_hoper     TEXT NOT NULL,
    kode_trace   TEXT NOT NULL,
    jenis        TEXT NOT NULL,
    berat        REAL NOT NULL,          -- berat saat ini (berubah saat dilepas dgn sisa)
    berat_awal   REAL,                   -- berat saat diterima
    waktu_terima TEXT NOT NULL,
    status       TEXT NOT NULL,
    aktif        INTEGER NOT NULL DEFAULT 1,
    shift_terima INTEGER
    operator     TEXT
);
CREATE TABLE IF NOT EXISTS riwayat (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    hoper_id  INTEGER NOT NULL REFERENCES hoper(id),
    waktu     TEXT NOT NULL,
    status    TEXT NOT NULL,
    catatan   TEXT,
    oleh      TEXT
);
CREATE TABLE IF NOT EXISTS pemakaian (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    hoper_id     INTEGER NOT NULL REFERENCES hoper(id),
    mesin        TEXT NOT NULL,
    operator     TEXT,
    waktu_pasang TEXT NOT NULL,
    shift_pasang INTEGER,
    waktu_lepas  TEXT,            -- NULL = masih terpasang
    shift_lepas  INTEGER,
    sisa_berat   REAL,
    catatan      TEXT
);
CREATE TABLE IF NOT EXISTS approval (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    aktivitas  TEXT NOT NULL,         -- TERIMA | PASANG | LEPAS
    ref_id     INTEGER NOT NULL,      -- id hoper (TERIMA) / id pemakaian (PASANG, LEPAS)
    hoper_id   INTEGER NOT NULL,
    oleh       TEXT NOT NULL,
    waktu      TEXT NOT NULL,
    UNIQUE (aktivitas, ref_id)
);
CREATE TABLE IF NOT EXISTS master (       -- data master: pilihan untuk operator
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    kategori TEXT NOT NULL,               -- HOPER | MESIN | JENIS
    nama     TEXT NOT NULL COLLATE NOCASE,
    aktif    INTEGER NOT NULL DEFAULT 1,
    UNIQUE (kategori, nama)
);
CREATE TABLE IF NOT EXISTS reject (       -- material reject (tidak layak pakai)
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    waktu    TEXT NOT NULL,
    shift    INTEGER NOT NULL,
    operator TEXT NOT NULL,
    berat    REAL NOT NULL CHECK (berat > 0),
    jenis    TEXT NOT NULL,
    catatan  TEXT,
    oleh     TEXT                         -- akun yang menginput
);
CREATE TABLE IF NOT EXISTS reject_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    reject_id INTEGER NOT NULL REFERENCES reject(id),
    waktu     TEXT NOT NULL,
    status    TEXT NOT NULL,
    catatan   TEXT,
    oleh      TEXT
);
CREATE TABLE IF NOT EXISTS rekap_approval (   -- persetujuan rekap per shift
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    tgl_shift TEXT NOT NULL,
    shift     INTEGER NOT NULL,
    ringkasan TEXT NOT NULL,                  -- foto angka rekap saat disetujui (JSON)
    oleh      TEXT NOT NULL,
    waktu     TEXT NOT NULL,
    UNIQUE (tgl_shift, shift)
);
CREATE TABLE IF NOT EXISTS audit (            -- jejak perubahan sistem (master, akun, login, backup)
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    waktu  TEXT NOT NULL,
    oleh   TEXT,
    aksi   TEXT NOT NULL,
    objek  TEXT,
    detail TEXT
);
"""

# Kolom yang ditambahkan belakangan: otomatis ditambahkan ke database lama.
MIGRASI = [("hoper", "shift_terima", "INTEGER"),
           ("hoper", "berat_awal", "REAL"),
           ("hoper", "operator", "TEXT"),     # <--- TAMBAHKAN INI
           ("pemakaian", "shift_pasang", "INTEGER"),
           ("pemakaian", "shift_lepas", "INTEGER"),
           ("riwayat", "oleh", "TEXT")]

# Hoper yang sedang terpasang = baris pemakaian dengan waktu_lepas IS NULL
AKTIF_PAKAI = "waktu_lepas IS NULL"

# True  = rekap shift baru bisa disetujui setelah SEMUA aktivitas shift itu disetujui.
# False = rekap boleh disetujui walau masih ada aktivitas pending.
REKAP_WAJIB_AKTIVITAS_DISETUJUI = True

# Gabungan semua kejadian (penerimaan, pemasangan, pelepasan) sebagai satu daftar.
EVENT_SQL = """

SELECT 'TERIMA' AS aktivitas, w.id AS ref_id, w.id AS hoper_id, w.waktu_terima AS waktu,
       w.shift_terima AS shift, w.no_hoper, w.kode_trace, w.jenis,
       w.berat_awal AS berat, NULL AS mesin, w.operator AS operator, NULL AS catatan
FROM hoper w
UNION ALL


SELECT 'PASANG', p.id, p.hoper_id, p.waktu_pasang, p.shift_pasang,
       w.no_hoper, w.kode_trace, w.jenis, NULL, p.mesin, p.operator, p.catatan
FROM pemakaian p JOIN hoper w ON w.id = p.hoper_id
UNION ALL

SELECT 'LEPAS', p.id, p.hoper_id, p.waktu_lepas, p.shift_lepas,
       w.no_hoper, w.kode_trace, w.jenis, p.sisa_berat, p.mesin, p.operator, NULL
FROM pemakaian p JOIN hoper w ON w.id = p.hoper_id WHERE p.waktu_lepas IS NOT NULL
UNION ALL

SELECT 'REJECT', r.id, 0, r.waktu, r.shift, '-', '-', r.jenis, r.berat, NULL,
       r.operator, r.catatan
FROM reject r
"""

# Tanggal shift: shift 3 (23.00-07.00) yang dicatat 00.00-06.59 dihitung ke hari sebelumnya.
TGL_SHIFT = ("CASE WHEN e.shift=3 AND substr(e.waktu,12,2)<'07' "
             "THEN date(substr(e.waktu,1,10),'-1 day') ELSE substr(e.waktu,1,10) END")


def _sekarang() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _alami(teks: str):
    """Kunci urut alami: H-2 tampil sebelum H-10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", teks)]


def _wajib_shift(shift, konteks: str):
    if shift not in (1, 2, 3):
        raise ValueError(f"Shift {konteks} wajib dipilih.")


def _sama(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 1e-9
    return (a or "") == (b or "")


class Repository:
    def __init__(self, path: str = "penerimaan.db"):
        self.pengguna: Optional[User] = None      # diisi saat login
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self._migrasi_nama()            # harus sebelum SKEMA agar tidak membuat tabel kembar
        self.db.executescript(SKEMA)
        self._migrasi()
        self._migrasi_master()
        if self.db.execute("PRAGMA user_version").fetchone()[0] < VERSI_SKEMA:
            self.db.execute(f"PRAGMA user_version = {VERSI_SKEMA}")
            self.db.commit()

    def _kolom(self, tabel: str) -> List[str]:
        return [r["name"] for r in self.db.execute(f"PRAGMA table_info({tabel})")]

    def _migrasi_nama(self):
        """Database lama memakai istilah 'wadah'. Ganti nama tabel & kolom ke 'hoper'
        (seluruh data tetap). Aman dijalankan berulang, dan memperbaiki migrasi yang
        sebelumnya berhenti di tengah jalan: setiap tabel/kolom diperiksa sendiri-sendiri."""
        ada = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "wadah" in ada:
            if "hoper" in ada and self.db.execute("SELECT COUNT(*) FROM hoper").fetchone()[0] == 0:
                self.db.execute("DROP TABLE hoper")        # tabel kosong buatan skema baru
                ada.discard("hoper")
            if "hoper" not in ada:
                self.db.execute("ALTER TABLE wadah RENAME TO hoper")
                ada.discard("wadah")
                ada.add("hoper")
        for tabel, lama, baru in [("hoper", "no_wadah", "no_hoper"),
                                  ("riwayat", "wadah_id", "hoper_id"),
                                  ("pemakaian", "wadah_id", "hoper_id"),
                                  ("approval", "wadah_id", "hoper_id")]:
            if tabel in ada:
                kolom = self._kolom(tabel)
                if lama in kolom and baru not in kolom:
                    self.db.execute(f"ALTER TABLE {tabel} RENAME COLUMN {lama} TO {baru}")
        self.db.commit()

    def _migrasi_master(self):
        """Sekali saja: isi master data dari nilai yang sudah pernah dipakai di transaksi,
        agar data lama tetap konsisten dengan pilihan operator."""
        if self.db.execute("PRAGMA user_version").fetchone()[0] >= 1:
            return
        with self.db:
            for kat, sql in [("HOPER", "SELECT DISTINCT TRIM(no_hoper) FROM hoper"),
                             ("JENIS", "SELECT DISTINCT TRIM(jenis) FROM hoper"),
                             ("MESIN", "SELECT DISTINCT TRIM(mesin) FROM pemakaian")]:
                for baris in self.db.execute(sql).fetchall():
                    if baris[0]:
                        self.db.execute("INSERT OR IGNORE INTO master (kategori,nama) "
                                        "VALUES (?,?)", (kat, baris[0]))
        self.db.execute("PRAGMA user_version = 1")
        self.db.commit()

    def _migrasi(self):
        for tabel, kolom, tipe in MIGRASI:
            ada = [r["name"] for r in self.db.execute(f"PRAGMA table_info({tabel})")]
            if kolom not in ada:
                self.db.execute(f"ALTER TABLE {tabel} ADD COLUMN {kolom} {tipe}")
        self.db.execute("UPDATE hoper SET berat_awal=berat WHERE berat_awal IS NULL")
        self.db.commit()

    def tambah(self, w: Hoper, catatan: str = "") -> int:
        _wajib_shift(w.shift_terima, "penerimaan")
        w.no_hoper = self._cek_master(Kategori.HOPER, w.no_hoper)
        w.jenis = self._cek_master(Kategori.JENIS, w.jenis)
        ada = self.db.execute(
            "SELECT 1 FROM hoper WHERE no_hoper=? AND aktif=1", (w.no_hoper,)).fetchone()
        if ada:
            raise ValueError(f"Hoper {w.no_hoper} masih berisi material.\n"
                             "Kosongkan dulu sebelum diisi lagi.")
        nama_operator = (self.pengguna.nama or self.pengguna.username) if self.pengguna else "sistem"
        with self.db:
            cur = self.db.execute(
                "INSERT INTO hoper (no_hoper,kode_trace,jenis,berat,berat_awal,waktu_terima,"
                "status,shift_terima,operator) VALUES (?,?,?,?,?,?,?,?,?)",
                (w.no_hoper, w.kode_trace, w.jenis, w.berat, w.berat, w.waktu_terima,
                 w.status.value, w.shift_terima, nama_operator))
            self._log(cur.lastrowid, w.status.value,
                      f"[Shift {w.shift_terima}] {catatan or 'Diterima'}")
        return cur.lastrowid

    # ================================================== Pengguna aktif & izin
    @property
    def oleh(self) -> str:
        return self.pengguna.username if self.pengguna else "sistem"

    def boleh_ekspor(self) -> bool:
        return self.pengguna is not None and self.pengguna.role.boleh_ekspor

    def _wajib(self, *role: Role):
        if self.pengguna is None or self.pengguna.role not in role:
            raise PermissionError("Akun Anda tidak memiliki izin untuk tindakan ini.")

    # ================================================== Penerimaan / status
    def tambah(self, w: Hoper, catatan: str = "") -> int:
        _wajib_shift(w.shift_terima, "penerimaan")
        w.no_hoper = self._cek_master(Kategori.HOPER, w.no_hoper)
        w.jenis = self._cek_master(Kategori.JENIS, w.jenis)
        ada = self.db.execute(
            "SELECT 1 FROM hoper WHERE no_hoper=? AND aktif=1", (w.no_hoper,)).fetchone()
        if ada:
            raise ValueError(f"Hoper {w.no_hoper} masih berisi material.\n"
                             "Kosongkan dulu sebelum diisi lagi.")
        with self.db:
            cur = self.db.execute(
                "INSERT INTO hoper (no_hoper,kode_trace,jenis,berat,berat_awal,waktu_terima,"
                "status,shift_terima) VALUES (?,?,?,?,?,?,?,?)",
                (w.no_hoper, w.kode_trace, w.jenis, w.berat, w.berat, w.waktu_terima,
                 w.status.value, w.shift_terima))
            self._log(cur.lastrowid, w.status.value,
                      f"[Shift {w.shift_terima}] {catatan or 'Diterima'}")
        return cur.lastrowid

    def ubah_status(self, hoper_id: int, status: Status, catatan: str = ""):
        with self.db:
            self.db.execute("UPDATE hoper SET status=? WHERE id=?", (status.value, hoper_id))
            self._log(hoper_id, status.value, catatan)

    def kosongkan(self, hoper_id: int, catatan: str = ""):
        if self._sedang_terpasang(hoper_id):
            raise ValueError("Hoper masih terpasang di mesin.\nLepas dulu dari mesin.")
        with self.db:
            self.db.execute("UPDATE hoper SET aktif=0 WHERE id=?", (hoper_id,))
            self._log(hoper_id, "KOSONG", catatan or "Hoper dikosongkan")

    # ================================================== Pemakaian (mesin)
    def pasang(self, hoper_id: int, mesin: str, operator: str, waktu: str,
               shift: Optional[int], catatan: str = ""):
        _wajib_shift(shift, "pemakaian")
        mesin = self._cek_master(Kategori.MESIN, mesin)
        w = self.db.execute("SELECT * FROM hoper WHERE id=?", (hoper_id,)).fetchone()
        if not w or not w["aktif"]:
            raise ValueError("Hoper ini sudah kosong.")
        if w["status"] != Status.OK.value:
            raise ValueError(f"Hoper berstatus {w['status']}.\n"
                             "Hanya hoper berstatus OK yang boleh dipasang ke mesin.")
        if self._sedang_terpasang(hoper_id):
            raise ValueError("Hoper ini sudah terpasang di mesin.")
        # Aturan: satu mesin = satu hoper. Hapus blok ini jika mesin boleh >1 hoper.
        sibuk = self.db.execute(
            f"SELECT w.no_hoper FROM pemakaian p JOIN hoper w ON w.id=p.hoper_id "
            f"WHERE p.mesin=? COLLATE NOCASE AND p.{AKTIF_PAKAI}", (mesin,)).fetchone()
        if sibuk:
            raise ValueError(f"Mesin {mesin} masih terpasang hoper {sibuk[0]}.\nLepas dulu.")
        with self.db:
            self.db.execute(
                "INSERT INTO pemakaian (hoper_id,mesin,operator,waktu_pasang,shift_pasang,"
                "catatan) VALUES (?,?,?,?,?,?)",
                (hoper_id, mesin, operator, waktu, shift, catatan))
            info = f"[Shift {shift}] Dipasang di mesin {mesin}" + \
                   (f" oleh {operator}" if operator else "")
            self._log(hoper_id, "PASANG", info + (f" - {catatan}" if catatan else ""))

    def lepas(self, pemakaian_id: int, waktu: str, shift: Optional[int], sisa: float,
              kosongkan: bool = False, catatan: str = ""):
        """Lepas hoper dari mesin.
        kosongkan=False -> hoper STANDBY (masih ada isi, bisa dipasang ke mesin lain).
        kosongkan=True  -> hoper kosong (material habis / dikuras)."""
        _wajib_shift(shift, "pelepasan")
        if not kosongkan and sisa <= 0:
            raise ValueError("Hoper standby harus masih punya sisa (> 0 kg).\n"
                             "Pilih 'Kosong' jika material sudah habis.")
        p = self.db.execute(
            f"SELECT p.*, w.berat AS berat_hoper FROM pemakaian p "
            f"JOIN hoper w ON w.id=p.hoper_id WHERE p.id=? AND p.{AKTIF_PAKAI}",
            (pemakaian_id,)).fetchone()
        if not p:
            raise ValueError("Hoper ini tidak sedang terpasang di mesin.")
        if sisa > p["berat_hoper"] + 1e-9:
            raise ValueError("Sisa tidak boleh lebih besar dari berat hoper saat ini.")
        sisa = 0.0 if kosongkan else sisa
        with self.db:
            self.db.execute(
                "UPDATE pemakaian SET waktu_lepas=?, shift_lepas=?, sisa_berat=? WHERE id=?",
                (waktu, shift, sisa, pemakaian_id))
            self.db.execute("UPDATE hoper SET berat=?, aktif=? WHERE id=?",
                            (sisa, 0 if kosongkan else 1, p["hoper_id"]))
            self._log(p["hoper_id"], "LEPAS",
                      f"[Shift {shift}] Dilepas dari mesin {p['mesin']}, sisa {sisa:.2f} kg "
                      f"(sebelumnya {p['berat_hoper']:.2f} kg), "
                      + ("hoper dikosongkan" if kosongkan else "hoper standby")
                      + (f" - {catatan}" if catatan else ""))
            if kosongkan:
                self._log(p["hoper_id"], "KOSONG", "Hoper dikosongkan")

    def _sedang_terpasang(self, hoper_id: int) -> bool:
        return self.db.execute(
            f"SELECT 1 FROM pemakaian WHERE hoper_id=? AND {AKTIF_PAKAI}",
            (hoper_id,)).fetchone() is not None

    def _log(self, hoper_id: int, status: str, catatan: str):
        self.db.execute(
            "INSERT INTO riwayat (hoper_id,waktu,status,catatan,oleh) VALUES (?,?,?,?,?)",
            (hoper_id, _sekarang(), status, catatan, self.oleh))

    # ================================================== Material reject
    def tambah_reject(self, waktu: str, shift: Optional[int], operator: str, berat: float,
                      jenis: str, catatan: str = "") -> int:
        """Catat material yang ditolak (tidak layak pakai). Jenis harus dari Master Data."""
        _wajib_shift(shift, "reject")
        if berat <= 0:
            raise ValueError("Berat reject harus lebih dari 0 kg.")
        jenis = self._cek_master(Kategori.JENIS, jenis)
        operator = operator.strip() or (self.pengguna.nama if self.pengguna else "")
        if not operator:
            raise ValueError("Operator wajib diisi.")
        catatan = catatan.strip()
        with self.db:
            cur = self.db.execute(
                "INSERT INTO reject (waktu,shift,operator,berat,jenis,catatan,oleh) "
                "VALUES (?,?,?,?,?,?,?)", (waktu, shift, operator, berat, jenis, catatan, self.oleh))
            self._log_reject(cur.lastrowid, "REJECT",
                             f"[Shift {shift}] Dicatat: {berat:.2f} kg {jenis}"
                             + (f" - {catatan}" if catatan else ""))
        return cur.lastrowid

    def koreksi_reject(self, reject_id: int, waktu: str, shift: Optional[int], operator: str,
                       berat: float, jenis: str, catatan: str, alasan: str):
        self._wajib(Role.ADMIN)
        _wajib_shift(shift, "reject")
        if berat <= 0:
            raise ValueError("Berat reject harus lebih dari 0 kg.")
        operator = operator.strip()
        if not operator:
            raise ValueError("Operator wajib diisi.")
        lama = self.db.execute("SELECT * FROM reject WHERE id=?", (reject_id,)).fetchone()
        if lama is None:
            raise ValueError("Data tidak ditemukan.")
        if jenis.lower() != lama["jenis"].lower():
            jenis = self._cek_master(Kategori.JENIS, jenis)
        self._koreksi("reject", reject_id, 0, "REJECT",
                      {"waktu": waktu, "shift": shift, "operator": operator, "berat": berat,
                       "jenis": jenis, "catatan": catatan.strip()}, alasan)

    def _audit(self, aksi: str, objek: str = "", detail: str = "", oleh: Optional[str] = None):
        """Catat ke tabel audit TANPA commit (dipakai di dalam transaksi yang sedang berjalan)."""
        self.db.execute("INSERT INTO audit (waktu,oleh,aksi,objek,detail) VALUES (?,?,?,?,?)",
                        (_sekarang(), oleh or self.oleh, aksi, objek, detail))

    def catat_audit(self, aksi: str, objek: str = "", detail: str = "",
                    oleh: Optional[str] = None):
        with self.db:
            self._audit(aksi, objek, detail, oleh)

    def daftar_audit(self, cari: str = "", limit: int = 1000):
        sql, par = "SELECT waktu, COALESCE(oleh,''), aksi, COALESCE(objek,''), COALESCE(detail,'') FROM audit", []
        if cari:
            sql += " WHERE oleh LIKE ? OR aksi LIKE ? OR objek LIKE ? OR detail LIKE ?"
            par = [f"%{cari}%"] * 4
        sql += " ORDER BY id DESC LIMIT ?"
        return self.db.execute(sql, par + [limit]).fetchall()

    def _log_reject(self, reject_id: int, status: str, catatan: str):
        self.db.execute(
            "INSERT INTO reject_log (reject_id,waktu,status,catatan,oleh) VALUES (?,?,?,?,?)",
            (reject_id, _sekarang(), status, catatan, self.oleh))

    # ================================================== Approval (supervisor)
    def setujui(self, daftar: List[Aktivitas]) -> int:
        """Setujui aktivitas yang masih pending. Mengembalikan jumlah yang disetujui."""
        self._wajib(Role.SUPERVISOR)
        n = 0
        with self.db:
            for a in daftar:
                if a.disetujui:
                    continue
                cur = self.db.execute(
                    "INSERT OR IGNORE INTO approval (aktivitas,ref_id,hoper_id,oleh,waktu) "
                    "VALUES (?,?,?,?,?)",
                    (a.aktivitas, a.ref_id, a.hoper_id, self.oleh, _sekarang()))
                if cur.rowcount:
                    n += 1
                    pesan = f"{a.label} shift {a.shift} ({a.tgl_shift}) disetujui"
                    if a.aktivitas == "REJECT":
                        self._log_reject(a.ref_id, "APPROVE", pesan)
                    else:
                        self._log(a.hoper_id, "APPROVE", pesan)
        return n

    # ================================================== Rekap per shift
    def rekap_shift(self, dari: Optional[str] = None, sampai: Optional[str] = None,
                    shift: Optional[int] = None) -> List[RekapShift]:
        """Rekap per (tanggal shift, shift): hoper & berat diterima, hoper digunakan,
        material reject, rincian per jenis, serta status approval rekap."""
        grup, pakai = {}, {}
        for a in self.aktivitas(dari=dari, sampai=sampai, shift=shift):
            if not a.shift:
                continue                      # data lama tanpa shift tidak bisa direkap
            kunci = (a.tgl_shift, a.shift)
            rk = grup.setdefault(kunci, RekapShift(a.tgl_shift, a.shift))
            berat = a.berat or 0.0
            if a.aktivitas == "TERIMA":
                rk.hoper_diterima += 1
                rk.berat_diterima += berat
                rk.per_jenis.setdefault(a.jenis, [0.0, 0.0])[0] += berat
            elif a.aktivitas == "REJECT":
                rk.reject_catatan += 1
                rk.berat_reject += berat
                rk.per_jenis.setdefault(a.jenis, [0.0, 0.0])[1] += berat
            elif a.aktivitas == "PASANG":
                rk.pemasangan += 1
                pakai.setdefault(kunci, set()).add(a.hoper_id)
            elif a.aktivitas == "LEPAS":
                rk.pelepasan += 1
            if not a.disetujui:
                rk.pending += 1
        tersimpan = {(r["tgl_shift"], r["shift"]): r
                     for r in self.db.execute("SELECT * FROM rekap_approval")}
        hasil = []
        for kunci, rk in grup.items():
            rk.hoper_digunakan = len(pakai.get(kunci, ()))
            rk.berat_diterima = round(rk.berat_diterima, 2)
            rk.berat_reject = round(rk.berat_reject, 2)
            rk.per_jenis = {j: [round(v[0], 2), round(v[1], 2)]
                            for j, v in rk.per_jenis.items()}
            if kunci in tersimpan:
                rk.approval_oleh = tersimpan[kunci]["oleh"]
                rk.approval_waktu = tersimpan[kunci]["waktu"]
                rk.berubah = tersimpan[kunci]["ringkasan"] != rk.snapshot()
            hasil.append(rk)
        return sorted(hasil, key=lambda r: (r.tgl_shift, r.shift), reverse=True)

    def setujui_rekap(self, tgl_shift: str, shift: int) -> RekapShift:
        """Supervisor menyetujui rekap satu shift. Angka rekap disimpan sebagai foto; bila data
        shift itu berubah kemudian (mis. koreksi admin), status menjadi 'perlu approval ulang'."""
        self._wajib(Role.SUPERVISOR)
        rk = next(iter(self.rekap_shift(tgl_shift, tgl_shift, shift)), None)
        if rk is None:
            raise ValueError("Tidak ada aktivitas pada shift ini.")
        if REKAP_WAJIB_AKTIVITAS_DISETUJUI and rk.pending:
            raise ValueError(f"Masih ada {rk.pending} aktivitas yang belum disetujui pada "
                             "shift ini.\nSetujui aktivitasnya dulu, baru rekap.")
        if rk.disetujui:
            raise ValueError("Rekap shift ini sudah disetujui.")
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO rekap_approval (tgl_shift,shift,ringkasan,oleh,waktu) "
                "VALUES (?,?,?,?,?)", (tgl_shift, shift, rk.snapshot(), self.oleh, _sekarang()))
            self._audit("APPROVE_REKAP", f"{tgl_shift} shift {shift}")
        return rk

    # ================================================== Koreksi (admin)
    def koreksi_terima(self, hoper_id: int, no_hoper: str, kode_trace: str, jenis: str,
                       berat_awal: float, waktu: str, shift: Optional[int], alasan: str):
        self._wajib(Role.ADMIN)
        _wajib_shift(shift, "penerimaan")
        no_hoper, kode_trace, jenis = no_hoper.strip(), kode_trace.strip(), jenis.strip()
        if not (no_hoper and kode_trace and jenis) or berat_awal <= 0:
            raise ValueError("No. hoper, kode trace, jenis, dan berat (> 0) wajib diisi.")
        lama = self.db.execute("SELECT * FROM hoper WHERE id=?", (hoper_id,)).fetchone()
        if lama is None:
            raise ValueError("Data tidak ditemukan.")
        if no_hoper.lower() != lama["no_hoper"].lower():
            no_hoper = self._cek_master(Kategori.HOPER, no_hoper)
        if jenis.lower() != lama["jenis"].lower():
            jenis = self._cek_master(Kategori.JENIS, jenis)
        if lama["aktif"] and no_hoper != lama["no_hoper"] and self.db.execute(
                "SELECT 1 FROM hoper WHERE no_hoper=? AND aktif=1 AND id<>?",
                (no_hoper, hoper_id)).fetchone():
            raise ValueError(f"Hoper {no_hoper} sudah dipakai hoper lain yang masih berisi.")
        # Berat diterima dikoreksi -> berat saat ini ikut bergeser dengan selisih yang sama.
        delta = round(berat_awal - (lama["berat_awal"] or lama["berat"]), 2)
        sql_lain = []
        if delta and lama["aktif"]:
            sql_lain.append(("UPDATE hoper SET berat=ROUND(MAX(0, berat+?),2) WHERE id=?",
                             (delta, hoper_id)))
        self._koreksi("hoper", hoper_id, hoper_id, "TERIMA",
                      {"no_hoper": no_hoper, "kode_trace": kode_trace, "jenis": jenis,
                       "berat_awal": berat_awal, "waktu_terima": waktu,
                       "shift_terima": shift}, alasan, sql_lain)

    def koreksi_pasang(self, pemakaian_id: int, mesin: str, operator: str, waktu: str,
                       shift: Optional[int], catatan: str, alasan: str):
        self._wajib(Role.ADMIN)
        _wajib_shift(shift, "pemakaian")
        mesin = mesin.strip()
        if not mesin:
            raise ValueError("Mesin wajib diisi.")
        p = self.db.execute("SELECT * FROM pemakaian WHERE id=?", (pemakaian_id,)).fetchone()
        if p is None:
            raise ValueError("Data tidak ditemukan.")
        if mesin.lower() != p["mesin"].lower():
            mesin = self._cek_master(Kategori.MESIN, mesin)
        if p["waktu_lepas"] is None and mesin.lower() != p["mesin"].lower() and \
                self.db.execute(
                    f"SELECT 1 FROM pemakaian WHERE mesin=? COLLATE NOCASE "
                    f"AND {AKTIF_PAKAI} AND id<>?", (mesin, pemakaian_id)).fetchone():
            raise ValueError(f"Mesin {mesin} sedang terpasang hoper lain.")
        self._koreksi("pemakaian", pemakaian_id, p["hoper_id"], "PASANG",
                      {"mesin": mesin, "operator": operator.strip(), "waktu_pasang": waktu,
                       "shift_pasang": shift, "catatan": catatan.strip()}, alasan)

    def koreksi_lepas(self, pemakaian_id: int, waktu: str, shift: Optional[int],
                      sisa: float, alasan: str):
        self._wajib(Role.ADMIN)
        _wajib_shift(shift, "pelepasan")
        if sisa < 0:
            raise ValueError("Sisa tidak boleh negatif.")
        p = self.db.execute("SELECT * FROM pemakaian WHERE id=? AND waktu_lepas IS NOT NULL",
                            (pemakaian_id,)).fetchone()
        if p is None:
            raise ValueError("Data pelepasan tidak ditemukan.")
        aktif = self.db.execute("SELECT aktif FROM hoper WHERE id=?",
                                (p["hoper_id"],)).fetchone()["aktif"]
        terakhir = self.db.execute("SELECT MAX(id) FROM pemakaian WHERE hoper_id=?",
                                   (p["hoper_id"],)).fetchone()[0]
        sql_lain = []
        if aktif and terakhir == pemakaian_id:       # hoper standby dari pelepasan ini
            if sisa <= 0:
                raise ValueError("Hoper masih standby, sisa harus > 0.\n"
                                 "Kosongkan hopernya dulu bila material sudah habis.")
            sql_lain.append(("UPDATE hoper SET berat=? WHERE id=?", (sisa, p["hoper_id"])))
        self._koreksi("pemakaian", pemakaian_id, p["hoper_id"], "LEPAS",
                      {"waktu_lepas": waktu, "shift_lepas": shift, "sisa_berat": sisa},
                      alasan, sql_lain)

    def _koreksi(self, tabel: str, row_id: int, hoper_id: int, aktivitas: str,
                 baru: dict, alasan: str, sql_lain=()):
        """Terapkan koreksi: hanya kolom yang berubah, approval direset, dicatat di riwayat.
        (nama tabel/kolom berasal dari kode di atas, bukan dari input pengguna)"""
        if not alasan.strip():
            raise ValueError("Alasan koreksi wajib diisi.")
        lama = self.db.execute(f"SELECT * FROM {tabel} WHERE id=?", (row_id,)).fetchone()
        beda = {k: v for k, v in baru.items() if not _sama(lama[k], v)}
        if not beda:
            raise ValueError("Tidak ada data yang diubah.")
        sets = ", ".join(f"{k}=?" for k in beda)
        rincian = "; ".join(
            f"{k}: {'' if lama[k] is None else lama[k]} -> {v}" for k, v in beda.items())
        with self.db:
            self.db.execute(f"UPDATE {tabel} SET {sets} WHERE id=?", [*beda.values(), row_id])
            for sql, par in sql_lain:
                self.db.execute(sql, par)
            self.db.execute("DELETE FROM approval WHERE aktivitas=? AND ref_id=?",
                            (aktivitas, row_id))
            pesan = f"[{aktivitas}] {alasan.strip()} | {rincian}"
            if aktivitas == "REJECT":
                self._log_reject(row_id, "KOREKSI", pesan)
            else:
                self._log(hoper_id, "KOREKSI", pesan)

    # ================================================== Master data (admin)
    _PAKAI_SQL = {
        Kategori.HOPER: "SELECT COUNT(*) FROM hoper WHERE no_hoper=? COLLATE NOCASE",
        Kategori.MESIN: "SELECT COUNT(*) FROM pemakaian WHERE mesin=? COLLATE NOCASE",
        Kategori.JENIS: ("SELECT (SELECT COUNT(*) FROM hoper WHERE jenis=?1 COLLATE NOCASE) + "
                         "(SELECT COUNT(*) FROM reject WHERE jenis=?1 COLLATE NOCASE)"),
    }

    def master_daftar(self, kategori: Kategori) -> List[ItemMaster]:
        rows = self.db.execute("SELECT * FROM master WHERE kategori=?",
                               (kategori.value,)).fetchall()
        hasil = [ItemMaster(r["id"], kategori, r["nama"], bool(r["aktif"]),
                            self.db.execute(self._PAKAI_SQL[kategori],
                                            (r["nama"],)).fetchone()[0]) for r in rows]
        return sorted(hasil, key=lambda m: _alami(m.nama))

    def master_nama(self, kategori: Kategori, aktif_saja: bool = True) -> List[str]:
        sql = "SELECT nama FROM master WHERE kategori=?" + (" AND aktif=1" if aktif_saja else "")
        return sorted((r[0] for r in self.db.execute(sql, (kategori.value,))), key=_alami)

    def master_tambah(self, kategori: Kategori, daftar: List[str]):
        """Tambah satu/banyak nama. Mengembalikan (jumlah ditambah, daftar yang dilewati
        karena sudah ada). Semua-atau-tidak-sama-sekali bila ada nama yang tidak valid."""
        self._wajib(Role.ADMIN)
        if len(daftar) > 500:
            raise ValueError("Maksimal 500 nama sekali tambah.")
        ditambah, lewat, baru = 0, [], []
        with self.db:
            for nama in daftar:
                nama = " ".join(nama.split())
                if not nama:
                    continue
                if len(nama) > 40:
                    raise ValueError(f"Nama terlalu panjang (maks. 40 karakter): {nama[:24]}...")
                cur = self.db.execute("INSERT OR IGNORE INTO master (kategori,nama) VALUES (?,?)",
                                      (kategori.value, nama))
                if cur.rowcount:
                    ditambah += 1
                    baru.append(nama)
                else:
                    lewat.append(nama)
            if baru:
                self._audit("MASTER_TAMBAH", kategori.label,
                            f"{len(baru)} nama: " + ", ".join(baru[:15])
                            + (" ..." if len(baru) > 15 else ""))
        return ditambah, lewat

    def master_set_aktif(self, item_id: int, aktif: bool):
        self._wajib(Role.ADMIN)
        r = self.db.execute("SELECT kategori, nama FROM master WHERE id=?", (item_id,)).fetchone()
        with self.db:
            self.db.execute("UPDATE master SET aktif=? WHERE id=?", (int(aktif), item_id))
            if r:
                self._audit("MASTER_AKTIF" if aktif else "MASTER_NONAKTIF",
                            Kategori(r["kategori"]).label, r["nama"])

    def master_hapus(self, item_id: int):
        self._wajib(Role.ADMIN)
        r = self.db.execute("SELECT * FROM master WHERE id=?", (item_id,)).fetchone()
        if r is None:
            raise ValueError("Data tidak ditemukan.")
        n = self.db.execute(self._PAKAI_SQL[Kategori(r["kategori"])], (r["nama"],)).fetchone()[0]
        if n:
            raise ValueError(f"'{r['nama']}' sudah dipakai di {n} catatan sehingga tidak bisa "
                             "dihapus.\nNonaktifkan saja agar tidak muncul lagi di pilihan operator.")
        with self.db:
            self.db.execute("DELETE FROM master WHERE id=?", (item_id,))
            self._audit("MASTER_HAPUS", Kategori(r["kategori"]).label, r["nama"])

    def _cek_master(self, kategori: Kategori, nilai: str) -> str:
        """Pastikan nilai terdaftar di master & aktif. Mengembalikan penulisan resminya."""
        r = self.db.execute(
            "SELECT nama, aktif FROM master WHERE kategori=? AND nama=? COLLATE NOCASE",
            (kategori.value, (nilai or "").strip())).fetchone()
        if r is None:
            raise ValueError(f"{kategori.label} '{nilai}' belum terdaftar di Master Data.\n"
                             "Minta admin menambahkannya.")
        if not r["aktif"]:
            raise ValueError(f"{kategori.label} '{r['nama']}' sedang nonaktif.")
        return r["nama"]

    def daftar_hoper_tersedia(self) -> List[str]:
        """Nomor hoper aktif yang saat ini TIDAK berisi material (boleh menerima material)."""
        baris = self.db.execute(
            "SELECT m.nama FROM master m WHERE m.kategori='HOPER' AND m.aktif=1 AND NOT EXISTS "
            "(SELECT 1 FROM hoper h WHERE h.no_hoper=m.nama COLLATE NOCASE AND h.aktif=1)")
        return sorted((r[0] for r in baris), key=_alami)

    def daftar_mesin_kosong(self) -> List[str]:
        """Mesin aktif yang saat ini belum terpasang hoper."""
        baris = self.db.execute(
            f"SELECT m.nama FROM master m WHERE m.kategori='MESIN' AND m.aktif=1 AND NOT EXISTS "
            f"(SELECT 1 FROM pemakaian p WHERE p.mesin=m.nama COLLATE NOCASE AND p.{AKTIF_PAKAI})")
        return sorted((r[0] for r in baris), key=_alami)

    # ================================================== Baca
    def daftar(self, status: Optional[Status] = None, cari: str = "",
               semua: bool = False) -> List[Hoper]:
        sql = ("SELECT w.*, p.mesin, p.id AS pemakaian_id, p.shift_pasang, "
               "(SELECT mesin FROM pemakaian WHERE hoper_id=w.id ORDER BY id DESC LIMIT 1) "
               "AS mesin_terakhir FROM hoper w "
               f"LEFT JOIN pemakaian p ON p.hoper_id=w.id AND p.{AKTIF_PAKAI} WHERE 1=1")
        par = []
        if not semua:
            sql += " AND w.aktif=1"
        if status:
            sql += " AND w.status=?"
            par.append(status.value)
        if cari:
            sql += (" AND (w.no_hoper LIKE ? OR w.kode_trace LIKE ? "
                    "OR w.jenis LIKE ? OR p.mesin LIKE ?)")
            par += [f"%{cari}%"] * 4
        sql += " ORDER BY w.waktu_terima DESC, w.id DESC"
        return [self._ke_hoper(r) for r in self.db.execute(sql, par)]

    def daftar_siap_pakai(self) -> List[Hoper]:
        """Hoper berisi, berstatus OK, dan belum terpasang (baru diterima / standby)."""
        return [w for w in self.daftar(Status.OK) if not w.mesin]

    def aktivitas(self, dari: Optional[str] = None, sampai: Optional[str] = None,
                  shift: Optional[int] = None, tipe: Optional[str] = None,
                  cari: str = "", approval: Optional[str] = None) -> List[Aktivitas]:
        """Riwayat aktivitas dengan filter. dari/sampai = tanggal shift 'YYYY-MM-DD',
        tipe = TERIMA|PASANG|LEPAS, approval = 'pending'|'approved'."""
        sql = ("SELECT * FROM (SELECT e.*, " + TGL_SHIFT + " AS tgl_shift, "
               "a.oleh AS approval_oleh, a.waktu AS approval_waktu "
               "FROM (" + EVENT_SQL + ") e "
               "LEFT JOIN approval a ON a.aktivitas=e.aktivitas AND a.ref_id=e.ref_id "
               "WHERE e.waktu IS NOT NULL) WHERE 1=1")
        par = []
        if dari:
            sql += " AND tgl_shift >= ?"
            par.append(dari)
        if sampai:
            sql += " AND tgl_shift <= ?"
            par.append(sampai)
        if shift:
            sql += " AND shift = ?"
            par.append(shift)
        if tipe:
            sql += " AND aktivitas = ?"
            par.append(tipe)
        if approval == "pending":
            sql += " AND approval_oleh IS NULL"
        elif approval == "approved":
            sql += " AND approval_oleh IS NOT NULL"
        if cari:
            sql += (" AND (no_hoper LIKE ? OR kode_trace LIKE ? OR jenis LIKE ? "
                    "OR mesin LIKE ? OR operator LIKE ?)")
            par += [f"%{cari}%"] * 5
        sql += " ORDER BY waktu DESC, aktivitas, ref_id"
        return [Aktivitas(**dict(r)) for r in self.db.execute(sql, par)]

    def riwayat_aktivitas(self, a: Aktivitas):
        """Riwayat lengkap satu aktivitas: log hoper, atau log material reject."""
        if a.aktivitas == "REJECT":
            return self.db.execute(
                "SELECT waktu, status, COALESCE(oleh,''), catatan FROM reject_log "
                "WHERE reject_id=? ORDER BY id", (a.ref_id,)).fetchall()
        return self.riwayat(a.hoper_id)

    def riwayat(self, hoper_id: int):
        return self.db.execute(
            "SELECT waktu, status, COALESCE(oleh,''), catatan FROM riwayat "
            "WHERE hoper_id=? ORDER BY id", (hoper_id,)).fetchall()

    def daftar_jenis(self, aktif_saja: bool = True) -> List[str]:
        return self.master_nama(Kategori.JENIS, aktif_saja)

    def daftar_mesin(self, aktif_saja: bool = True) -> List[str]:
        return self.master_nama(Kategori.MESIN, aktif_saja)

    def daftar_hoper(self, aktif_saja: bool = True) -> List[str]:
        return self.master_nama(Kategori.HOPER, aktif_saja)

    @staticmethod
    def _ke_hoper(r) -> Hoper:
        return Hoper(id=r["id"], no_hoper=r["no_hoper"], kode_trace=r["kode_trace"],
                     jenis=r["jenis"], berat=r["berat"], waktu_terima=r["waktu_terima"],
                     status=Status(r["status"]), aktif=bool(r["aktif"]),
                     mesin=r["mesin"], pemakaian_id=r["pemakaian_id"],
                     shift_terima=r["shift_terima"], shift_pasang=r["shift_pasang"],
                     mesin_terakhir=r["mesin_terakhir"])
