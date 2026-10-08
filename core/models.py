import re
import secrets
import uuid

from django.db import models
from django.utils import timezone

FIELDS = [
    ("adm", "Admission No"), ("name", "Student Name"), ("cls", "Class"), ("sec", "Section"),
    ("roll", "Roll No"), ("dob", "DOB"), ("blood", "Blood Group"), ("father", "Father's Name"),
    ("mother", "Mother's Name"), ("addr", "Address"), ("smob", "Student Mobile"),
    ("pmob", "Parent Mobile"), ("house", "School House"), ("bus", "Bus Route"),
]
LBL = dict(FIELDS)
PHOTO_KEYS = ("photo", "fphoto", "mphoto")   # student, father, mother
PHOTO_NAMES = {"photo": "Student photo", "fphoto": "Father photo", "mphoto": "Mother photo"}


def default_fields():
    return ["adm", "name", "cls", "sec", "dob", "father", "pmob"]


def default_pp():
    return ["f", "m"]


def new_token():
    return secrets.token_urlsafe(16)


def photo_path(instance, filename):
    return f"photos/{instance.school_id}/{uuid.uuid4().hex}.jpg"


def template_path(instance, filename):
    return f"templates/{instance.pk}-{uuid.uuid4().hex[:8]}.jpg"


def norm_mobile(m):
    d = re.sub(r"\D", "", str(m or ""))
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    if len(d) == 11 and d.startswith("0"):
        d = d[1:]
    return d


def valid_mobile(m):
    return bool(re.fullmatch(r"[6-9]\d{9}", m or ""))


class School(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)            # the school's login email
    session = models.CharField(max_length=20, default="2026-27")
    fields = models.JSONField(default=default_fields)  # which student fields this school collects
    pp = models.JSONField(default=default_pp)          # ["f","m"] = father / mother photo on
    tpl = models.JSONField(default=dict, blank=True)   # {"W","H","lab","pos":{...}}
    bg = models.ImageField(upload_to=template_path, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def photo_fields(self):
        return ["photo"] + [k + "photo" for k in self.pp]


class Member(models.Model):
    """Everyone who logs in with email + OTP: the owner (admin), team members, school staff."""
    ROLES = [("admin", "Admin"), ("team", "Team member"), ("school", "School")]
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=120, blank=True)
    role = models.CharField(max_length=10, choices=ROLES)
    schools = models.ManyToManyField(School, blank=True, related_name="members")

    def __str__(self):
        return f"{self.email} ({self.role})"

    def can(self, school):
        return self.role == "admin" or self.schools.filter(pk=school.pk).exists()

    def my_schools(self):
        return School.objects.all() if self.role == "admin" else self.schools.all()


class OTP(models.Model):
    key = models.CharField(max_length=200, unique=True)   # "login:<email>" or "parent:<token>"
    code_hash = models.CharField(max_length=64)
    expires = models.DateTimeField()
    tries = models.PositiveSmallIntegerField(default=0)
    created = models.DateTimeField(default=timezone.now)


class Student(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="students")
    adm = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    data = models.JSONField(default=dict, blank=True)     # all other fields (cls, sec, dob, ...)
    photo = models.ImageField(upload_to=photo_path, blank=True, null=True)
    fphoto = models.ImageField(upload_to=photo_path, blank=True, null=True)
    mphoto = models.ImageField(upload_to=photo_path, blank=True, null=True)
    # changes the parent made, waiting for OTP confirmation
    pending = models.JSONField(default=dict, blank=True)
    n_photo = models.ImageField(upload_to=photo_path, blank=True, null=True)
    n_fphoto = models.ImageField(upload_to=photo_path, blank=True, null=True)
    n_mphoto = models.ImageField(upload_to=photo_path, blank=True, null=True)
    verified_at = models.DateField(null=True, blank=True)   # parent OTP verified
    appr_at = models.DateField(null=True, blank=True)       # school said OK, sent for print
    printed_at = models.DateField(null=True, blank=True)
    delivered_at = models.DateField(null=True, blank=True)
    chg = models.TextField(blank=True)                      # what the parent changed
    token = models.CharField(max_length=40, unique=True, default=new_token)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("school", "adm")]
        ordering = ["adm"]

    def __str__(self):
        return f"{self.adm} {self.name}"

    def val(self, f):
        if f == "adm":
            return self.adm
        if f == "name":
            return self.name
        return self.data.get(f, "")

    @property
    def stage(self):
        if self.delivered_at:
            return "Delivered"
        if self.printed_at:
            return "Printed"
        if self.appr_at:
            return "Sent for print"
        if self.verified_at:
            return "Awaiting school OK"
        if self.photo:
            return "Awaiting parent"
        return "Needs photo"
