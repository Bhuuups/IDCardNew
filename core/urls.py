from django.urls import path

from . import views as v

urlpatterns = [
    path("", v.home, name="home"),
    path("login/", v.login_view, name="login"),
    path("logout/", v.logout_view, name="logout"),
    # admin
    path("manage/", v.admin_home, name="admin_home"),
    path("manage/schools/add/", v.add_school, name="add_school"),
    path("manage/team/add/", v.add_team, name="add_team"),
    path("manage/team/<int:mid>/allot/", v.allot_team, name="allot_team"),
    path("manage/team/<int:mid>/delete/", v.delete_team, name="delete_team"),
    path("manage/queue/", v.queue, name="queue"),
    path("manage/queue/<int:pk>/mark/", v.queue_mark, name="queue_mark"),
    path("manage/queue/waiting.pdf", v.queue_pdf, name="queue_pdf"),
    path("manage/queue/waiting.csv", v.queue_csv, name="queue_csv"),
    path("manage/design/<int:sid>/", v.design, name="design"),
    path("manage/design/<int:sid>/save/", v.design_save, name="design_save"),
    path("manage/design/<int:sid>/pos/", v.design_pos, name="design_pos"),
    path("manage/design/<int:sid>/sample.pdf", v.design_sample, name="design_sample"),
    path("template-image/<int:sid>/", v.school_bg, name="school_bg"),
    # school and team
    path("s/<int:sid>/", v.school_home, name="school_home"),
    path("s/<int:sid>/fields/", v.school_fields, name="school_fields"),
    path("s/<int:sid>/upload/", v.school_upload, name="school_upload"),
    path("s/<int:sid>/template.csv", v.school_template_csv, name="school_template_csv"),
    path("s/<int:sid>/add/", v.school_add, name="school_add"),
    path("s/<int:sid>/approve/<int:pk>/", v.school_approve, name="school_approve"),
    path("s/<int:sid>/approve-all/", v.school_approve_all, name="school_approve_all"),
    path("s/<int:sid>/card/<int:pk>.pdf", v.card_pdf, name="card_pdf"),
    path("s/<int:sid>/photo-day/", v.photoday, name="photoday"),
    path("s/<int:sid>/photo/<int:pk>/<str:which>/upload/", v.photo_upload, name="photo_upload"),
    path("s/<int:sid>/report/", v.report, name="report"),
    path("photo/<int:sid>/<int:pk>/<str:which>/", v.photo, name="photo"),
    # parent
    path("v/<str:token>/", v.parent, name="parent"),
    path("v/<str:token>/photo/<str:which>/", v.parent_photo, name="parent_photo"),
]
