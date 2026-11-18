"""Choose CAP Composer branding based on installed applications."""

from django.apps import apps


def composer_branding(request):
    """Display combined branding only when CHE Composer is installed."""
    return {
        "che_composer_installed": apps.is_installed("capcomposer.che"),
    }
