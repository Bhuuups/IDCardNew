import io
import re

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from . import otp
from .models import Member, OTP, School, Student


def img(color="red", size=(640, 480)):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "JPEG")
    return SimpleUploadedFile("x.jpg", b.getvalue(), content_type="image/jpeg")


def login(client, email):
    client.post(reverse("login"), {"email": email})
    code = re.search(r"code is (\d{6})", mail.outbox[-1].body).group(1)
    r = client.post(reverse("login"), {"email": email, "code": code})
    return r


@override_settings(KEEP_OUTBOX=True, SHOW_OTP_ON_SCREEN=False)
class Flow(TestCase):
    def setUp(self):
        otp.COOLDOWN = 0
        Member.objects.create(email="owner@x.in", name="Owner", role="admin")

    def test_full_flow(self):
        # --- admin logs in with OTP, adds a school and a team member
        admin = self.client_class()
        self.assertEqual(login(admin, "owner@x.in").status_code, 302)
        admin.post(reverse("add_school"), {"name": "ABC Public School", "email": "abc@school.in"})
        school = School.objects.get(email="abc@school.in")
        admin.post(reverse("add_team"), {"name": "Ravi", "email": "ravi@team.in"})
        ravi = Member.objects.get(email="ravi@team.in")
        admin.post(reverse("allot_team", args=[ravi.pk]), {"schools": [school.pk]})
        self.assertEqual(list(ravi.schools.all()), [school])

        # --- school logs in, picks fields, uploads CSV (one bad row)
        sc = self.client_class()
        login(sc, "abc@school.in")
        self.assertRedirects(sc.get(reverse("home")), reverse("school_home", args=[school.pk]), fetch_redirect_response=False)
        sc.post(reverse("school_fields", args=[school.pk]), {"fields": ["cls", "sec", "pmob", "dob"], "pp": ["f", "m"]})
        school.refresh_from_db()
        self.assertEqual(school.fields, ["adm", "name", "cls", "sec", "dob", "pmob"])
        csv = ("Admission No,Student Name,Class,Section,DOB,Parent Mobile\n"
               "1001,Rahul Sharma,5,A,01/01/2015,+91 98765-43210\n"
               "1002,Aman,5,A,02/02/2015,12345\n"
               "1001,Dup,5,B,03/03/2015,9876543211\n"
               "1003,Priya,6,B,04/04/2014,9876543212\n")
        r = sc.post(reverse("school_upload", args=[school.pk]),
                    {"csv": SimpleUploadedFile("s.csv", csv.encode(), content_type="text/csv")})
        self.assertEqual(school.students.count(), 2)
        rahul = school.students.get(adm="1001")
        self.assertEqual(rahul.data["pmob"], "9876543210")           # cleaned
        self.assertEqual(len(sc.session["import_errors"]), 2)

        # --- photo day: student + father photo; photos are cropped to 4:5
        r = sc.post(reverse("photo_upload", args=[school.pk, rahul.pk, "photo"]), {"image": img()})
        self.assertEqual(r.json(), {"ok": True})
        sc.post(reverse("photo_upload", args=[school.pk, rahul.pk, "fphoto"]), {"image": img("blue")})
        rahul.refresh_from_db()
        w, h = Image.open(rahul.photo.path).size
        self.assertEqual((w, h), (480, 600))
        bad = sc.post(reverse("photo_upload", args=[school.pk, rahul.pk, "photo"]),
                      {"image": SimpleUploadedFile("a.jpg", b"not an image")})
        self.assertEqual(bad.status_code, 400)

        # --- photos are private
        self.assertEqual(sc.get(reverse("photo", args=[school.pk, rahul.pk, "photo"])).status_code, 200)
        self.assertEqual(self.client_class().get(reverse("photo", args=[school.pk, rahul.pk, "photo"])).status_code, 302)

        # --- parent: change class, upload mother's photo, verify by OTP
        pc = self.client_class()
        url = reverse("parent", args=[rahul.token])
        self.assertEqual(pc.get(url).status_code, 200)
        pc.post(url, {"action": "send", "name": "Rahul K Sharma", "cls": "5", "sec": "B", "dob": "01/01/2015", "mphoto": img("green")})
        code = otp.OUTBOX[-1][2]
        self.assertEqual(otp.OUTBOX[-1][1], "9876543210")
        pc.post(url, {"action": "verify", "code": "000000"})
        rahul.refresh_from_db()
        self.assertIsNone(rahul.verified_at)                          # wrong code does nothing
        pc.post(url, {"action": "verify", "code": code})
        rahul.refresh_from_db()
        self.assertIsNotNone(rahul.verified_at)
        self.assertEqual((rahul.name, rahul.data["sec"]), ("Rahul K Sharma", "B"))
        self.assertIn("Section: A to B", rahul.chg)
        self.assertIn("Mother photo changed", rahul.chg)
        self.assertTrue(rahul.mphoto)

        # --- school says OK, admin prints
        sc.post(reverse("school_approve", args=[school.pk, rahul.pk]))
        rahul.refresh_from_db()
        self.assertIsNotNone(rahul.appr_at)
        r = admin.get(reverse("queue_pdf"))
        self.assertTrue(r.content.startswith(b"%PDF"))
        admin.post(reverse("queue_mark", args=[rahul.pk]), {"what": "printed"})
        admin.post(reverse("queue_mark", args=[rahul.pk]), {"what": "delivered"})
        rahul.refresh_from_db()
        self.assertEqual(rahul.stage, "Delivered")
        self.assertContains(admin.get(reverse("admin_home")), "ABC Public School")

        # --- reports
        r = sc.get(reverse("report", args=[school.pk]) + "?csv=summary")
        self.assertIn("5", r.content.decode())
        self.assertEqual(sc.get(reverse("report", args=[school.pk])).status_code, 200)

        # --- team member sees only the allotted school; school staff cannot open admin pages
        tm = self.client_class()
        login(tm, "ravi@team.in")
        self.assertRedirects(tm.get(reverse("home")), reverse("school_home", args=[school.pk]), fetch_redirect_response=False)
        other = School.objects.create(name="Other", email="o@o.in")
        self.assertEqual(tm.get(reverse("school_home", args=[other.pk])).status_code, 403)
        self.assertEqual(sc.get(reverse("admin_home")).status_code, 403)

    def test_design_and_pdf(self):
        admin = self.client_class()
        login(admin, "owner@x.in")
        s = School.objects.create(name="D School", email="d@d.in")
        stu = Student.objects.create(school=s, adm="1", name="Sample", data={"cls": "5", "pmob": "9876543210"})
        stu.photo.save("p.jpg", __import__("core.photos", fromlist=["x"]).process_photo(img()), save=True)
        bg = img("#ffe9a8", (1011, 638))
        admin.post(reverse("design_save", args=[s.pk]), {"W": "85.6", "H": "54", "bg": bg, "autosize": "1"})
        s.refresh_from_db()
        self.assertTrue(s.bg)
        admin.post(reverse("design_pos", args=[s.pk]), {"key": "name", "x": "30", "y": "12"})
        admin.post(reverse("design_pos", args=[s.pk]), {"key": "cls", "form": "1", "x": "30", "y": "20", "sz": "9", "c": "#ff0000", "al": "center", "show": "1", "b": "1"})
        s.refresh_from_db()
        self.assertEqual(s.tpl["pos"]["name"]["x"], 30.0)
        self.assertEqual(s.tpl["pos"]["cls"]["c"], "#ff0000")
        page = admin.get(reverse("design", args=[s.pk]))
        self.assertContains(page, "chip")
        self.assertTrue(admin.get(reverse("design_sample", args=[s.pk])).content.startswith(b"%PDF"))
        self.assertEqual(admin.get(reverse("school_bg", args=[s.pk])).status_code, 200)

    def test_otp_rules(self):
        k = "login:z@z.in"
        code = otp.issue(k)
        self.assertEqual(otp.check(k, "000000" if code != "000000" else "111111"), "wrong")
        self.assertEqual(otp.check(k, "999999" if code != "999999" else "888888"), "wrong")
        self.assertEqual(otp.check(k, "123456" if code != "123456" else "654321"), "wrong")
        self.assertEqual(otp.check(k, code), "locked")        # 3 wrong tries lock the code
        code = otp.issue(k)
        self.assertEqual(otp.check(k, code), "ok")
        self.assertEqual(otp.check(k, code), "none")           # a code works once

    def test_unknown_email_gets_no_code(self):
        c = self.client_class()
        r = c.post(reverse("login"), {"email": "nobody@x.in"})
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(r, "If this email is registered")
