from django.core.management.base import BaseCommand, CommandError

from core.models import Member


class Command(BaseCommand):
    help = "Create the owner (admin) login. Usage: python manage.py create_admin you@example.com"

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--name", default="Owner")

    def handle(self, *a, **o):
        email = o["email"].strip().lower()
        if "@" not in email:
            raise CommandError("Give a valid email.")
        m, made = Member.objects.get_or_create(email=email, defaults=dict(name=o["name"], role="admin"))
        if not made:
            m.role = "admin"
            m.save()
        self.stdout.write(self.style.SUCCESS(f"Admin ready: {email}. Log in at /login/ with an email OTP."))
