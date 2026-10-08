"""EXAMPLE ONLY, not tested against any provider.
To send the parent OTP by SMS/WhatsApp, copy this file's idea: write a function f(mobile, code)
that calls your provider's API (MSG91, Twilio, Gupshup, WhatsApp Business API...), then set
    SMS_SENDER=core.sms_example.send
in your environment. Use the provider's official instructions for the request format, and
register your OTP message template with them first (required in India for DLT)."""
import json
import os
import urllib.request


def send(mobile, code):
    url = os.environ["SMS_API_URL"]          # from your provider
    key = os.environ["SMS_API_KEY"]
    body = json.dumps({"to": "91" + mobile, "otp": code}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json", "Authorization": "Bearer " + key})
    urllib.request.urlopen(req, timeout=10).read()
