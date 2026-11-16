"""Read-only map presentation for CHE records.

For now this endpoint is restricted to authenticated Wagtail administrators with
CHE view permission. It is NOT the future public/global WMO data API.
"""

import json
from django.contrib.auth.decorators import permission_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from wagtail.admin.auth import require_admin_access

from .models import CHEEvent
from .filters import filtered_events, filter_options, is_demo_event


@require_admin_access
@permission_required("che.view_cheevent", raise_exception=True)
def che_global_map(request):
    """Render the global overview; the browser fetches polygons separately."""
    return render(request, "che/global_map.html", {
        "geojson_url": reverse("che_global_map_data"),
        "page_title": "CHE Global Map",
    })


@require_admin_access
@permission_required("che.view_cheevent", raise_exception=True)
def che_global_map_geojson(request):
    """Serve all readable CHE event geometries as a GeoJSON FeatureCollection.

    This prototype deliberately returns all geometry-bearing events. Scaling
    to very large catalogues will require bounding-box filtering / pagination.
    """
    features = []
    invalid_count = 0
    for event in filtered_events(request.GET).iterator():
        geom = event.spatial_area
        if not geom:
            continue
        if isinstance(geom, str):
            try:
                geom = json.loads(geom)
            except (ValueError, TypeError):
                invalid_count += 1
                continue
        # Accept GeoJSON geometry or a Feature containing its geometry.
        if isinstance(geom, dict) and geom.get("type") == "Feature":
            geom = geom.get("geometry")
        if not isinstance(geom, dict) or geom.get("type") not in {"Polygon", "MultiPolygon", "Point", "MultiPoint", "LineString", "MultiLineString"} or not geom.get("coordinates"):
            invalid_count += 1
            continue
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "event_id": str(event.event_id),
                "event_type": str(event.get_event_type_display()) if hasattr(event, "get_event_type_display") else str(event.event_type),
                "event_type_value": str(event.event_type),
                "hazard_specification": event.hazard_specification,
                "status": event.status,
                "originator": event.originator,
                "event_start": event.event_start.isoformat() if event.event_start else None,
                "event_end": event.event_end.isoformat() if event.event_end else None,
                "event_linkage": str(event.event_linkage) if event.event_linkage else None,
                "is_synthetic": is_demo_event(event),
            },
        })
    return JsonResponse({"type": "FeatureCollection", "features": features, "invalid_count": invalid_count, "filters": filter_options()})
