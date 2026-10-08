from django.contrib import admin

from .models import Member, School, Student

admin.site.register(School)
admin.site.register(Member)
admin.site.register(Student)
