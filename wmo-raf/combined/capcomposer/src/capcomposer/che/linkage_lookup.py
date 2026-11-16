"""Read-only lookup of CHE higher-order events for the edit form.

The WMO-CHE event_linkage attribute remains an ordinary UUID. This endpoint
provides human-readable lookup results without changing the data model.
"""
from django.contrib.auth.decorators import permission_required
from django.db.models import Q
from django.http import JsonResponse
from wagtail.admin.auth import require_admin_access
from .models import CHEEvent


@require_admin_access
@permission_required('che.view_cheevent', raise_exception=True)
def linkage_lookup(request):
    """Return matching local CHE events; never modify a CHE record."""
    query = request.GET.get('q', '').strip()[:120]
    exclude = request.GET.get('exclude', '').strip()
    qs = CHEEvent.objects.all()
    if exclude:
        # Avoid UUID parsing errors from a malformed request parameter.
        import uuid
        try:
            qs = qs.exclude(event_id=uuid.UUID(exclude))
        except (ValueError, AttributeError):
            pass
    if query:
        terms = [query]
        matches = Q()
        for term in terms:
            matches |= (Q(event_type__icontains=term) |
                        Q(hazard_specification__icontains=term) |
                        Q(originator__icontains=term) |
                        Q(event_description__icontains=term))
        # UUID comparison is exact because database UUIDField cannot perform
        # a reliable substring match across backends.
        import uuid
        try:
            matches |= Q(event_id=uuid.UUID(query))
        except ValueError:
            pass
        # Allow searching by year, e.g. 2025, using event_start.
        if len(query) == 4 and query.isdigit():
            matches |= Q(event_start__year=int(query))
        qs = qs.filter(matches)
    qs = qs.order_by('-event_start', 'event_id')[:30]
    results = [
        {
            'uuid': str(event.event_id),
            'event_type': event.event_type,
            'hazard': event.hazard_specification,
            'originator': event.originator,
            'start': event.event_start.date().isoformat() if event.event_start else '',
            'status': event.get_status_display(),
        }
        for event in qs
    ]
    return JsonResponse({'results': results, 'limit': 30})
