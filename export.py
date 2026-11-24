"""Ekspor tabel ke Excel (.xlsx), PDF, atau CSV. Tidak bergantung pada Qt.
Pustaka: pip install openpyxl reportlab"""
import csv
from pathlib import Path
from xml.sax.saxutils import escape


def ekspor(path, judul, kolom, baris, info="", angka=()):
    fn = {".xlsx": ke_xlsx, ".pdf": ke_pdf, ".csv": ke_csv}.get(Path(path).suffix.lower())
    if fn is None:
        raise ValueError("Format harus .xlsx, .pdf, atau .csv")
    fn(path, judul, kolom, baris, info, angka)


def _angka(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def _aman_csv(v):
    """Cegah 'CSV injection': teks berawalan = + - @ dianggap rumus oleh Excel."""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


def ke_csv(path, judul, kolom, baris, info="", angka=()):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(kolom)
        w.writerows([_aman_csv(x) for x in b] for b in baris)


def ke_xlsx(path, judul, kolom, baris, info="", angka=()):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = judul[:31]
    ws["A1"] = judul
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = info
    ws["A2"].font = Font(italic=True, color="555555")
    for j, k in enumerate(kolom, 1):
        c = ws.cell(row=4, column=j, value=k)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="37474F")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, b in enumerate(baris, 5):
        for j, v in enumerate(b, 1):
            v = _angka(v) if (j - 1) in angka else ("" if v is None else str(v))
            c = ws.cell(row=i, column=j, value=v)
            if isinstance(v, str) and v.startswith("="):
                c.data_type = "s"              # jangan jalankan sebagai rumus
    for j, k in enumerate(kolom, 1):
        isi = [len(str(k))] + [len(str(b[j - 1])) for b in baris]
        ws.column_dimensions[get_column_letter(j)].width = min(max(isi) + 3, 50)
    ws.freeze_panes = "A5"
    wb.save(path)


def ke_pdf(path, judul, kolom, baris, info="", angka=()):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    doc = SimpleDocTemplate(path, pagesize=landscape(A4), title=judul,
                            leftMargin=24, rightMargin=24, topMargin=28, bottomMargin=30)
    st = getSampleStyleSheet()
    sel = ParagraphStyle("sel", parent=st["BodyText"], fontSize=7, leading=9)
    hdr = ParagraphStyle("hdr", parent=sel, fontName="Helvetica-Bold",
                         textColor=colors.white)

    def p(x, gaya):
        return Paragraph(escape("" if x is None else str(x)).replace("\n", "<br/>"), gaya)

    data = [[p(k, hdr) for k in kolom]] + [[p(x, sel) for x in b] for b in baris]
    bobot = [min(max([len(str(k))] + [len(str(b[j])) for b in baris]), 28) + 2
             for j, k in enumerate(kolom)]
    lebar = [doc.width * x / sum(bobot) for x in bobot]
    tabel = Table(data, colWidths=lebar, repeatRows=1)
    tabel.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#37474F")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9e9e9e")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ]))
    cerita = [Paragraph(escape(judul), st["Heading2"])]
    if info:
        cerita.append(Paragraph(escape(info), st["Italic"]))
    cerita += [Spacer(1, 8), tabel]
    if not baris:
        cerita.append(Paragraph("(tidak ada data)", st["Italic"]))

    def footer(canvas, d):
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(d.pagesize[0] - 24, 14, f"Halaman {d.page}")

    doc.build(cerita, onFirstPage=footer, onLaterPages=footer)
