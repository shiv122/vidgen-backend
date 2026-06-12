"""Project-level views: a root health/index endpoint and JSON error handlers.

This is a JSON API backend, so the error handlers return JSON instead of
Django's default HTML error pages. Custom handlers only take effect when
DEBUG=False.
"""

from django.http import JsonResponse


def index(request):
    """Root endpoint — confirms the API is up (also used for health checks)."""
    return JsonResponse({"status": "ok", "service": "vidgen-backend"})


def health(request):
    """Dedicated health check endpoint."""
    return JsonResponse({"status": "ok", "service": "vidgen-backend"})


def handler404(request, exception):
    return JsonResponse(
        {"error": "not_found", "detail": "The requested resource was not found."},
        status=404,
    )


def handler500(request):
    return JsonResponse(
        {"error": "server_error", "detail": "An internal server error occurred."},
        status=500,
    )
