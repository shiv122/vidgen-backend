from django.contrib import admin

from .models import VideoJob, Voice


@admin.register(Voice)
class VoiceAdmin(admin.ModelAdmin):
    list_display = ("name", "id", "status", "voice_id", "created_at")
    list_filter = ("status",)
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(VideoJob)
class VideoJobAdmin(admin.ModelAdmin):
    list_display = ("id", "voice_name", "voice_id", "status", "resolution", "created_at")
    list_filter = ("status", "resolution")
    readonly_fields = ("id", "created_at", "updated_at")
