from django.urls import path
from . import views

urlpatterns = [
    # Lista dei video (homepage dell’app)
    path("", views.VideoDetectionListView.as_view(), name="video_list"),

    # Pagina per caricare un nuovo video
    path("upload/", views.VideoUploadView.as_view(), name="upload_video"),

    # Dettaglio di un singolo video (stato, risultati, ecc.)
    path("video/<int:pk>/", views.VideoDetectionDetailView.as_view(), name="video_detail"),

    # API: controllo stato del task Celery (per polling)
    path("api/task/<str:task_id>/status/", views.check_task_status, name="task_status"),

    # API: stato generale del video (progress, frame analizzati, ecc.)
    path("api/video/<int:video_id>/status/", views.check_video_status, name="video_status"),

    # Eliminazione di un video (cancella anche file e detection collegate)
    path("video/<int:pk>/delete/", views.delete_video, name="delete_video"),

    # Uso di un video di esempio (per fare test senza upload)
    path("use-sample/<str:code>/", views.use_sample_video, name="use_sample_video"),

    # Pagina di registrazione utenti
    path("accounts/signup/", views.SignUpView.as_view(), name="signup"),
]
