# detection/tasks.py
from celery import shared_task, states
from celery.exceptions import Ignore
from django.conf import settings

from .models import VideoDetection, Detection

from ultralytics import YOLO
import cv2
import torch
from pathlib import Path
from functools import lru_cache
import logging
from typing import Dict, List, Tuple
import subprocess

logger = logging.getLogger(__name__)

# ---- PALETTE FISSA (BGR) PER 6 CLASSI ----
# NB: OpenCV usa BGR. Ordine dei colori in cui verranno assegnati alle classi.
_CLASS_PALETTE_6: List[Tuple[int, int, int]] = [
    (0, 255, 0),     # Verde
    (255, 0, 0),     # Blu
    (0, 0, 255),     # Rosso
    (0, 255, 255),   # Giallo (BGR)
    (255, 0, 255),   # Magenta
    (255, 255, 0),   # Ciano
]

# Verrà popolata in base a model.names (nome classe -> colore)
_CLASS_COLOR_MAP: Dict[str, Tuple[int, int, int]] = {}


def _build_class_color_map(model) -> Dict[str, Tuple[int, int, int]]:
    """
    Crea una mappatura deterministica: nome_classe -> colore dalla palette fissa.
    L'ordine segue quello di model.names.
    """
    names_list: List[str] = []
    if hasattr(model, "names"):
        # model.names può essere dict {id: name} o list
        if isinstance(model.names, dict):
            for k in sorted(model.names.keys()):
                names_list.append(model.names[k])
        elif isinstance(model.names, list):
            names_list = list(model.names)

    color_map: Dict[str, Tuple[int, int, int]] = {}
    for i, name in enumerate(names_list):
        color_map[name] = _CLASS_PALETTE_6[i % len(_CLASS_PALETTE_6)]
    return color_map


@lru_cache(maxsize=1)
def _load_model():
    """
    Carica il modello YOLO una sola volta per processo Celery.
    Prepara anche la mappa colori per le classi.
    """
    model_path = Path(settings.YOLO_MODEL_PATH)
    if not model_path.exists():
        raise FileNotFoundError(f"Modello YOLO non trovato: {model_path}")

    model = YOLO(str(model_path))

    # opzionale: fuse layers
    try:
        model.fuse()
    except Exception as fuse_err:
        logger.debug("Fuse non eseguito: %s", fuse_err)

    global _CLASS_COLOR_MAP
    _CLASS_COLOR_MAP = _build_class_color_map(model)
    if not _CLASS_COLOR_MAP:
        logger.warning(
            "model.names non trovato o vuoto: uso colore di fallback per tutte le classi."
        )

    # device: preferisci settings.YOLO_DEVICE se presente, altrimenti autodetect
    device = getattr(settings, "YOLO_DEVICE", None)
    if device not in ("cpu", "cuda"):
        device = "cuda" if torch.cuda.is_available() else "cpu"
    return model, device


@shared_task(bind=True)
def process_video_detection(self, video_detection_id: int):
    """
    Processa un video con YOLO, salva le detection e scrive un MP4 annotato.

    Pipeline:
    - Legge il video originale
    - Esegue l'inferenza frame-by-frame
    - Disegna le bbox con colori fissi per classe
    - Scrive un video "raw" (codec semplice) con OpenCV
    - Ricodifica il video in H.264 tramite ffmpeg per compatibilità browser
    - Aggiorna progress, statistiche e stato nel modello VideoDetection
    """
    vd = None
    try:
        vd = VideoDetection.objects.get(id=video_detection_id)
        vd.status = "processing"
        vd.processed_frames = 0
        vd.detections_count = 0
        vd.error_message = ""
        vd.save(
            update_fields=[
                "status",
                "processed_frames",
                "detections_count",
                "error_message",
                "updated_at",
            ]
        )

        model, device = _load_model()

        # --- Input video ---
        in_path = Path(vd.original_video.path)
        cap = cv2.VideoCapture(str(in_path))
        if not cap.isOpened():
            raise RuntimeError(f"Impossibile aprire il video: {in_path}")

        fps = int(cap.get(cv2.CAP_PROP_FPS)) or 25
        ok_probe, probe = cap.read()
        if not ok_probe or probe is None:
            raise RuntimeError("Nessun frame leggibile dal video")
        height, width = probe.shape[:2]
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        vd.total_frames = total_frames
        vd.save(update_fields=["total_frames", "updated_at"])

        # --- Output per utente ---
        user_id_str = str(vd.user_id or "anon")
        base_user_dir = Path(settings.MEDIA_ROOT) / "videos" / user_id_str

        out_dir = base_user_dir / "processed"
        out_dir.mkdir(parents=True, exist_ok=True)

        # file grezzo scritto da OpenCV
        raw_path = out_dir / f"processed_raw_{vd.id}.mp4"
        # file finale ricodificato (H.264)
        final_path = out_dir / f"processed_{vd.id}.mp4"

        # opzionale: directory preview per future anteprime
        preview_dir = base_user_dir / "preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path = preview_dir / f"preview_{vd.id}.jpg"

        # Writer OpenCV (codec semplice; ffmpeg poi ricodifica)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(raw_path), fourcc, fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError(
                f"VideoWriter non inizializzato (path={raw_path}, fps={fps}, size=({width},{height}))"
            )

        # --- Soglie YOLO ---
        conf_thr = float(getattr(settings, "YOLO_CONFIDENCE_THRESHOLD", 0.5))
        iou_thr = float(getattr(settings, "YOLO_IOU_THRESHOLD", 0.45))

        # --- Loop ---
        frame_idx = 0
        det_counter = 0
        batch: List[Detection] = []
        BATCH_SIZE = 512

        # Spessore bbox dinamico in base alla risoluzione
        thickness = max(2, int(round(0.002 * (width + height))))

        while True:
            ok, frame = cap.read()
            if not ok:
                break

            # Inference (usa predict per compatibilità Ultralytics)
            results = model.predict(
                source=frame,
                conf=conf_thr,
                iou=iou_thr,
                verbose=False,
                device=device,
            )

            annotated = frame  # disegniamo direttamente sul frame

            for r in results:
                boxes = getattr(r, "boxes", None)
                if boxes is None:
                    continue

                for b in boxes:
                    # bbox/score/cls
                    x1, y1, x2, y2 = b.xyxy[0].tolist()
                    conf = float(b.conf[0].item())
                    cls_id = int(b.cls[0].item())

                    # class name
                    if hasattr(model, "names"):
                        if isinstance(model.names, dict):
                            class_name = model.names.get(cls_id, str(cls_id))
                        else:
                            class_name = (
                                model.names[cls_id]
                                if cls_id < len(model.names)
                                else str(cls_id)
                            )
                    else:
                        class_name = str(cls_id)

                    # colore per classe
                    color = _CLASS_COLOR_MAP.get(class_name, (0, 255, 0))

                    # salva detection (batch)
                    batch.append(
                        Detection(
                            video_detection=vd,
                            frame_number=frame_idx,
                            class_name=class_name,
                            confidence=conf,
                            bbox_x1=float(x1),
                            bbox_y1=float(y1),
                            bbox_x2=float(x2),
                            bbox_y2=float(y2),
                        )
                    )
                    det_counter += 1

                    # draw
                    cv2.rectangle(
                        annotated,
                        (int(x1), int(y1)),
                        (int(x2), int(y2)),
                        color,
                        thickness,
                    )
                    label = f"{class_name} {conf:.2f}"
                    (tw, th), _ = cv2.getTextSize(
                        label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
                    )
                    cv2.rectangle(
                        annotated,
                        (int(x1), int(y1) - th - 8),
                        (int(x1) + tw + 6, int(y1)),
                        color,
                        -1,
                    )
                    cv2.putText(
                        annotated,
                        label,
                        (int(x1) + 3, int(y1) - 4),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 0, 0),
                        1,
                    )

            # scrivi frame sul video grezzo
            writer.write(annotated)
            frame_idx += 1

            # salva anteprima ogni N frame (per eventuale "realtime" preview)
            if frame_idx % 10 == 0:
                try:
                    cv2.imwrite(str(preview_path), annotated)
                except Exception as preview_err:
                    logger.debug("Impossibile salvare preview: %s", preview_err)

            # bulk insert periodico delle detection
            if len(batch) >= BATCH_SIZE:
                Detection.objects.bulk_create(batch, batch_size=BATCH_SIZE)
                batch.clear()

            # progress (ogni 10 frame)
            if frame_idx % 10 == 0 or (total_frames and frame_idx == total_frames):
                vd.processed_frames = frame_idx
                vd.detections_count = det_counter
                vd.save(
                    update_fields=[
                        "processed_frames",
                        "detections_count",
                        "updated_at",
                    ]
                )
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "current": frame_idx,
                        "total": total_frames,
                        "percentage": int((frame_idx / total_frames) * 100)
                        if total_frames
                        else 0,
                    },
                )

        # chiusure sorgente e writer
        cap.release()
        writer.release()

        # flush batch rimasto
        if batch:
            Detection.objects.bulk_create(batch, batch_size=BATCH_SIZE)

        # --- Ricodifica con ffmpeg in H.264 per compatibilità browser ---
        use_raw_as_fallback = False
        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(raw_path),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-c:a",
                "copy",
                str(final_path),
            ]
            logger.info("Eseguo ffmpeg per ricodifica: %s", " ".join(cmd))
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # se la ricodifica è andata bene, puoi rimuovere il raw
            try:
                raw_path.unlink(missing_ok=True)
            except Exception as del_err:
                logger.debug("Impossibile eliminare il file raw: %s", del_err)

        except FileNotFoundError:
            # ffmpeg non installato -> fallback
            logger.warning(
                "ffmpeg non trovato nel sistema. Uso il file raw come video finale."
            )
            use_raw_as_fallback = True
        except subprocess.CalledProcessError as ff_err:
            logger.error("Errore nella ricodifica ffmpeg: %s", ff_err)
            use_raw_as_fallback = True

        # path relativo per il modello Django
        if use_raw_as_fallback:
            final_rel = f"videos/{user_id_str}/processed/{raw_path.name}"
        else:
            final_rel = f"videos/{user_id_str}/processed/{final_path.name}"

        # finalizza record
        vd.processed_video = final_rel
        vd.status = "completed"
        vd.processed_frames = frame_idx
        vd.detections_count = det_counter
        vd.save(
            update_fields=[
                "processed_video",
                "status",
                "processed_frames",
                "detections_count",
                "updated_at",
            ]
        )

        return {"status": "completed", "detections": det_counter, "frames": frame_idx}

    except Exception as e:
        logger.exception(
            "Errore durante process_video_detection(%s): %s",
            video_detection_id,
            e,
        )
        try:
            if vd is None:
                vd = VideoDetection.objects.get(id=video_detection_id)
            vd.status = "failed"
            vd.error_message = str(e)
            vd.save(update_fields=["status", "error_message", "updated_at"])
        except Exception as inner:
            logger.error(
                "Impossibile salvare lo stato di failure per video %s: %s",
                video_detection_id,
                inner,
            )

        self.update_state(state=states.FAILURE, meta={"error": str(e)})
        raise Ignore()
