"""Restrict CAP and Wagtail page administration in CHE Standalone."""

from django.conf import settings
from django.http import HttpResponseNotFound


class CHEOnlyAdminMiddleware:
    """Deny direct access to CAP administration and page editing."""

    BLOCKED_PREFIXES = (
        "load-boundary/",
        "preview-boundary/",
        "predefinedalertarea_chooser/",
        "reports/aging-pages/",
        "reports/locked/",
        "reports/page-types-usage/",
        "forms/submissions/",
        "newsletter/",
        "workflows/",
        "pages/",
        "page-chooser/",
        "choose-page/",
        "bulk/",
        "api/main/pages/",
        "cap/",
        "import-cap/",
        "modeladmin/cap/",
        "snippets/cap/",
        "snippets/capeditor/",
        "settings/cap/",
        "settings/capeditor/",
        "settings/other-cap-settings/",
        "modeladmin/capeditor/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        admin_path = getattr(
            settings, "ADMIN_URL_PATH", "admin"
        ).strip("/")

        prefix = f"/{admin_path}/"
        path = request.path_info

        if path.startswith(prefix):
            relative_path = path[len(prefix):].lstrip("/")

            if any(
                relative_path.startswith(blocked)
                for blocked in self.BLOCKED_PREFIXES
            ):
                return HttpResponseNotFound(
                    "This feature is unavailable in CHE Standalone."
                )

        return self.get_response(request)
