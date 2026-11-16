"""Authenticated, read-only CHE event relationship exploration.

Only the existing event_linkage UUID is interpreted; no causal claims are made.
No events are edited, and the global map remains a separate feature.
"""
from django.contrib.auth.decorators import permission_required
from django.http import JsonResponse
from django.shortcuts import render
from wagtail.admin.auth import require_admin_access

from .models import CHEEvent
from .filters import filter_options, is_demo_event


@require_admin_access
@permission_required("che.view_cheevent", raise_exception=True)
def relationship_explorer(request):
    """Standalone interface. User can focus an event using ?event=<UUID>."""
    return render(request, "che/relationships.html")


@require_admin_access
@permission_required("che.view_cheevent", raise_exception=True)
def relationship_data(request):
    """Small catalogue-level read-only dataset for the prototype network.

    Edges are explicit event_linkage values only. A UUID with no matching CHE
    record is returned as an unresolved reference rather than silently omitted.
    Large deployments will require server-side filtering and pagination.
    """
    records = []
    for event in CHEEvent.objects.all().iterator():
        records.append({
            "id": str(event.event_id),
            "event_type": str(event.get_event_type_display()) if hasattr(event, "get_event_type_display") else str(event.event_type),
            "event_type_value": str(event.event_type),
            "hazard_specification": event.hazard_specification,
            "description": event.event_description[:240],
            "status": event.status,
            "originator": event.originator,
            "start": event.event_start.isoformat() if event.event_start else None,
            "parent": str(event.event_linkage) if event.event_linkage else None,
            "is_synthetic": is_demo_event(event),
        })
    return JsonResponse({"events": records, "filters": filter_options()})
