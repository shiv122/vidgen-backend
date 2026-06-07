import uuid

from django.db import models


def voice_sample_path(instance, filename):
    return f"voices/{instance.id}/sample_{filename}"


def job_image_path(instance, filename):
    return f"jobs/{instance.id}/image_{filename}"


def job_audio_path(instance, filename):
    return f"jobs/{instance.id}/audio_{filename}"


def job_bg_video_path(instance, filename):
    return f"jobs/{instance.id}/bg_{filename}"


def job_composite_path(instance, filename):
    return f"jobs/{instance.id}/composite_{filename}"


class Voice(models.Model):
    """A cloned voice: an audio sample turned into an ElevenLabs voice_id."""

    class Status(models.TextChoices):
        CLONING = "cloning", "Cloning voice"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    language = models.CharField(max_length=60, blank=True, default="")
    accent = models.CharField(max_length=60, blank=True, default="")
    sample = models.FileField(upload_to=voice_sample_path)
    voice_id = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.CLONING
    )
    error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Voice({self.name}, {self.status})"

    def set_status(self, status):
        self.status = status
        self.save(update_fields=["status", "updated_at"])


class VideoJob(models.Model):
    """Generate a talking video from a cloned voice + an image + text."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SYNTHESIZING = "synthesizing", "Synthesizing speech"
        ANIMATING = "animating", "Animating"
        PROCESSING = "processing", "Finalizing video"
        COMPOSITING = "compositing", "Compositing overlay"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    class Position(models.TextChoices):
        BOTTOM_LEFT = "bottom-left", "Bottom left"
        BOTTOM_CENTER = "bottom-center", "Bottom center"
        BOTTOM_RIGHT = "bottom-right", "Bottom right"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # ElevenLabs voice id (from a cloned voice or the account's voice library).
    voice_id = models.CharField(max_length=128)
    voice_name = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    image = models.ImageField(upload_to=job_image_path)
    text = models.TextField()
    resolution = models.PositiveIntegerField(default=480)

    # Optional background video: the talking head is overlaid as a circular
    # "facecam" bubble on top of it (streamer style).
    background_video = models.FileField(
        upload_to=job_bg_video_path, blank=True, null=True
    )
    position = models.CharField(
        max_length=20, choices=Position.choices, default=Position.BOTTOM_LEFT
    )
    # Optional custom placement (pixels in the background video's own space):
    # top-left x/y and circle diameter. When set, these override `position`.
    overlay_x = models.PositiveIntegerField(blank=True, null=True)
    overlay_y = models.PositiveIntegerField(blank=True, null=True)
    overlay_diameter = models.PositiveIntegerField(blank=True, null=True)
    # Ring around the circular cutout (per-job overrides of the defaults).
    overlay_border = models.PositiveIntegerField(blank=True, null=True)
    overlay_border_color = models.CharField(max_length=9, blank=True, default="")
    # Animated placement: list of {t, x, y} (seconds + top-left px in bg space).
    # With 2+ points the facecam moves between them over time; 1 point is static.
    overlay_keyframes = models.JSONField(blank=True, null=True)

    audio = models.FileField(upload_to=job_audio_path, blank=True, null=True)
    did_talk_id = models.CharField(max_length=128, blank=True, default="")
    composite = models.FileField(
        upload_to=job_composite_path, blank=True, null=True
    )
    result_url = models.URLField(max_length=1024, blank=True, default="")
    error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"VideoJob({self.id}, {self.status})"

    def set_status(self, status):
        self.status = status
        self.save(update_fields=["status", "updated_at"])
