"""CHE-only navigation for the standalone WMO-RAF edition.

The shared CHE application remains unchanged.
"""

from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.views.generic import IndexView

from capcomposer.che.wagtail_hooks import che_event_viewset


# Keep the standard permission-aware Add button, but remove the
# extra visualization/DELTA header buttons in standalone mode.
che_event_viewset.index_view_class = IndexView


class CHEViewerMenuItem(MenuItem):
    def is_shown(self, request):
        return request.user.has_perm("che.view_cheevent")


class CHEDeltaMenuItem(MenuItem):
    def is_shown(self, request):
        return request.user.has_perm("che.change_cheevent")


@hooks.register("register_admin_menu_item")
def register_che_network_viewer():
    return CHEViewerMenuItem(
        "Network Viewer",
        "/che/relationships/",
        name="che-network-viewer",
        icon_name="link",
        order=352,
    )


@hooks.register("register_admin_menu_item")
def register_che_delta():
    return CHEDeltaMenuItem(
        "Push to DELTA",
        "/che/delta/",
        name="che-delta",
        icon_name="upload",
        order=353,
    )


@hooks.register("construct_main_menu")
def rename_che_global_map(request, menu_items):
    menu_items[:] = [
        item for item in menu_items
        if item.name not in {"explorer", "pages"}
    ]
    # Global Map is already registered by the shared CHE application.
    # Rename it rather than registering a duplicate.
    for item in menu_items:
        if item.name == "che-global-map":
            item.label = "Global Map"
            item.attrs = {}
