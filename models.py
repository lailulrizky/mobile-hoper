"""Model data: status, shift, peran pengguna, hoper, dan aktivitas riwayat."""
import json
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import ClassVar, Dict, List, Optional, Tuple


class Status(str, Enum):
    OK = "OK"            # siap digunakan
    HOLD = "HOLD"        # tunggu informasi
    REJECT = "REJECT"    # dikuras

    @property
    def keterangan(self):
        return {"OK": "Siap digunakan", "HOLD": "Tunggu informasi",
                "REJECT": "Dikuras"}[self.value]

    @property
    def warna(self):            # latar baris tabel
        return {"OK": "#DCFCE7", "HOLD": "#FEF3C7", "REJECT": "#FEE2E2"}[self.value]

    @property
    def warna_teks(self):       # teks status (tebal)
        return {"OK": "#166534", "HOLD": "#92400E", "REJECT": "#991B1B"}[self.value]


class Shift(IntEnum):
    S1 = 1
    S2 = 2
    S3 = 3

    @property
    def label(self):
        return {1: "Shift 1 (07.00-15.00)", 2: "Shift 2 (15.00-23.00)",
                3: "Shift 3 (23.00-07.00)"}[self.value]


class Role(str, Enum):
    OPERATOR = "operator"
    ADMIN = "admin"
    SUPERVISOR = "supervisor"

    @property
    def label(self):
        return {"operator": "Operator", "admin": "Admin",
                "supervisor": "Supervisor"}[self.value]

    @property
    def boleh_ekspor(self) -> bool:
        return self is not Role.OPERATOR


class Kategori(str, Enum):
    """Jenis data master yang dikelola admin; operator hanya memilih darinya."""
    HOPER = "HOPER"
    MESIN = "MESIN"
    JENIS = "JENIS"

    @property
    def label(self):
        return {"HOPER": "Nomor Hoper", "MESIN": "Nomor Mesin",
                "JENIS": "Jenis Material"}[self.value]


@dataclass
class ItemMaster:
    id: int
    kategori: Kategori
    nama: str
    aktif: bool = True
    dipakai: int = 0          # jumlah catatan transaksi yang memakai nama ini


@dataclass
class User:
    id: int
    username: str
    nama: str
    role: Role
    aktif: bool = True
    wajib_ganti: bool = False


@dataclass
class Hoper:
    no_hoper: str
    kode_trace: str
    jenis: str
    berat: float
    waktu_terima: str
    status: Status = Status.HOLD
    aktif: bool = True              # True = masih berisi material
    id: Optional[int] = None
    mesin: Optional[str] = None     # mesin tempat hoper terpasang (None = tidak terpasang)
    pemakaian_id: Optional[int] = None
    shift_terima: Optional[int] = None      # shift saat material diterima (1/2/3)
    shift_pasang: Optional[int] = None      # shift saat dipasang ke mesin (jika terpasang)
    mesin_terakhir: Optional[str] = None    # mesin terakhir yang memakai hoper ini

    @property
    def kondisi(self) -> str:
        """Terpasang = di mesin | Standby = berisi & tidak di mesin | Kosong = selesai."""
        if not self.aktif:
            return "Kosong"
        return "Terpasang" if self.mesin else "Standby"


@dataclass
class RekapShift:
    """Rekap satu shift pada satu tanggal shift: penerimaan, pemakaian hoper, material reject.
    Dihitung dari riwayat aktivitas; disetujui supervisor (angkanya disimpan sebagai foto)."""
    tgl_shift: str
    shift: int
    hoper_diterima: int = 0
    berat_diterima: float = 0.0
    hoper_digunakan: int = 0          # jumlah hoper BERBEDA yang dipasang ke mesin
    pemasangan: int = 0
    pelepasan: int = 0
    reject_catatan: int = 0
    berat_reject: float = 0.0
    pending: int = 0                  # aktivitas shift ini yang belum disetujui
    per_jenis: Dict[str, List[float]] = field(default_factory=dict)   # jenis -> [diterima, reject]
    approval_oleh: Optional[str] = None
    approval_waktu: Optional[str] = None
    berubah: bool = False             # angka berubah sejak rekap disetujui

    KOLOM: ClassVar[List[str]] = [
        "Tgl Shift", "Shift", "Hoper Diterima", "Berat Diterima (kg)", "Hoper Digunakan",
        "Pemasangan", "Pelepasan", "Catatan Reject", "Berat Reject (kg)",
        "Aktivitas Pending", "Status Rekap"]
    IDX_ANGKA: ClassVar[Tuple[int, ...]] = (2, 3, 4, 5, 6, 7, 8, 9)
    KOLOM_JENIS: ClassVar[List[str]] = ["Tgl Shift", "Shift", "Jenis Material",
                                        "Diterima (kg)", "Reject (kg)"]

    def snapshot(self) -> str:
        """Foto angka rekap; dibandingkan untuk mendeteksi perubahan setelah disetujui."""
        return json.dumps({
            "hd": self.hoper_diterima, "bd": round(self.berat_diterima, 2),
            "hg": self.hoper_digunakan, "ps": self.pemasangan, "pl": self.pelepasan,
            "rc": self.reject_catatan, "br": round(self.berat_reject, 2),
            "pj": {j: [round(v[0], 2), round(v[1], 2)] for j, v in sorted(self.per_jenis.items())},
        }, sort_keys=True)

    @property
    def disetujui(self) -> bool:
        return self.approval_oleh is not None and not self.berubah

    @property
    def status(self) -> str:
        if self.approval_oleh is None:
            return "Belum disetujui"
        if self.berubah:
            return "Berubah sejak disetujui - perlu approval ulang"
        return f"Disetujui {self.approval_oleh} ({(self.approval_waktu or '')[:16]})"

    def baris(self) -> List[str]:
        return [self.tgl_shift, str(self.shift), str(self.hoper_diterima),
                f"{self.berat_diterima:.2f}", str(self.hoper_digunakan), str(self.pemasangan),
                str(self.pelepasan), str(self.reject_catatan), f"{self.berat_reject:.2f}",
                str(self.pending), self.status]

    def baris_jenis(self) -> List[List[str]]:
        return [[self.tgl_shift, str(self.shift), j, f"{v[0]:.2f}", f"{v[1]:.2f}"]
                for j, v in sorted(self.per_jenis.items())]


@dataclass
class Aktivitas:
    """Satu kejadian di riwayat: Penerimaan, Pemasangan ke mesin, atau Pelepasan."""
    aktivitas: str            # TERIMA | PASANG | LEPAS
    ref_id: int               # id hoper (TERIMA) atau id pemakaian (PASANG / LEPAS)
    hoper_id: int
    waktu: str
    shift: Optional[int]
    no_hoper: str
    kode_trace: str
    jenis: str
    berat: Optional[float]    # berat diterima (TERIMA) / sisa saat dilepas (LEPAS)
    mesin: Optional[str]
    operator: Optional[str]
    catatan: Optional[str]
    tgl_shift: str            # tanggal shift (shift 3 setelah 00.00 dihitung hari sebelumnya)
    approval_oleh: Optional[str] = None
    approval_waktu: Optional[str] = None

    LABEL: ClassVar[Dict[str, str]] = {"TERIMA": "Penerimaan", "PASANG": "Pemasangan",
                                       "LEPAS": "Pelepasan",
                                       "REJECT": "Material Reject"}
    KOLOM: ClassVar[List[str]] = ["Waktu", "Tgl Shift", "Shift", "Aktivitas", "No. Hoper",
                                  "Kode Trace", "Jenis", "Berat/Sisa (kg)", "Mesin",
                                  "Operator", "Catatan", "Approval"]
    IDX_ANGKA: ClassVar[Tuple[int, ...]] = (7,)

    @property
    def label(self) -> str:
        return self.LABEL[self.aktivitas]

    @property
    def objek(self) -> str:
        return self.jenis if self.aktivitas == "REJECT" else f"Hoper {self.no_hoper}"

    @property
    def judul_riwayat(self) -> str:
        if self.aktivitas == "REJECT":
            return f"Riwayat Material Reject - {self.jenis} {self.berat or 0:.2f} kg"
        return f"Riwayat Hoper {self.no_hoper} - Trace {self.kode_trace}"

    @property
    def disetujui(self) -> bool:
        return self.approval_oleh is not None

    @property
    def status_approval(self) -> str:
        if not self.disetujui:
            return "Pending"
        return f"Disetujui {self.approval_oleh} ({(self.approval_waktu or '')[:16]})"

    def baris(self) -> List[str]:
        return [self.waktu, self.tgl_shift, str(self.shift or "-"), self.label,
                self.no_hoper, self.kode_trace, self.jenis,
                "" if self.berat is None else f"{self.berat:.2f}",
                self.mesin or "", self.operator or "", self.catatan or "",
                self.status_approval]
