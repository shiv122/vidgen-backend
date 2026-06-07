"""Background orchestration for voice cloning and video generation.

Kept as plain functions so they can run in a `threading.Thread` today and be
moved to Celery tasks later with no logic change.
"""

import logging
import os
import tempfile
import time

import requests
from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.db import DatabaseError

from .models import Voice, VideoJob
from .services import compositor, did, elevenlabs

logger = logging.getLogger(__name__)


class _RowGone(Exception):
    """Raised internally when the row was deleted while the job was running."""


def _save(obj, fields):
    """Save the given update_fields, tolerating the row being deleted mid-run.

    A background job may outlive its DB row (e.g. the user deletes it). Saving
    with update_fields on a missing row raises DatabaseError — and a plain
    save() would re-INSERT it. We detect that and stop quietly instead.
    """
    try:
        obj.save(update_fields=fields)
    except DatabaseError:
        logger.warning(
            "pipeline: %s %s was deleted mid-processing; stopping",
            type(obj).__name__,
            obj.pk,
        )
        raise _RowGone from None


def process_voice(voice_id):
    """Clone a voice from its uploaded audio sample (ElevenLabs)."""
    try:
        voice = Voice.objects.get(pk=voice_id)
    except Voice.DoesNotExist:
        logger.error("process_voice: voice %s not found", voice_id)
        return

    try:
        voice.sample.open("rb")
        try:
            sample_bytes = voice.sample.read()
        finally:
            voice.sample.close()

        eleven_voice_id = elevenlabs.clone_voice(
            name=voice.name,
            sample_bytes=sample_bytes,
            filename=voice.sample.name.rsplit("/", 1)[-1],
            language=voice.language,
            accent=voice.accent,
        )
        voice.voice_id = eleven_voice_id
        voice.status = Voice.Status.READY
        _save(voice, ["voice_id", "status", "updated_at"])
        logger.info("process_voice: voice %s ready", voice_id)
    except _RowGone:
        return
    except Exception as exc:  # noqa: BLE001 - record any failure for the UI
        logger.exception("process_voice: voice %s failed", voice_id)
        _fail(voice, exc)


def process_job(job_id):
    """Synthesize cloned-voice audio, then render the talking video with D-ID."""
    try:
        job = VideoJob.objects.get(pk=job_id)
    except VideoJob.DoesNotExist:
        logger.error("process_job: job %s not found", job_id)
        return

    try:
        # 1. Synthesize the text into speech in the chosen voice.
        job.status = VideoJob.Status.SYNTHESIZING
        _save(job, ["status", "updated_at"])
        audio_bytes = elevenlabs.tts(job.voice_id, job.text)
        job.audio.save(f"{job.id}.mp3", ContentFile(audio_bytes), save=False)
        _save(job, ["audio", "updated_at"])

        # 2. Start the D-ID talk: lip-sync the image to the generated audio.
        job.status = VideoJob.Status.ANIMATING
        _save(job, ["status", "updated_at"])
        talk_id = did.create_talk(
            source_url=job.image.url,
            audio_url=job.audio.url,
            resolution=job.resolution,
        )
        job.did_talk_id = talk_id
        _save(job, ["did_talk_id", "updated_at"])

        # 3. Poll D-ID until the talking-head video is ready.
        job.status = VideoJob.Status.PROCESSING
        _save(job, ["status", "updated_at"])
        talk_url = _poll_talk(talk_id)

        # 4. If a background video was provided, overlay the talking head as a
        #    circular facecam; otherwise the talking head is the final result.
        if job.background_video:
            job.status = VideoJob.Status.COMPOSITING
            _save(job, ["status", "updated_at"])
            _composite(job, talk_url)
        else:
            job.result_url = talk_url

        job.status = VideoJob.Status.DONE
        _save(job, ["result_url", "status", "updated_at"])
        logger.info("process_job: job %s done", job_id)
    except _RowGone:
        return
    except Exception as exc:  # noqa: BLE001 - record any failure for the UI
        logger.exception("process_job: job %s failed", job_id)
        _fail(job, exc)


def _fail(obj, exc):
    """Record a failure on the object, tolerating it having been deleted."""
    obj.error = str(exc)
    obj.status = obj.Status.FAILED
    try:
        _save(obj, ["error", "status", "updated_at"])
    except _RowGone:
        pass


def _composite(job, talk_url):
    """Overlay the D-ID talking head as a circular facecam on the bg video.

    Downloads the D-ID result and reads the background from storage into temp
    files (S3 storage has no local path), runs ffmpeg, then uploads the result.
    Sets job.composite and job.result_url.
    """
    tmpdir = tempfile.mkdtemp(prefix="vidgen-")
    bg_path = os.path.join(tmpdir, "bg.mp4")
    face_path = os.path.join(tmpdir, "face.mp4")
    out_path = os.path.join(tmpdir, "out.mp4")
    try:
        # Background video from storage.
        job.background_video.open("rb")
        try:
            with open(bg_path, "wb") as fh:
                for chunk in job.background_video.chunks():
                    fh.write(chunk)
        finally:
            job.background_video.close()

        # D-ID talking head from its result URL.
        resp = requests.get(talk_url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(face_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                fh.write(chunk)

        compositor.overlay_circle(
            bg_path,
            face_path,
            out_path,
            position=job.position,
            x=job.overlay_x,
            y=job.overlay_y,
            diameter=job.overlay_diameter,
            border=job.overlay_border,
            border_color=job.overlay_border_color,
            keyframes=job.overlay_keyframes,
        )

        with open(out_path, "rb") as fh:
            job.composite.save(f"{job.id}.mp4", File(fh), save=False)
        job.result_url = job.composite.url
    finally:
        for p in (bg_path, face_path, out_path):
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass


def _poll_talk(talk_id):
    """Poll a D-ID talk until done or timeout. Returns the result_url."""
    deadline = time.monotonic() + settings.VIDEO_POLL_TIMEOUT
    while time.monotonic() < deadline:
        state = did.get_talk(talk_id)
        status = state["status"]
        if status == "done":
            if not state["result_url"]:
                raise did.DIDError("talk done but no result_url returned")
            return state["result_url"]
        if status in ("error", "rejected"):
            raise did.DIDError(f"D-ID render {status}: {state.get('error')}")
        time.sleep(settings.VIDEO_POLL_INTERVAL)
    raise did.DIDError("timed out waiting for D-ID render")
