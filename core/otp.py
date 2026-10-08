import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.module_loading import import_string

from .models import OTP

log = logging.getLogger(__name__)
OUTBOX = []          # (kind, to, code): kept only in DEBUG / tests, never in production
COOLDOWN = 20        # seconds before a new code can be requested
MAX_TRIES = 3


def _h(code):
    return hashlib.sha256((settings.SECRET_KEY + code).encode()).hexdigest()


def issue(key):
    """Create a 6-digit code (valid 5 minutes). Returns None if asked again too soon."""
    now = timezone.now()
    o = OTP.objects.filter(key=key).first()
    if o and (now - o.created).total_seconds() < COOLDOWN:
        return None
    code = f"{secrets.randbelow(10**6):06d}"
    OTP.objects.update_or_create(key=key, defaults=dict(
        code_hash=_h(code), expires=now + timedelta(minutes=5), tries=0, created=now))
    return code


def check(key, code):
    """'ok', 'wrong', 'expired', 'locked' or 'none'."""
    o = OTP.objects.filter(key=key).first()
    if not o:
        return "none"
    if o.tries >= MAX_TRIES:
        return "locked"
    if timezone.now() > o.expires:
        return "expired"
    o.tries += 1
    o.save(update_fields=["tries"])
    if secrets.compare_digest(o.code_hash, _h(str(code))):
        o.delete()
        return "ok"
    return "wrong"


def _keep(kind, to, code):
    if getattr(settings, "KEEP_OUTBOX", False):
        OUTBOX.append((kind, to, code))
        del OUTBOX[:-50]


def send_email(to, code):
    _keep("email", to, code)
    send_mail("Your ID Card Desk login code",
              f"Your code is {code}. It is valid for 5 minutes. Do not share it.",
              settings.DEFAULT_FROM_EMAIL, [to])


def send_sms(mobile, code):
    """Parent OTP. Plug in your SMS / WhatsApp provider with SMS_SENDER (see README, Step 9)."""
    _keep("sms", mobile, code)
    if settings.SMS_SENDER:
        import_string(settings.SMS_SENDER)(mobile, code)
    else:
        log.warning("SMS provider not configured. OTP for %s: %s", mobile, code if settings.DEBUG else "******")
