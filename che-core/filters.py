"""CHE catalogue filters: existing WMO-CHE fields only; no schema changes.

Year is derived from event_start. Originator choices are values actually present
in the catalogue, not guessed countries or new fields.
"""
import django_filters
from wagtail.admin.filters import WagtailFilterSet
from .models import CHEEvent


class CHEEventFilterSet(WagtailFilterSet):
    originator = django_filters.ChoiceFilter(label="Originating institution")
    year = django_filters.ChoiceFilter(method="by_event_year", label="Event year")

    class Meta:
        model = CHEEvent
        fields = ["originator", "year", "event_type", "status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = CHEEvent.objects.all()
        institutions = queryset.order_by("originator").values_list("originator", flat=True).distinct()
        years = queryset.order_by().dates("event_start", "year", order="DESC")
        self.filters["originator"].field.choices = [(s, s) for s in institutions if s]
        self.filters["year"].field.choices = [(str(y.year), str(y.year)) for y in years]

    def by_event_year(self, queryset, name, value):
        return queryset.filter(event_start__year=int(value)) if value else queryset


def filter_options():
    """Options derived only from actual records (not a country registry)."""
    qs = CHEEvent.objects.all()
    return {
        "originators": list(qs.exclude(originator="").order_by("originator").values_list("originator", flat=True).distinct()),
        "years": [d.year for d in qs.dates("event_start", "year", order="DESC")],
        "event_types": [{"value": value, "label": str(label)} for value, label in CHEEvent._meta.get_field("event_type").flatchoices if value],
        "statuses": [{"value": value, "label": str(label)} for value, label in CHEEvent._meta.get_field("status").flatchoices if value],
    }


def filtered_events(params):
    """Apply validated GET filters, using the same CHE fields as Wagtail."""
    from django.db.models import Q
    qs = CHEEvent.objects.all()
    if params.get("originator"):
        qs = qs.filter(originator=params["originator"])
    if params.get("year"):
        try:
            year = int(params["year"])
            if not 1 <= year <= 9999:
                return qs.none()
            qs = qs.filter(event_start__year=year)
        except (TypeError, ValueError):
            return qs.none()
    if params.get("event_type"):
        qs = qs.filter(event_type=params["event_type"])
    if params.get("status"):
        qs = qs.filter(status=params["status"])
    if params.get("q"):
        query = params["q"].strip()[:180]
        if query:
            match = Q(originator__icontains=query) | Q(hazard_specification__icontains=query) | Q(event_description__icontains=query)
            # UUID values can be searched exactly without database-dependent partial UUID matching.
            try:
                from uuid import UUID
                match |= Q(event_id=UUID(query))
            except (ValueError, AttributeError):
                pass
            qs = qs.filter(match)
    return qs


def is_demo_event(event):
    """Use the reserved DEMO description markers; originator names are illustrative."""
    desc = event.event_description or ""
    return "SYNTHETIC TEST EVENT" in desc and "NOT AN OBSERVED HAZARD" in desc
