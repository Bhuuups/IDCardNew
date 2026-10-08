import csv
import io
from datetime import timedelta
from functools import wraps
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import otp
from .layout import IMG_KEYS, dims, elements, elpos, tpl
from .models import (FIELDS, LBL, PHOTO_KEYS, PHOTO_NAMES, Member, OTP, School, Student,
                     norm_mobile, valid_mobile)
from .pdfcards import cards_pdf, sample_pdf
from .photos import process_photo, process_template

SAMPLE = {"adm": "1001", "name": "Sample Student", "cls": "5", "sec": "A", "dob": "01/01/2015",
          "father": "Sample Father", "mother": "Sample Mother", "pmob": "9876543210"}


# ---------- helpers ----------
def today():
    return timezone.localdate()


def current(request):
    mid = request.session.get("mid")
    return Member.objects.filter(pk=mid).first() if mid else None


def member_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(request, *a, **kw):
            m = current(request)
            if not m:
                return redirect(f"{reverse('login')}?next={quote(request.get_full_path())}")
            if roles and m.role not in roles:
                raise PermissionDenied
            request.member = m
            return fn(request, *a, **kw)
        return wrapper
    return deco


def school_for(request, sid):
    school = get_object_or_404(School, pk=sid)
    if not request.member.can(school):
        raise PermissionDenied
    return school


def stats(qs):
    n = lambda **f: qs.filter(**f).count()
    return [("Students", qs.count()), ("Photos taken", qs.exclude(photo="").count()),
            ("Parent verified", qs.exclude(verified_at=None).count()),
            ("Awaiting school OK", qs.exclude(verified_at=None).filter(appr_at=None).count()),
            ("Sent for print", qs.exclude(appr_at=None).count()),
            ("Printed", qs.exclude(printed_at=None).count()),
            ("Delivered", qs.exclude(delivered_at=None).count())]


def pdf_response(data, name):
    r = HttpResponse(data, content_type="application/pdf")
    r["Content-Disposition"] = f'inline; filename="{name}"'
    return r


def csv_response(rows, name):
    r = HttpResponse(content_type="text/csv; charset=utf-8")
    r["Content-Disposition"] = f'attachment; filename="{name}"'
    r.write("\ufeff")
    csv.writer(r).writerows(rows)
    return r


def safe_name(s):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(s))


# ---------- login ----------
def login_view(request):
    step, email = "email", ""
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        member = Member.objects.filter(email=email).first()
        code = request.POST.get("code", "").strip()
        if code:
            step = "code"
            res = otp.check("login:" + email, code) if member else "wrong"
            if res == "ok":
                request.session.cycle_key()
                request.session["mid"] = member.pk
                nxt = request.GET.get("next", "")
                return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "home")
            messages.error(request, {"expired": "That code has expired. Ask for a new one.",
                                     "locked": "Too many wrong attempts. Ask for a new code."}.get(res, "Wrong code."))
        else:
            step = "code"
            messages.info(request, "If this email is registered, a 6-digit code has been sent to it.")
            if member:
                new = otp.issue("login:" + email)
                if new is None:
                    messages.error(request, "Please wait a few seconds before asking for another code.")
                else:
                    otp.send_email(email, new)
                    if settings.SHOW_OTP_ON_SCREEN:
                        messages.warning(request, f"Development mode: your code is {new}")
    return render(request, "core/login.html", {"step": step, "email": email})


def logout_view(request):
    request.session.flush()
    return redirect("login")


@member_required()
def home(request):
    m = request.member
    if m.role == "admin":
        return redirect("admin_home")
    schools = list(m.my_schools())
    if len(schools) == 1:
        return redirect("school_home", sid=schools[0].pk)
    return render(request, "core/school_pick.html", {"member": m, "schools": schools})


# ---------- admin ----------
@member_required("admin")
def admin_home(request):
    t = today()
    days = [t - timedelta(days=i) for i in range(7)]
    per_day = [(d, Student.objects.filter(appr_at=d).count(), Student.objects.filter(printed_at=d).count()) for d in days]
    rows = []
    for s in School.objects.all():
        q = s.students.all()
        rows.append(dict(school=s, total=q.count(), verified=q.exclude(verified_at=None).count(),
                         ready_today=q.filter(appr_at=t).count(),
                         waiting=q.exclude(appr_at=None).filter(printed_at=None).count(),
                         printed=q.exclude(printed_at=None).count(), delivered=q.exclude(delivered_at=None).count()))
    return render(request, "core/admin_home.html", dict(
        member=request.member, stats=stats(Student.objects.all()), per_day=per_day, rows=rows, today=t,
        team=Member.objects.filter(role="team").prefetch_related("schools"), schools=School.objects.all()))


@member_required("admin")
@require_POST
def add_school(request):
    name, email = request.POST.get("name", "").strip(), request.POST.get("email", "").strip().lower()
    if not name or "@" not in email:
        messages.error(request, "Enter the school name and a valid email.")
    elif Member.objects.filter(email=email).exists() or School.objects.filter(email=email).exists():
        messages.error(request, "That email is already used.")
    else:
        with transaction.atomic():
            s = School.objects.create(name=name, email=email, session=request.POST.get("session", "2026-27").strip())
            Member.objects.create(email=email, name=name, role="school").schools.add(s)
        messages.success(request, f"School added. {email} can now log in with an OTP.")
    return redirect("admin_home")


@member_required("admin")
@require_POST
def add_team(request):
    name, email = request.POST.get("name", "").strip(), request.POST.get("email", "").strip().lower()
    if not name or "@" not in email:
        messages.error(request, "Enter the member's name and a valid email.")
    elif Member.objects.filter(email=email).exists():
        messages.error(request, "That email is already used.")
    else:
        Member.objects.create(email=email, name=name, role="team")
        messages.success(request, "Team member added. Tick the schools to allot to them.")
    return redirect("admin_home")


@member_required("admin")
@require_POST
def allot_team(request, mid):
    m = get_object_or_404(Member, pk=mid, role="team")
    m.schools.set(School.objects.filter(pk__in=request.POST.getlist("schools")))
    messages.success(request, f"Schools updated for {m.name}.")
    return redirect("admin_home")


@member_required("admin")
@require_POST
def delete_team(request, mid):
    get_object_or_404(Member, pk=mid, role="team").delete()
    return redirect("admin_home")


@member_required("admin")
def queue(request):
    q = Student.objects.exclude(appr_at=None).filter(delivered_at=None).select_related("school").order_by("-appr_at", "school__name", "adm")
    return render(request, "core/queue.html", dict(member=request.member, q=q))


@member_required("admin")
@require_POST
def queue_mark(request, pk):
    s = get_object_or_404(Student, pk=pk)
    what = request.POST.get("what")
    if what == "printed" and s.appr_at:
        s.printed_at = today()
    elif what == "delivered" and s.printed_at:
        s.delivered_at = today()
    s.save()
    return redirect("queue")


@member_required("admin")
def queue_pdf(request):
    q = list(Student.objects.exclude(appr_at=None).filter(printed_at=None).select_related("school"))
    if not q:
        messages.error(request, "No cards are waiting to print.")
        return redirect("queue")
    return pdf_response(cards_pdf(q), "waiting-cards.pdf")


@member_required("admin")
def queue_csv(request):
    q = Student.objects.exclude(appr_at=None).filter(printed_at=None).select_related("school")
    rows = [["School", "Admission No", "Name", "Class", "Section", "Approved on"]]
    rows += [[s.school.name, s.adm, s.name, s.data.get("cls", ""), s.data.get("sec", ""), s.appr_at] for s in q]
    return csv_response(rows, "print-queue.csv")


# ---------- card design (admin) ----------
def sample_text(stu):
    return (lambda k: stu.val(k)) if stu else (lambda k: SAMPLE.get(k, ""))


@member_required("admin")
def design(request, sid):
    school = get_object_or_404(School, pk=sid)
    stu = school.students.exclude(photo="").first() or school.students.first()
    img = (lambda k: reverse("photo", args=[sid, stu.pk, k]) if stu and getattr(stu, k) else None)
    W, H = dims(school)
    pos = elpos(school)
    chips = [dict(key=k, name=PHOTO_NAMES.get(k) or ("School name" if k == "school" else LBL[k]),
                  l=p["x"] / W * 100, t=p["y"] / H * 100, w=p["w"] / W * 100,
                  h=(p["h"] if k in IMG_KEYS else p.get("sz", 8) * 0.3528 * 1.15) / H * 100,
                  hide=p.get("hide")) for k, p in pos.items()]
    sel = request.GET.get("sel")
    return render(request, "core/design.html", dict(
        member=request.member, school=school, W=W, H=H, lab=tpl(school)["lab"], chips=chips,
        els=elements(school, sample_text(stu), img, placeholder=True),
        bg=reverse("school_bg", args=[sid]) if school.bg else "",
        sel=sel if sel in pos else "", selp=pos.get(sel), sel_img=sel in IMG_KEYS,
        sel_name=PHOTO_NAMES.get(sel) or ("School name" if sel == "school" else LBL.get(sel, ""))))


@member_required("admin")
@require_POST
def design_save(request, sid):
    school = get_object_or_404(School, pk=sid)
    t = tpl(school)
    t["pos"] = dict(t["pos"])
    try:
        t["W"], t["H"] = float(request.POST["W"]), float(request.POST["H"])
        if not (20 <= t["W"] <= 300 and 20 <= t["H"] <= 300):
            raise ValueError
    except (KeyError, ValueError):
        messages.error(request, "Card width and height must be numbers between 20 and 300 mm.")
        return redirect("design", sid=sid)
    t["lab"] = bool(request.POST.get("lab"))
    if request.POST.get("remove_bg"):
        school.bg = None
    up = request.FILES.get("bg")
    if up:
        try:
            content, aspect = process_template(up)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("design", sid=sid)
        school.bg.save("t.jpg", content, save=False)
        if request.POST.get("autosize"):
            t["W"], t["H"] = (85.6, round(85.6 / aspect, 1)) if aspect >= 1 else (round(85.6 * aspect, 1), 85.6)
    school.tpl = t
    school.save()
    messages.success(request, "Design saved.")
    return redirect("design", sid=sid)


@member_required("admin")
@require_POST
def design_pos(request, sid):
    school = get_object_or_404(School, pk=sid)
    key = request.POST.get("key", "")
    cur = elpos(school)
    if key not in cur:
        raise Http404
    p = dict(cur[key])
    try:
        for f in ("x", "y", "w", "h", "sz"):
            if request.POST.get(f) not in (None, ""):
                p[f] = round(float(request.POST[f]), 2)
        if key in IMG_KEYS and request.POST.get("w") and not request.POST.get("h"):
            p["h"] = round(p["w"] * 1.25, 2)
    except ValueError:
        return JsonResponse({"ok": False}, status=400)
    if request.POST.get("form"):
        p["hide"] = not request.POST.get("show")
        if key not in IMG_KEYS:
            p["b"] = bool(request.POST.get("b"))
            if request.POST.get("c", "").startswith("#") and len(request.POST["c"]) == 7:
                p["c"] = request.POST["c"]
            if request.POST.get("al") in ("left", "center", "right"):
                p["al"] = request.POST["al"]
    t = tpl(school)
    t["pos"] = dict(t["pos"])
    t["pos"][key] = p
    school.tpl = t
    school.save()
    if request.POST.get("form"):
        return redirect(f"{reverse('design', args=[sid])}?sel={key}")
    return JsonResponse({"ok": True})


@member_required("admin")
def design_sample(request, sid):
    return pdf_response(sample_pdf(get_object_or_404(School, pk=sid)), "sample-card.pdf")


def school_bg(request, sid):
    """The card design image (not a secret: it is the blank template)."""
    s = get_object_or_404(School, pk=sid)
    if not s.bg:
        raise Http404
    return FileResponse(s.bg.open("rb"), content_type="image/jpeg")


# ---------- photos (always permission-checked) ----------
def _photo_response(stu, which, pending=False):
    f = getattr(stu, ("n_" if pending else "") + which)
    if not f:
        raise Http404
    r = FileResponse(f.open("rb"), content_type="image/jpeg")
    r["Cache-Control"] = "private, no-store"
    return r


@member_required()
def photo(request, sid, pk, which):
    school = school_for(request, sid)
    if which not in PHOTO_KEYS:
        raise Http404
    return _photo_response(get_object_or_404(Student, pk=pk, school=school), which)


# ---------- school ----------
def validate_row(school, d, seen):
    e = []
    if not d.get("adm"):
        e.append("Admission No is missing")
    elif d["adm"] in seen:
        e.append(f"Admission No {d['adm']} already exists")
    if not d.get("name"):
        e.append("Student Name is missing")
    for m in ("pmob", "smob"):
        if m in d and d[m]:
            raw = d[m]
            d[m] = norm_mobile(raw)
            if not valid_mobile(d[m]):
                e.append(f'{LBL[m]} "{raw}" must be 10 digits starting with 6, 7, 8 or 9')
    if "pmob" in school.fields and not d.get("pmob"):
        e.append("Parent Mobile is missing")
    return e


def make_student(school, d):
    d = dict(d)
    adm, name = d.pop("adm"), d.pop("name")
    return Student.objects.create(school=school, adm=adm, name=name, data={k: v for k, v in d.items() if v})


def import_csv(school, f):
    rows = list(csv.reader(io.StringIO(f.read().decode("utf-8-sig", errors="replace"))))
    if not rows:
        return 0, ["The file is empty."]
    head = [h.strip().lower() for h in rows[0]]
    cols = {k: head.index(LBL[k].lower()) for k in school.fields if LBL[k].lower() in head}
    missing = [LBL[k] for k in school.fields if k not in cols]
    if missing:
        return 0, ["Columns not found in file: " + ", ".join(missing)]
    seen = set(school.students.values_list("adm", flat=True))
    ok, errs = 0, []
    for i, r in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in r):
            continue
        d = {k: (r[ix].strip() if ix < len(r) else "") for k, ix in cols.items()}
        e = validate_row(school, d, seen)
        if e:
            errs.append(f"Row {i}: " + "; ".join(e))
            continue
        make_student(school, d)
        seen.add(d["adm"])
        ok += 1
    return ok, errs


@member_required()
def school_home(request, sid):
    school = school_for(request, sid)
    q = school.students.all()
    s = request.GET.get("q", "").strip().lower()
    rows = []
    for st in q:
        if s and s not in (st.adm + " " + st.name + " " + " ".join(map(str, st.data.values()))).lower():
            continue
        st.link = request.build_absolute_uri(reverse("parent", args=[st.token]))
        mob = norm_mobile(st.data.get("pmob", ""))
        st.wa = (f"https://wa.me/91{mob}?text=" + quote(
            f"Please verify {st.name}'s ID card details for {school.name}: {st.link}")) if valid_mobile(mob) else ""
        rows.append(st)
    return render(request, "core/school_home.html", dict(
        member=request.member, school=school, tab="students", stats=stats(q), rows=rows, q=s,
        all_fields=FIELDS, errors=request.session.pop("import_errors", None)))


@member_required()
@require_POST
def school_fields(request, sid):
    school = school_for(request, sid)
    chosen = set(request.POST.getlist("fields")) | {"adm", "name"}
    school.fields = [k for k, _ in FIELDS if k in chosen]
    school.pp = [k for k in ("f", "m") if k in request.POST.getlist("pp")]
    school.save()
    messages.success(request, "ID card fields saved.")
    return redirect("school_home", sid=sid)


@member_required()
@require_POST
def school_upload(request, sid):
    school = school_for(request, sid)
    f = request.FILES.get("csv")
    if not f:
        messages.error(request, "Choose a CSV file first.")
    else:
        ok, errs = import_csv(school, f)
        (messages.success if ok else messages.error)(request, f"{ok} students added, {len(errs)} rows skipped.")
        request.session["import_errors"] = errs[:100]
    return redirect("school_home", sid=sid)


@member_required()
def school_template_csv(request, sid):
    school = school_for(request, sid)
    return csv_response([[LBL[k] for k in school.fields]], "template.csv")


@member_required()
@require_POST
def school_add(request, sid):
    school = school_for(request, sid)
    d = {k: request.POST.get(k, "").strip() for k in school.fields}
    e = validate_row(school, d, set(school.students.values_list("adm", flat=True)))
    if e:
        messages.error(request, "; ".join(e))
    else:
        make_student(school, d)
        messages.success(request, "Student added.")
    return redirect("school_home", sid=sid)


@member_required()
@require_POST
def school_approve(request, sid, pk):
    school = school_for(request, sid)
    s = get_object_or_404(Student, pk=pk, school=school)
    if s.verified_at and not s.appr_at:
        s.appr_at = today()
        s.save()
        messages.success(request, f"{s.name} sent to admin for printing.")
    return redirect("school_home", sid=sid)


@member_required()
@require_POST
def school_approve_all(request, sid):
    school = school_for(request, sid)
    n = school.students.exclude(verified_at=None).filter(appr_at=None, chg="").update(appr_at=today())
    messages.success(request, f"{n} students sent to admin for printing (those with no parent changes).")
    return redirect("school_home", sid=sid)


@member_required()
def card_pdf(request, sid, pk):
    school = school_for(request, sid)
    s = get_object_or_404(Student, pk=pk, school=school)
    return pdf_response(cards_pdf([s]), f"{safe_name(s.adm)}-{safe_name(s.name)}.pdf")


@member_required()
def photoday(request, sid):
    school = school_for(request, sid)
    adm = request.GET.get("adm", "").strip()
    stu = school.students.filter(adm=adm).first() if adm else None
    if adm and not stu:
        messages.error(request, f"No student with admission no {adm} in this school.")
    return render(request, "core/photoday.html", dict(
        member=request.member, school=school, tab="photo", stu=stu, adm=adm,
        targets=[(k, PHOTO_NAMES[k]) for k in school.photo_fields]))


@member_required()
@require_POST
def photo_upload(request, sid, pk, which):
    school = school_for(request, sid)
    if which not in school.photo_fields:
        raise Http404
    s = get_object_or_404(Student, pk=pk, school=school)
    f = request.FILES.get("image")
    if not f:
        return JsonResponse({"ok": False, "error": "No image received."}, status=400)
    try:
        content = process_photo(f)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    getattr(s, which).save("p.jpg", content, save=False)
    if which == "photo":                      # a new student photo must be confirmed by the parent again
        s.verified_at = s.appr_at = None
    s.save()
    return JsonResponse({"ok": True})


@member_required()
def report(request, sid):
    school = school_for(request, sid)
    split = bool(request.GET.get("sec")) and "sec" in school.fields
    groups = {}
    for s in school.students.all():
        k = (s.data.get("cls") or "-") + (("-" + (s.data.get("sec") or "-")) if split else "") if "cls" in school.fields else "All students"
        groups.setdefault(k, []).append(s)
    keys = sorted(groups, key=lambda x: [int(p) if p.isdigit() else p for p in __import__("re").split(r"(\d+)", x)])
    cols = ["Students", "Photos taken", "Photo missing", "Parent verified", "Awaiting parent", "Sent for print", "Printed", "Delivered"]

    def row(a):
        return [len(a), sum(1 for x in a if x.photo), sum(1 for x in a if not x.photo),
                sum(1 for x in a if x.verified_at), sum(1 for x in a if x.photo and not x.verified_at),
                sum(1 for x in a if x.appr_at), sum(1 for x in a if x.printed_at), sum(1 for x in a if x.delivered_at)]

    table = [(k, row(groups[k])) for k in keys]
    total = row([s for g in groups.values() for s in g])
    sel = request.GET.get("cls")
    sel = sel if sel in groups else (keys[0] if keys else "")
    if request.GET.get("csv") == "summary":
        return csv_response([["Class"] + cols] + [[k] + r for k, r in table] + [["Total"] + total],
                            f"{safe_name(school.name)}-class-summary.csv")
    if request.GET.get("csv") == "class" and sel:
        rows = [[LBL[f] for f in school.fields] + ["Photo", "Status"]]
        rows += [[s.val(f) for f in school.fields] + ["Yes" if s.photo else "Missing", s.stage] for s in groups[sel]]
        return csv_response(rows, f"{safe_name(school.name)}-class-{safe_name(sel)}.csv")
    return render(request, "core/report.html", dict(
        member=request.member, school=school, tab="reports", cols=cols, table=table, total=total,
        sel=sel, students=groups.get(sel, []), split=split, has_sec="sec" in school.fields))


# ---------- parent (public link + mobile OTP) ----------
def apply_pending(s):
    changes = []
    for k, v in s.pending.items():
        old = s.val(k)
        if v != old:
            changes.append(f"{LBL[k]}: {old or '-'} to {v}")
        if k == "name":
            s.name = v
        elif v:
            s.data[k] = v
        else:
            s.data.pop(k, None)
    for w in PHOTO_KEYS:
        n = getattr(s, "n_" + w)
        if n:
            setattr(s, w, n.name)
            setattr(s, "n_" + w, None)
            changes.append(PHOTO_NAMES[w] + " changed")
    s.pending = {}
    s.chg = "; ".join(changes)


def parent(request, token):
    s = get_object_or_404(Student, token=token)
    school = s.school
    mob = norm_mobile(s.data.get("pmob", ""))
    editable = [f for f in school.fields if f not in ("adm", "pmob")]
    key = "parent:" + token
    if request.method == "POST" and s.photo and not s.verified_at:
        action = request.POST.get("action")
        if action == "send":
            edits, errs = {}, []
            for f in editable:
                v = request.POST.get(f, s.val(f)).strip()
                if f == "smob" and v:
                    v = norm_mobile(v)
                    if not valid_mobile(v):
                        errs.append("Student mobile must be 10 digits starting with 6, 7, 8 or 9.")
                if f == "name" and not v:
                    errs.append("Name cannot be empty.")
                edits[f] = v
            for w in school.photo_fields:
                up = request.FILES.get(w)
                if up:
                    try:
                        getattr(s, "n_" + w).save("p.jpg", process_photo(up), save=False)
                    except ValueError as e:
                        errs.append(str(e))
            if not valid_mobile(mob):
                errs.append("No valid parent mobile number is on record. Please contact the school.")
            if errs:
                for e in dict.fromkeys(errs):
                    messages.error(request, e)
                s.save()
            else:
                s.pending = edits
                s.save()
                code = otp.issue(key)
                if code is None:
                    messages.error(request, "Please wait a few seconds before asking for another code.")
                else:
                    otp.send_sms(mob, code)
                    messages.info(request, "A 6-digit code was sent to the mobile number on record.")
                    if settings.SHOW_OTP_ON_SCREEN:
                        messages.warning(request, f"Development mode: your code is {code}")
        elif action == "verify":
            res = otp.check(key, request.POST.get("code", "").strip())
            if res == "ok":
                apply_pending(s)
                s.verified_at, s.appr_at = today(), None
                s.save()
                messages.success(request, "Thank you. The details are verified and sent to the school.")
                return redirect("parent", token=token)
            messages.error(request, {"expired": "That code has expired. Send a new one.",
                                     "locked": "Too many wrong attempts. Send a new code.",
                                     "none": "Send a code first."}.get(res, "Wrong code. Try again."))
    s.refresh_from_db()
    pend = {**{f: s.val(f) for f in school.fields}, **s.pending}
    img = lambda k: (reverse("parent_photo", args=[token, k]) + ("?p=1" if getattr(s, "n_" + k) else "")
                     if (getattr(s, "n_" + k) or getattr(s, k)) else None)
    return render(request, "core/parent.html", dict(
        s=s, school=school, verified=bool(s.verified_at), ready=bool(s.photo),
        otp_sent=OTP.objects.filter(key=key).exists() and not s.verified_at,
        masked=("X" * 6 + mob[-4:]) if mob else "", cur=pend,
        fields=[(f, LBL[f], pend.get(f, "")) for f in editable],
        targets=[(k, PHOTO_NAMES[k]) for k in school.photo_fields],
        els=elements(school, lambda k: pend.get(k, ""), img),
        W=dims(school)[0], H=dims(school)[1],
        bg=reverse("school_bg", args=[school.pk]) if school.bg else ""))


def parent_photo(request, token, which):
    s = get_object_or_404(Student, token=token)
    if which not in PHOTO_KEYS:
        raise Http404
    return _photo_response(s, which, pending=bool(request.GET.get("p")))
