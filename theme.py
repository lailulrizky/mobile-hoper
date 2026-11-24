"""Tema visual: palet warna + stylesheet global bergaya dashboard industri.
Ubah warna di PALET; seluruh aplikasi mengikuti."""
from PySide6.QtGui import QColor, QFont, QPalette

PALET = {
    "NAVY": "#17365D", "NAVY_GELAP": "#0F2742",
    "BIRU": "#2563EB", "BIRU_GELAP": "#1D4ED8",
    "HIJAU": "#16A34A", "HIJAU_GELAP": "#15803D",
    "KUNING": "#D97706",
    "MERAH": "#DC2626", "MERAH_GELAP": "#B91C1C",
    "LATAR": "#F1F5F9", "KARTU": "#FFFFFF",
    "GARIS": "#E2E8F0", "GARIS_INPUT": "#CBD5E1",
    "TEKS": "#0F172A", "REDUP": "#64748B",
}
NAVY, BIRU, HIJAU, KUNING, MERAH, REDUP = (PALET[k] for k in
                                           ("NAVY", "BIRU", "HIJAU", "KUNING", "MERAH", "REDUP"))

_QSS = """
QMainWindow, QDialog { background: @LATAR@; }

QToolTip { background: @NAVY@; color: white; border: none; padding: 5px 8px; }

/* ---------- kartu & panel ---------- */
QFrame#panel { background: @KARTU@; border: 1px solid @GARIS@; border-radius: 10px; }

QGroupBox {
    background: @KARTU@; border: 1px solid @GARIS@; border-radius: 10px;
    margin-top: 18px; padding: 22px 14px 14px 14px;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left; left: 16px;
    padding: 2px 8px; color: @NAVY@; font-size: 11pt; font-weight: 700;
}
QLabel#judul_kartu { color: @NAVY@; font-size: 11pt; font-weight: 700; }
QLabel#muted { color: @REDUP@; }

/* ---------- bilah atas ---------- */
QFrame#header {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @NAVY_GELAP@, stop:1 @NAVY@);
    border-radius: 10px;
}
QLabel#brand { color: white; font-size: 13pt; font-weight: 700; }
QLabel#jam { color: #CBD5E1; }
QLabel#avatar { background: @BIRU@; color: white; border-radius: 19px; font-weight: 700; }
QLabel#user_nama { color: white; font-weight: 700; }
QLabel#user_peran { color: #93C5FD; font-size: 8pt; font-weight: 600; }

/* ---------- kartu KPI ---------- */
QLabel#kpi_judul { color: @REDUP@; font-size: 8pt; font-weight: 700; }
QLabel#kpi_nilai { font-size: 22pt; font-weight: 700; }
QLabel#kpi_sub { color: #94A3B8; font-size: 8pt; }

/* ---------- input ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit {
    background: white; border: 1px solid @GARIS_INPUT@; border-radius: 6px;
    padding: 5px 8px; min-height: 20px; selection-background-color: @BIRU@;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QDateTimeEdit:focus { border: 1px solid @BIRU@; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QDateEdit:disabled, QDateTimeEdit:disabled { background: @LATAR@; color: #94A3B8; }
QComboBox QLineEdit, QAbstractSpinBox QLineEdit {
    border: none; background: transparent; padding: 0px; min-height: 0px;
}
QComboBox QAbstractItemView {
    background: white; border: 1px solid @GARIS_INPUT@; outline: 0;
    selection-background-color: #DBEAFE; selection-color: @TEKS@;
}
QCheckBox { spacing: 8px; }

/* ---------- tombol ---------- */
QPushButton {
    background: white; color: @NAVY@; border: 1px solid @GARIS_INPUT@; border-radius: 6px;
    padding: 7px 16px; font-weight: 600; min-height: 20px;
}
QPushButton:hover { background: #F8FAFC; border-color: #94A3B8; }
QPushButton:pressed { background: @GARIS@; }
QPushButton:disabled { color: #94A3B8; background: @LATAR@; }
QPushButton:default { background: @BIRU@; color: white; border: 1px solid @BIRU@; }
QPushButton:default:hover { background: @BIRU_GELAP@; }
QPushButton[varian="primer"] { background: @BIRU@; color: white; border: 1px solid @BIRU@; }
QPushButton[varian="primer"]:hover { background: @BIRU_GELAP@; border-color: @BIRU_GELAP@; }
QPushButton[varian="sukses"] { background: @HIJAU@; color: white; border: 1px solid @HIJAU@; }
QPushButton[varian="sukses"]:hover { background: @HIJAU_GELAP@; border-color: @HIJAU_GELAP@; }
QPushButton[varian="bahaya"] { background: @MERAH@; color: white; border: 1px solid @MERAH@; }
QPushButton[varian="bahaya"]:hover { background: @MERAH_GELAP@; border-color: @MERAH_GELAP@; }
QPushButton[varian="header"] {
    background: rgba(255, 255, 255, 26); color: white; border: 1px solid rgba(255, 255, 255, 90);
}
QPushButton[varian="header"]:hover { background: @MERAH@; border-color: @MERAH@; }

/* ---------- tab ---------- */
QTabWidget::pane { border: none; border-top: 1px solid @GARIS@; background: transparent; top: -1px; }
QTabBar::tab {
    background: transparent; color: @REDUP@; padding: 10px 22px; margin-right: 4px;
    border: none; border-bottom: 3px solid transparent; font-weight: 600;
}
QTabBar::tab:selected { color: @BIRU@; border-bottom: 3px solid @BIRU@; }
QTabBar::tab:hover:!selected { color: @NAVY@; }

/* ---------- tabel ---------- */
QTableWidget, QTableView {
    background: white; border: 1px solid @GARIS@; border-radius: 8px;
    gridline-color: @GARIS@; outline: 0;
    selection-background-color: #BFDBFE; selection-color: @TEKS@;
}
QHeaderView { background: @NAVY@; }
QHeaderView::section {
    background: @NAVY@; color: white; padding: 9px 10px; border: none;
    border-right: 1px solid #2B4C7E; font-weight: 600;
}
QTableCornerButton::section { background: @NAVY@; border: none; }

/* ---------- menu & status ---------- */
QMenuBar { background: white; border-bottom: 1px solid @GARIS@; padding: 2px 6px; }
QMenuBar::item { padding: 6px 12px; border-radius: 4px; background: transparent; }
QMenuBar::item:selected { background: @GARIS@; }
QMenu { background: white; border: 1px solid @GARIS@; padding: 4px; }
QMenu::item { padding: 7px 28px 7px 14px; border-radius: 4px; }
QMenu::item:selected { background: #DBEAFE; color: @TEKS@; }
QStatusBar { background: white; border-top: 1px solid @GARIS@; color: @REDUP@; }

/* ---------- scrollbar ---------- */
QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: @GARIS_INPUT@; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #94A3B8; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: @GARIS_INPUT@; border-radius: 5px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #94A3B8; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; }
"""


def buat_stylesheet() -> str:
    s = _QSS
    for k, v in PALET.items():
        s = s.replace(f"@{k}@", v)
    return s


def terapkan_tema(app):
    """Gaya Fusion + palet terang tetap (agar tidak berubah mengikuti mode gelap Windows)."""
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    pal = QPalette()
    P = QPalette.ColorRole
    for peran, warna in [(P.Window, PALET["LATAR"]), (P.WindowText, PALET["TEKS"]),
                         (P.Base, "#FFFFFF"), (P.AlternateBase, PALET["LATAR"]),
                         (P.Text, PALET["TEKS"]), (P.Button, "#FFFFFF"),
                         (P.ButtonText, PALET["NAVY"]), (P.Highlight, PALET["BIRU"]),
                         (P.HighlightedText, "#FFFFFF"), (P.ToolTipBase, PALET["NAVY"]),
                         (P.ToolTipText, "#FFFFFF"), (P.PlaceholderText, "#94A3B8")]:
        pal.setColor(peran, QColor(warna))
    app.setPalette(pal)
    app.setStyleSheet(buat_stylesheet())
