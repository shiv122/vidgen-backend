import threading

import requests
from django.http import Http404, StreamingHttpResponse
from rest_framework import status
from rest_framework.generics import RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import pipeline
from .models import VideoJob, Voice
from .serializers import (
    JobCreateSerializer,
    JobStatusSerializer,
    LibraryVoiceSerializer,
    VoiceCreateSerializer,
    VoiceSerializer,
)
from .services import elevenlabs


def _spawn(target, *args):
    threading.Thread(target=target, args=args, daemon=True).start()


class LibraryVoiceListView(APIView):
    """GET /api/library-voices/ — list available voices from the voice library."""

    def get(self, request):
        try:
            voices = elevenlabs.list_voices()
        except elevenlabs.ElevenLabsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(LibraryVoiceSerializer(voices, many=True).data)


class VoiceListCreateView(APIView):
    """GET /api/voices/ — list voices. POST — clone a new voice from audio."""

    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        voices = Voice.objects.all()
        status_filter = request.query_params.get("status")
        if status_filter:
            voices = voices.filter(status=status_filter)
        return Response(VoiceSerializer(voices, many=True).data)

    def post(self, request):
        serializer = VoiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        voice = serializer.save()
        _spawn(pipeline.process_voice, voice.id)
        return Response(VoiceSerializer(voice).data, status=status.HTTP_202_ACCEPTED)


class VoiceDetailView(RetrieveAPIView):
    """GET /api/voices/{id}/ — poll a voice's cloning status."""

    queryset = Voice.objects.all()
    serializer_class = VoiceSerializer
    lookup_field = "id"


class JobCreateView(APIView):
    """POST /api/jobs/ — start a new talking-head video job."""

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = JobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = serializer.save()
        _spawn(pipeline.process_job, job.id)
        return Response(
            JobStatusSerializer(job).data, status=status.HTTP_202_ACCEPTED
        )


class JobStatusView(RetrieveAPIView):
    """GET /api/jobs/{id}/ — poll a job's status and result."""

    queryset = VideoJob.objects.all()
    serializer_class = JobStatusSerializer
    lookup_field = "id"


class JobDownloadView(APIView):
    """GET /api/jobs/{id}/download/ — stream the result as a file download.

    Proxies the (cross-origin) result URL and sets a Content-Disposition
    attachment header so the browser downloads instead of opening it.
    """

    def get(self, request, id):
        try:
            job = VideoJob.objects.get(pk=id)
        except VideoJob.DoesNotExist:
            raise Http404
        if not job.result_url:
            raise Http404("Video not ready")
        upstream = requests.get(job.result_url, stream=True, timeout=60)
        if not upstream.ok:
            raise Http404("Video unavailable")
        resp = StreamingHttpResponse(
            upstream.iter_content(chunk_size=65536),
            content_type=upstream.headers.get("Content-Type", "video/mp4"),
        )
        resp["Content-Disposition"] = f'attachment; filename="vidgen-{job.id}.mp4"'
        return resp
