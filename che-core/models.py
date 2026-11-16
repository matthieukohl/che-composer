"""WMO-CHE hazardous-event models for the CAP Composer prototype.

Source: WMO-No. 1377 (2025), Table 1 (event attributes), Table 2
(optional attributes), and Annex 1 (WMO Event Types List).

This module is deliberately separate from CAP alert models. It does not
publish warnings, infer causal links, or transmit data to DELTA.

Implementation note: Spatial areas are held as GeoJSON-compatible JSON
in this first prototype. They are NOT yet verified as valid geometry; a
future iteration should validate GIS geometry and authoritative boundary
references, potentially using PostGIS/GeoDjango.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class CHEEvent(models.Model):
    """A single hazardous event, independent of any CAP warning.

    Fields marked as mandatory in WMO-No. 1377 must be complete before
    closure/validation. Some may initially be unknown for ongoing events.
    """

    # Official WMO Event Types List, Annex 1 (2025 edition).
    EVENT_TYPES = [
        ("Air quality", "Air quality"),
        ("Avalanche", "Avalanche"),
        ("Cold", "Cold"),
        ("Drought", "Drought"),
        ("Flooding", "Flooding"),
        ("Fog", "Fog"),
        ("Hail", "Hail"),
        ("Haze", "Haze"),
        ("Heat (terrestrial and marine)", "Heat (terrestrial and marine)"),
        ("Ice flows/icebergs", "Ice flows/icebergs"),
        ("Icing/freezing rain/frost", "Icing/freezing rain/frost"),
        ("Landslide", "Landslide"),
        ("Mid-/high-latitude cyclonic storm", "Mid-/high-latitude cyclonic storm"),
        ("Rain", "Rain"),
        ("Sand/dust", "Sand/dust"),
        ("Smoke", "Smoke"),
        ("Snow", "Snow"),
        ("Space weather", "Space weather"),
        ("Squall", "Squall"),
        ("Storm surge", "Storm surge"),
        ("Subtropical/tropical cyclone", "Subtropical/tropical cyclone"),
        ("Swell/waves", "Swell/waves"),
        ("Thunderstorm/lightning", "Thunderstorm/lightning"),
        ("Tornado", "Tornado"),
        ("Tsunami", "Tsunami"),
        ("UV radiation", "UV radiation"),
        ("Volcanic ash", "Volcanic ash"),
        ("Water quality", "Water quality"),
        ("Wildfire", "Wildfire"),
        ("Wind", "Wind"),
    ]

    class Status(models.TextChoices):
        ONGOING = "ongoing", "Ongoing"
        COMPLETED = "completed", "Completed"
        VALIDATED = "validated", "Validated"

    # WMO-No. 1377, Table 1: mandatory identification and provenance.
    event_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False,
        help_text="Permanent WMO-CHE UUID; must not change on revision.",
    )
    originator = models.CharField(
        max_length=255,
        help_text="Institution and country/territory responsible for this record.",
    )
    record_creation = models.DateTimeField(default=timezone.now, editable=False)

    # Mandatory when record is finalized; event_end can remain unknown while ongoing.
    event_start = models.DateTimeField()
    event_end = models.DateTimeField(null=True, blank=True)
    event_type = models.CharField(max_length=100, choices=EVENT_TYPES)
    hazard_specification = models.CharField(
        max_length=255,
        help_text="Hazard name from the NMHS's nationally controlled hazard list.",
    )
    spatial_area = models.JSONField(
        null=True, blank=True,
        help_text="Provisional GeoJSON geometry or authoritative spatial reference."
                  " Must describe the physical event area, not the impact districts.",
    )

    # WMO-No. 1377, Table 1: other standard attributes.
    event_description = models.TextField(
        blank=True,
        help_text="Physical characteristics and severity; do not include impacts.",
    )
    event_linkage = models.UUIDField(
        null=True, blank=True,
        help_text="UUID of the established higher-order event, if applicable."
                  " May refer to an event in another national/regional catalogue.",
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ONGOING,
    )

    # WMO-No. 1377, Table 2: optional and non-authoritative impact fields.
    impact = models.TextField(
        blank=True,
        help_text="Indicative impacts only; authoritative losses belong to DRR agencies.",
    )
    affected_sectors = models.TextField(blank=True)

    # CHE Composer operational metadata (NOT official WMO-CHE attributes).
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-event_start"]
        verbose_name = "CHE hazardous event"
        verbose_name_plural = "CHE hazardous events"

    def clean(self):
        """Check key scientific and WMO-CHE record consistency rules.

        Forms/admin should call full_clean() before saving. Django's bare
        Model.save() does not automatically invoke these checks.
        """
        super().clean()
        errors = {}
        if self.event_end and self.event_start and self.event_end < self.event_start:
            errors["event_end"] = "Event end cannot precede event start."
        if self.event_linkage and self.event_linkage == self.event_id:
            errors["event_linkage"] = "An event cannot link to itself."
        if self.status in (self.Status.COMPLETED, self.Status.VALIDATED):
            if not self.event_end:
                errors["event_end"] = "End time is needed before completion."
            if not self.spatial_area:
                errors["spatial_area"] = "Spatial area is needed before completion."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.event_type or 'Hazardous event'} — {self.event_id}"
