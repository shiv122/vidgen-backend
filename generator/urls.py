from django.urls import path

from .views import (
    ElevenLabsVoiceListView,
    JobCreateView,
    JobDownloadView,
    JobStatusView,
    VoiceDetailView,
    VoiceListCreateView,
)

urlpatterns = [
    path("voices/", VoiceListCreateView.as_view(), name="voice-list-create"),
    path("voices/<uuid:id>/", VoiceDetailView.as_view(), name="voice-detail"),
    path(
        "elevenlabs-voices/",
        ElevenLabsVoiceListView.as_view(),
        name="elevenlabs-voices",
    ),
    path("jobs/", JobCreateView.as_view(), name="job-create"),
    path("jobs/<uuid:id>/", JobStatusView.as_view(), name="job-status"),
    path(
        "jobs/<uuid:id>/download/",
        JobDownloadView.as_view(),
        name="job-download",
    ),
]
