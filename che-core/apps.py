from django.apps import AppConfig


class CheConfig(AppConfig):
    """Configuration for the WMO-CHE event catalogue module."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "capcomposer.che"
    verbose_name = "CHE Hazardous Events"
