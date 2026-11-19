"""Website routes for CHE Standalone.

CAP public feeds, alert routes and CAP page serving are not exposed.
The underlying CAP models remain installed temporarily for compatibility.
"""

from django.conf import settings
from django.urls import include, path
from django.views.generic import RedirectView
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

admin_path = getattr(settings, "ADMIN_URL_PATH", "admin").strip("/")

urlpatterns = [
    path(
        "",
        RedirectView.as_view(
            url=f"/{admin_path}/",
            permanent=False,
        ),
        name="che_standalone_home",
    ),
    path("che/", include("capcomposer.che.urls")),
    path("documents/", include(wagtaildocs_urls)),
    path(f"{admin_path}/", include(wagtailadmin_urls)),
]
