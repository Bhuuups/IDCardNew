"""Makes the print PDF: one card per page, each page in its school's card size and template."""
import io
import os

from django.conf import settings
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from .layout import IMG_KEYS, MM_PT, dims, elpos, tpl
from .models import LBL

_font = {"done": False, "reg": "Helvetica", "bold": "Helvetica-Bold"}


def fonts():
    """Helvetica by default. Set CARD_FONT to a .ttf file for other scripts (see README)."""
    if not _font["done"]:
        _font["done"] = True
        path = settings.CARD_FONT
        if path and os.path.exists(path):
            pdfmetrics.registerFont(TTFont("CardFont", path))
            _font["reg"] = _font["bold"] = "CardFont"
    return _font


def _fit(text, font, size, max_w_mm):
    t = str(text)
    while len(t) > 1 and pdfmetrics.stringWidth(t, font, size) > max_w_mm * mm:
        t = t[:-1]
    return t if t == str(text) else t[:-1] + ".."


def _file(f):
    try:
        return ImageReader(f.path) if f and os.path.exists(f.path) else None
    except Exception:
        return None


def draw_card(c, school, stu):
    W, H = dims(school)
    c.setPageSize((W * mm, H * mm))
    c.setFillColor(HexColor("#ffffff"))
    c.rect(0, 0, W * mm, H * mm, stroke=0, fill=1)
    bg = _file(school.bg)
    if bg:
        c.drawImage(bg, 0, 0, W * mm, H * mm)
    f = fonts()
    lab = tpl(school)["lab"]
    for k, p in elpos(school).items():
        if p.get("hide"):
            continue
        if k in IMG_KEYS:
            img = _file(getattr(stu, k))
            if img:
                c.drawImage(img, p["x"] * mm, (H - p["y"] - p["h"]) * mm, p["w"] * mm, p["h"] * mm)
            continue
        v = school.name if k == "school" else stu.val(k)
        if not v:
            continue
        if lab and k != "school":
            v = f"{LBL[k]}: {v}"
        sz = p.get("sz", 8)
        font = f["bold"] if p.get("b") else f["reg"]
        c.setFont(font, sz)
        c.setFillColor(HexColor(p.get("c", "#000000")))
        v = _fit(v, font, sz, p["w"])
        y = (H - p["y"] - sz * MM_PT * 0.8) * mm
        al = p.get("al", "left")
        if al == "center":
            c.drawCentredString((p["x"] + p["w"] / 2) * mm, y, v)
        elif al == "right":
            c.drawRightString((p["x"] + p["w"]) * mm, y, v)
        else:
            c.drawString(p["x"] * mm, y, v)
    c.showPage()


def cards_pdf(students):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for s in students:
        draw_card(c, s.school, s)
    c.save()
    return buf.getvalue()


def sample_pdf(school):
    from .models import Student
    return cards_pdf([Student(school=school, adm="1001", name="Sample Student",
                              data={"cls": "5", "sec": "A", "dob": "01/01/2015", "father": "Sample Father",
                                    "pmob": "9876543210"})])
