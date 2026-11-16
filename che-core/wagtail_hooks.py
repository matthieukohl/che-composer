"""CHE administration integrated into Wagtail, independent of CAP alerts.

The CHE catalogue keeps its normal Add button. Two additional header buttons
open the existing read-only CHE map and relationship explorer in new tabs.
No changes to the CHE data model, database, or map/graph views are needed.
"""

from django.utils.functional import cached_property
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.viewsets.model import ModelViewSet
from wagtail.admin.views.generic import IndexView
from wagtail.admin.widgets.button import HeaderButton

from .filters import CHEEventFilterSet
from .models import CHEEvent
from .widgets import CHESpatialAreaWidget


class CHEEventIndexView(IndexView):
    """Extend only the CHE catalogue's header, not its editing workflow."""

    @cached_property
    def header_buttons(self):
        # Wagtail supplies the permission-aware Add button. Keep it untouched.
        buttons = list(super().header_buttons)

        # The catalogue also allows users with view permission but no add
        # permission to inspect the visualizations. Both URLs enforce their
        # own authentication and permissions in their existing views.
        if self.request.user.has_perm("che.view_cheevent"):
            external_tab_attrs = {
                "target": "_blank",
                "rel": "noopener noreferrer",
            }
            buttons.extend(
                [
                    HeaderButton(
                        "View Global Map",
                        url="/che/map/",
                        icon_name="site",
                        priority=1100,
                        attrs=external_tab_attrs,
                    ),
                    HeaderButton(
                        "View Relationships",
                        url="/che/relationships/",
                        icon_name="link",
                        priority=1200,
                        attrs=external_tab_attrs,
                    ),
                ]
            )

        # DELTA transfers require CHE editing permission.
        if self.request.user.has_perm("che.change_cheevent"):
            buttons.append(
                HeaderButton(
                    "Push to DELTA",
                    url="/che/delta/",
                    icon_name="upload",
                    priority=1300,
                    attrs={
                        "target": "_blank",
                        "rel": "noopener noreferrer",
                    },
                )
            )

        return buttons


class CHEEventViewSet(ModelViewSet):
    """List and edit CHE records independently of CAP alerts."""

    model = CHEEvent
    index_view_class = CHEEventIndexView
    icon = "doc-full"
    menu_icon = "doc-full"
    menu_label = "CHE Events"
    menu_order = 350
    add_to_admin_menu = True
    list_display = ["event_id", "event_type", "status", "event_start", "originator"]
    ordering = ["-event_start"]
    # Wagtail search uses Django QuerySet lookups, without search-index changes.
    search_fields = ["originator", "event_description", "hazard_specification"]
    search_backend_name = None
    filterset_class = CHEEventFilterSet
    exclude_form_fields = ["record_creation", "last_updated"]
    copy_view_enabled = False
    delete_view_enabled = False
    inspect_view_enabled = True

    def formfield_for_dbfield(self, db_field, **kwargs):
        """Attach the independent CHE drawing widget only to spatial_area."""
        if db_field.name == "spatial_area":
            kwargs["widget"] = CHESpatialAreaWidget()
        return super().formfield_for_dbfield(db_field, **kwargs)


che_event_viewset = CHEEventViewSet("che_events")


@hooks.register("register_admin_viewset")
def register_che_event_viewset():
    """Register CHE's independent list and edit views."""
    return che_event_viewset


class CHEMapMenuItem(MenuItem):
    """Preserve the existing map sidebar shortcut for familiar navigation."""

    def is_shown(self, request):
        return request.user.has_perm("che.view_cheevent")


@hooks.register("register_admin_menu_item")
def register_che_map_menu_item():
    """Keep the original Global Map shortcut, opening in a new tab."""
    return CHEMapMenuItem(
        "View Global Map",
        "/che/map/",
        name="che-global-map",
        icon_name="site",
        order=351,
        attrs={"target": "_blank", "rel": "noopener noreferrer"},
    )


# CHE_LINKAGE_LOOKUP_STEP141: load only an enhancement of the CHE UUID input.
# The JavaScript itself checks that the current form has id_event_linkage.
@hooks.register("insert_global_admin_js")
def che_linkage_lookup_admin_js():
    from django.templatetags.static import static
    from django.utils.html import format_html
    return format_html('<script src="{}" defer></script>', static('che/js/linkage-lookup.js'))


@hooks.register("insert_global_admin_css")
def che_linkage_lookup_admin_css():
    from django.templatetags.static import static
    from django.utils.html import format_html
    return format_html('<link rel="stylesheet" href="{}">', static('che/css/linkage-lookup.css'))

# CHE_DATE_COUNTRY_STEP151: CHE-only UTC calendar/time form enhancement.
# This is additive and leaves the Event Linkage lookup hooks untouched.
@hooks.register("insert_global_admin_js")
def che_utc_datetime_admin_js():
    from django.templatetags.static import static
    from django.utils.html import format_html
    return format_html('<script src="{}" defer></script>', static('che/js/che-utc-datetime.js'))


@hooks.register("insert_global_admin_css")
def che_utc_datetime_admin_css():
    from django.templatetags.static import static
    from django.utils.html import format_html
    return format_html('<link rel="stylesheet" href="{}">', static('che/css/che-utc-datetime.css'))

