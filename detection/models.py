from django.db import models
from django.core.validators import FileExtensionValidator
from django.contrib.auth import get_user_model
import os

User = get_user_model()


def original_upload_path(instance, filename):
    # salva in: media/videos/<user_id>/original/<filename>
    user_id = instance.user_id or "anon"
    return f"videos/{user_id}/original/{filename}"


class VideoDetection(models.Model):
    STATUS_CHOICES = [
        ('pending', 'In Attesa'),
        ('processing', 'In Elaborazione'),
        ('completed', 'Completato'),
        ('failed', 'Fallito'),
    ]

    # NUOVO: proprietario del video
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="videos",
        null=True, blank=True, verbose_name="Utente"
    )

    title = models.CharField(max_length=200, verbose_name="Titolo")
    original_video = models.FileField(
        upload_to=original_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=['mp4', 'avi', 'mov', 'mkv'])],
        verbose_name="Video Originale"
    )
    # Notare: processed_video lo settiamo noi nel task in una cartella per utente.
    processed_video = models.FileField(
        upload_to='videos/processed/',  # non usata, verrà sovrascritta dal task
        blank=True, null=True,
        verbose_name="Video Processato"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Stato")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creato il")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Aggiornato il")

    # Statistiche detection
    total_frames = models.IntegerField(default=0, verbose_name="Frame Totali")
    processed_frames = models.IntegerField(default=0, verbose_name="Frame Processati")
    detections_count = models.IntegerField(default=0, verbose_name="Numero Rilevazioni")

    # Messaggi di errore
    error_message = models.TextField(blank=True, null=True, verbose_name="Messaggio Errore")

    # Task ID per Celery
    task_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="Task ID")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Rilevazione Video"
        verbose_name_plural = "Rilevazioni Video"
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        owner = f"{self.user}" if self.user_id else "anon"
        return f"[{owner}] {self.title} - {self.get_status_display()}"

    @property
    def progress_percentage(self):
        if self.total_frames > 0:
            return int((self.processed_frames / self.total_frames) * 100)
        return 0

    def delete(self, *args, **kwargs):
        # Elimina i file dal FS quando viene eliminato il record
        try:
            if self.original_video and os.path.isfile(self.original_video.path):
                os.remove(self.original_video.path)
        except Exception:
            pass
        try:
            if self.processed_video and os.path.isfile(self.processed_video.path):
                os.remove(self.processed_video.path)
        except Exception:
            pass
        super().delete(*args, **kwargs)


class Detection(models.Model):
    """Singola detection in un frame"""
    video_detection = models.ForeignKey(
        VideoDetection,
        on_delete=models.CASCADE,
        related_name='detections'
    )
    frame_number = models.IntegerField(verbose_name="Numero Frame")
    class_name = models.CharField(max_length=100, verbose_name="Classe")
    confidence = models.FloatField(verbose_name="Confidenza")
    bbox_x1 = models.FloatField(verbose_name="BBox X1")
    bbox_y1 = models.FloatField(verbose_name="BBox Y1")
    bbox_x2 = models.FloatField(verbose_name="BBox X2")
    bbox_y2 = models.FloatField(verbose_name="BBox Y2")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['frame_number']
        verbose_name = "Rilevazione"
        verbose_name_plural = "Rilevazioni"
        indexes = [
            models.Index(fields=['video_detection', 'frame_number']),
        ]

    def __str__(self):
        return f"{self.class_name} - Frame {self.frame_number} ({self.confidence:.2f})"
