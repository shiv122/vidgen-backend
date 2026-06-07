from django.conf import settings
from rest_framework import serializers

from .models import VideoJob, Voice


class VoiceCreateSerializer(serializers.ModelSerializer):
    """Validates the multipart upload that creates (clones) a new voice."""

    class Meta:
        model = Voice
        fields = ["name", "sample", "language", "accent"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name cannot be empty.")
        return value

    def validate_sample(self, f):
        max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
        if f.size > max_bytes:
            raise serializers.ValidationError(
                f"File exceeds the {settings.MAX_UPLOAD_MB}MB limit."
            )
        if not f.content_type.startswith("audio/"):
            raise serializers.ValidationError("Voice sample must be an audio file.")
        return f


class VoiceSerializer(serializers.ModelSerializer):
    """Voice payload returned to the frontend (list/detail/polling)."""

    class Meta:
        model = Voice
        fields = [
            "id",
            "name",
            "language",
            "accent",
            "voice_id",
            "status",
            "error",
            "created_at",
        ]


class JobCreateSerializer(serializers.ModelSerializer):
    """Validates a new video generation request (voice id + image + text)."""

    # Background video is required: the output is always the talking-head
    # composited as a circular facecam over this clip.
    background_video = serializers.FileField(required=True)
    # Sent as a JSON string in multipart form data; parse to a list here.
    overlay_keyframes = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = VideoJob
        fields = [
            "voice_id",
            "voice_name",
            "image",
            "text",
            "resolution",
            "background_video",
            "position",
            "overlay_x",
            "overlay_y",
            "overlay_diameter",
            "overlay_border",
            "overlay_border_color",
            "overlay_keyframes",
        ]

    def validate_background_video(self, f):
        if not f:
            return f
        max_bytes = settings.MAX_VIDEO_MB * 1024 * 1024
        if f.size > max_bytes:
            raise serializers.ValidationError(
                f"Video exceeds the {settings.MAX_VIDEO_MB}MB limit."
            )
        if not f.content_type.startswith("video/"):
            raise serializers.ValidationError("Background must be a video file.")
        return f

    def validate_voice_id(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A voice must be selected.")
        return value

    def validate_text(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Text cannot be empty.")
        if len(value) > settings.MAX_TEXT_LEN:
            raise serializers.ValidationError(
                f"Text exceeds the {settings.MAX_TEXT_LEN} character limit."
            )
        return value

    def validate_image(self, f):
        max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
        if f.size > max_bytes:
            raise serializers.ValidationError(
                f"File exceeds the {settings.MAX_UPLOAD_MB}MB limit."
            )
        # D-ID requires a face image of at least 100x100 px.
        from PIL import Image

        try:
            with Image.open(f) as img:
                width, height = img.size
        except Exception:
            raise serializers.ValidationError("Could not read the image file.")
        finally:
            f.seek(0)
        min_dim = settings.MIN_IMAGE_DIM
        if width < min_dim or height < min_dim:
            raise serializers.ValidationError(
                f"Image is too small ({width}x{height}). Use at least "
                f"{min_dim}x{min_dim} pixels."
            )
        return f

    def validate_resolution(self, value):
        if value and value not in (360, 480, 720):
            raise serializers.ValidationError("Resolution must be 360, 480, or 720.")
        return value or settings.DEFAULT_RESOLUTION

    def validate_overlay_keyframes(self, value):
        if not value:
            return None
        import json

        try:
            data = json.loads(value)
        except ValueError:
            raise serializers.ValidationError("Invalid keyframes JSON.")
        if not isinstance(data, list) or not data:
            return None
        cleaned = []
        for k in data:
            try:
                cleaned.append(
                    {"t": float(k["t"]), "x": int(k["x"]), "y": int(k["y"])}
                )
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError("Malformed keyframe entry.")
        return cleaned


class JobStatusSerializer(serializers.ModelSerializer):
    """The polling payload returned to the frontend."""

    class Meta:
        model = VideoJob
        fields = [
            "id",
            "voice_id",
            "voice_name",
            "status",
            "resolution",
            "result_url",
            "error",
            "created_at",
        ]


class ElevenVoiceSerializer(serializers.Serializer):
    """A voice from the ElevenLabs account library."""

    voice_id = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField(allow_blank=True)
    preview_url = serializers.CharField(allow_blank=True)
