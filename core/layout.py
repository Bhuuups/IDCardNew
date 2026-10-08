"""Where each item sits on a school's card. Units are millimetres, measured from the top-left."""
from .models import LBL

MM_PT = 0.3528          # 1 point in mm
IMG_KEYS = {"photo", "fphoto", "mphoto"}


def tpl(school):
    t = {"W": 85.6, "H": 54.0, "lab": False, "pos": {}}
    t.update(school.tpl or {})
    return t


def dims(school):
    t = tpl(school)
    return float(t["W"]), float(t["H"])


def keys(school):
    return ["school"] + school.photo_fields + list(school.fields)


def elpos(school):
    """Saved positions, with sensible defaults for anything not placed yet."""
    W, H = dims(school)
    saved = tpl(school)["pos"]
    out, ty, shown = {}, H * 0.22, 0
    for k in keys(school):
        if k in saved:
            out[k] = dict(saved[k])
            if k not in IMG_KEYS and k != "school":
                shown += 1
            continue
        if k == "school":
            out[k] = dict(x=3, y=2.5, w=W - 6, sz=9, c="#14213d", al="left", b=True, hide=bool(school.bg))
        elif k == "photo":
            out[k] = dict(x=W * .04, y=H * .2, w=W * .24, h=W * .3)
        elif k in IMG_KEYS:
            out[k] = dict(x=W * (.04 if k == "fphoto" else .17), y=H * .72, w=W * .1, h=W * .125)
        else:
            out[k] = dict(x=W * .36, y=ty, w=W * .58, sz=8, c="#000000", al="left", b=(k == "name"), hide=shown >= 6)
            ty += 5.2
            shown += 1
    return out


def elements(school, text_of, img_url_of, placeholder=False):
    """Items to draw on the card. text_of(key)->str, img_url_of(key)->url or None."""
    W, H = dims(school)
    lab = tpl(school)["lab"]
    out = []
    for k, p in elpos(school).items():
        if p.get("hide"):
            continue
        base = dict(key=k, l=p["x"] / W * 100, t=p["y"] / H * 100, w=p["w"] / W * 100)
        if k in IMG_KEYS:
            url = img_url_of(k)
            if not url and not placeholder:
                continue
            out.append(dict(base, img=True, h=p["h"] / H * 100, url=url))
        else:
            v = school.name if k == "school" else text_of(k)
            if not v:
                if not placeholder:
                    continue
                v = "[" + LBL.get(k, k) + "]"
            elif lab and k != "school":
                v = f"{LBL[k]}: {v}"
            out.append(dict(base, img=False, text=v, fs=p["sz"] * MM_PT / W * 100,
                            c=p.get("c", "#000000"), al=p.get("al", "left"), b=bool(p.get("b"))))
    return out
