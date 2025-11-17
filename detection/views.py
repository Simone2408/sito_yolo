from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files import File
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, FormView, ListView

from celery.result import AsyncResult

from .forms import VideoUploadForm
from .models import VideoDetection
from .tasks import process_video_detection


class SignUpView(FormView):
    template_name = "registration/signup.html"
    form_class = UserCreationForm
    success_url = reverse_lazy("video_list")

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.success(self.request, "Registrazione completata! Benvenuto 👋")
        return super().form_valid(form)


class VideoDetectionListView(LoginRequiredMixin, ListView):
    model = VideoDetection
    template_name = "detection/video_list.html"
    context_object_name = "videos"
    paginate_by = 10

    def get_queryset(self):
        # Mostra SOLO i video dell’utente loggato
        return VideoDetection.objects.filter(user=self.request.user)


class VideoDetectionDetailView(LoginRequiredMixin, DetailView):
    model = VideoDetection
    template_name = "detection/video_detail.html"
    context_object_name = "video"

    def get_queryset(self):
        # L’utente può vedere SOLO i propri video
        return VideoDetection.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        detections = self.object.detections.all()
        classes_stats = {}
        for d in detections:
            if d.class_name not in classes_stats:
                classes_stats[d.class_name] = {
                    "count": 0,
                    "avg_confidence": 0.0,
                    "confidences": [],
                }
            classes_stats[d.class_name]["count"] += 1
            classes_stats[d.class_name]["confidences"].append(d.confidence)
        for cname, stats in classes_stats.items():
            confs = stats["confidences"]
            stats["avg_confidence"] = sum(confs) / len(confs) if confs else 0.0

        context["classes_stats"] = classes_stats

        # eventuale URL per anteprima (se in futuro vuoi usarla nel template)
        user_id_str = str(self.object.user_id or "anon")
        preview_rel = f"videos/{user_id_str}/preview/preview_{self.object.id}.jpg"
        context["preview_url"] = settings.MEDIA_URL + preview_rel

        return context


class VideoUploadView(LoginRequiredMixin, CreateView):
    model = VideoDetection
    form_class = VideoUploadForm
    template_name = "detection/upload_video.html"
    success_url = reverse_lazy("video_list")

    def form_valid(self, form):
        # Assegna l’owner PRIMA di salvare
        obj = form.save(commit=False)
        obj.user = self.request.user
        obj.save()

        # Avvia il task Celery
        task = process_video_detection.delay(obj.id)

        # Salva il task id
        obj.task_id = task.id
        obj.save(update_fields=["task_id"])

        # Risposta AJAX (upload con progress bar)
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"detail_url": reverse("video_detail", args=[obj.pk])})

        messages.success(
            self.request, "Video caricato. Elaborazione avviata in background."
        )
        return redirect(self.get_success_url())


def check_task_status(request, task_id):
    task_result = AsyncResult(task_id)
    data = {"task_id": task_id, "status": task_result.state}
    if task_result.state == "PROGRESS":
        data["progress"] = task_result.info
    elif task_result.state == "SUCCESS":
        data["result"] = task_result.result
    elif task_result.state == "FAILURE":
        data["error"] = str(task_result.info)
    return JsonResponse(data)


def check_video_status(request, video_id):
    # Sicurezza: restituisci stato solo se owner
    video = get_object_or_404(VideoDetection, id=video_id, user=request.user)
    data = {
        "id": video.id,
        "status": video.status,
        "progress": video.progress_percentage,
        "processed_frames": video.processed_frames,
        "total_frames": video.total_frames,
        "detections_count": video.detections_count,
    }
    if video.status == "completed" and video.processed_video:
        data["processed_video_url"] = video.processed_video.url
    elif video.status == "failed":
        data["error"] = video.error_message or "Errore sconosciuto"
    return JsonResponse(data)


@require_POST
@login_required
def delete_video(request, pk: int):
    video = get_object_or_404(VideoDetection, pk=pk, user=request.user)
    title = video.title
    video.delete()
    messages.success(request, f"Video «{title}» eliminato con successo.")
    return redirect("video_list")


# ---------- VIDEO DI ESEMPIO: usa rail_1.mp4 / rail_2.mp4 senza toccare gli originali ---------


@require_POST
@login_required
def use_sample_video(request, code: str):
    """
    Crea un nuovo VideoDetection per l'utente corrente
    utilizzando uno dei video termici di esempio.
    I file di esempio originali NON vengono mai modificati né eliminati.
    """
    sample_map = {
        "sample1": (
            "Video termico ferroviario – Esempio 1",
            Path(settings.MEDIA_ROOT) / "sample_videos" / "rail_1.mp4",
        ),
        "sample2": (
            "Video termico ferroviario – Esempio 2",
            Path(settings.MEDIA_ROOT) / "sample_videos" / "rail_2.mp4",
        ),
    }

    if code not in sample_map:
        messages.error(request, "Video di esempio non valido.")
        return redirect("upload_video")

    title, sample_path = sample_map[code]

    if not sample_path.exists():
        messages.error(
            request,
            "Il file di esempio non è disponibile sul server. "
            "Assicurati che esista in media/sample_videos.",
        )
        return redirect("upload_video")

    # Crea un nuovo VideoDetection per l'utente
    vd = VideoDetection(user=request.user, title=title)

    # Copia il file sorgente nel FileField (nuova copia per l’utente)
    with sample_path.open("rb") as f:
        vd.original_video.save(sample_path.name, File(f), save=True)

    # Avvia il task Celery di elaborazione
    task = process_video_detection.delay(vd.id)
    vd.task_id = task.id
    vd.save(update_fields=["task_id"])

    messages.success(
        request,
        f"Video di esempio «{title}» caricato e inviato al modello per l'elaborazione.",
    )
    return redirect("video_detail", pk=vd.pk)
