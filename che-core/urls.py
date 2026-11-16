"""CHE-only website routes. Each view enforces its own access permissions.

The two existing global-map routes are preserved unchanged.
"""
from django.urls import path
from . import views
from . import relationship_views
from . import linkage_lookup
from . import delta_views

urlpatterns = [
    path("delta/", delta_views.delta_push_page, name="che_delta_push"),
    path("delta/test-connection/", delta_views.delta_test_connection, name="che_delta_test_connection"),
    path("delta/push/", delta_views.delta_push_selected, name="che_delta_push_selected"),
    path("linkage-lookup/", linkage_lookup.linkage_lookup, name="che_linkage_lookup"),
    path("map/", views.che_global_map, name="che_global_map"),
    path("map/data/", views.che_global_map_geojson, name="che_global_map_data"),
    path("relationships/", relationship_views.relationship_explorer, name="che_relationships"),
    path("relationships/data/", relationship_views.relationship_data, name="che_relationships_data"),
]
