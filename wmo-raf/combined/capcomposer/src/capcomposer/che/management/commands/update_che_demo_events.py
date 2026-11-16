"""Refresh the *existing* 2026 CHE demonstration data, without new schema fields.

Updates only originator and spatial_area for the 100 UUIDs made by
``generate_che_demo_events``. The originators are illustrative labels and do
NOT imply the named institutions supplied or endorsed the fictional records.

Run --dry-run first; use --restore before the original generator's --clear-demo
because the latter only deletes rows bearing its original originator string.
"""

import math
import random
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from capcomposer.che.models import CHEEvent
from .generate_che_demo_events import (
    CARIBBEAN, GLOBAL, NAMESPACE, DEMO_ORIGINATOR, demo_uuid
)

# These are ILLUSTRATIVE organization labels ONLY. They are NOT real submissions.
# The organization name is the existing WMO-CHE originator attribute, not a new field.
CARIBBEAN_ORIGINATORS = {
    "Jamaica": "Jamaica Meteorological Service",
    "Haiti": "Haiti National Meteorological Unit",
    "Dominican Republic": "Dominican Republic Meteorological Institute",
    "Cuba": "Cuban Institute of Meteorology",
    "Puerto Rico": "US National Weather Service",
    "Dominica": "Dominica Meteorological Service",
    "Martinique": "Météo-France",
    "Guadeloupe": "Météo-France",
    "Barbados": "Barbados Meteorological Services",
    "Saint Lucia": "Saint Lucia Meteorological Services",
    "Grenada": "Grenada Meteorological Service",
    "Trinidad and Tobago": "Trinidad and Tobago Meteorological Service",
    "Antigua and Barbuda": "Antigua and Barbuda Meteorological Service",
    "Saint Kitts and Nevis": "St Kitts Meteorological Services",
    "Saint Vincent and the Grenadines": "St Vincent and the Grenadines Meteorological Services",
    "Bahamas": "Bahamas Department of Meteorology",
    "Aruba": "Aruba Meteorological Department",
    "Curaçao": "Meteorological Department Curaçao",
    "Cayman Islands": "Cayman Islands National Weather Service",
    "Turks and Caicos": "Turks and Caicos Islands Meteorological Department",
}
GLOBAL_ORIGINATORS = {
    "Kenya": "Kenya Meteorological Department", "Ghana": "Ghana Meteorological Agency",
    "Mozambique": "Mozambique National Institute of Meteorology", "Morocco": "Moroccan Directorate General of Meteorology",
    "Ethiopia": "Ethiopian Meteorological Institute", "Madagascar": "Madagascar Meteorological Service",
    "Senegal": "Senegal National Meteorological Agency", "South Africa": "South African Weather Service",
    "Indonesia": "BMKG", "Philippines": "PAGASA", "Bangladesh": "Bangladesh Meteorological Department",
    "India": "India Meteorological Department", "Japan": "Japan Meteorological Agency",
    "Vietnam": "Viet Nam Meteorological and Hydrological Administration", "Pakistan": "Pakistan Meteorological Department",
    "Thailand": "Thai Meteorological Department", "Nepal": "Department of Hydrology and Meteorology Nepal",
    "Switzerland": "MeteoSwiss", "France": "Météo-France", "Germany": "Deutscher Wetterdienst",
    "Italy": "Italian Meteorological Service", "Spain": "AEMET", "Greece": "Hellenic National Meteorological Service",
    "Norway": "Norwegian Meteorological Institute", "United States": "US National Weather Service",
    "Canada": "Environment and Climate Change Canada", "Mexico": "Servicio Meteorológico Nacional Mexico",
    "Costa Rica": "Instituto Meteorológico Nacional Costa Rica", "Panama": "ETESA Meteorology Panama",
    "Brazil": "INMET", "Colombia": "IDEAM", "Peru": "SENAMHI Peru",
    "Chile": "Dirección Meteorológica de Chile", "Argentina": "Servicio Meteorológico Nacional Argentina",
    "Ecuador": "INAMHI Ecuador", "Australia": "Australian Bureau of Meteorology",
    "New Zealand": "MetService New Zealand", "Fiji": "Fiji Meteorological Service",
    "Vanuatu": "Vanuatu Meteorology and Geo-Hazards Department", "Papua New Guinea": "PNG National Weather Service",
    "Samoa": "Samoa Meteorology Division",
}


def irregular_polygon(lat, lon, slot, regional=False):
    """Deterministic, closed irregular GeoJSON polygon; NOT an observed footprint.

    Variable radii and angles avoid the previous rectangles. The regional cyclone
    uses a broad, nonrectangular envelope; it is NOT a storm track or forecast cone.
    """
    rng = random.Random(180200 + slot)
    n = 26 if regional else 15
    # Scale in degrees. Keep small island geometries reasonably compact.
    horizontal = 8.2 if regional else (0.17 if slot < 50 else 0.30)
    vertical = 5.7 if regional else (0.14 if slot < 50 else 0.23)
    coords = []
    phase = rng.uniform(0, math.tau)
    for j in range(n):
        theta = phase + math.tau * j / n
        radius = rng.uniform(0.78, 1.08)
        # Broad smooth variation makes a geographic-looking silhouette instead of a starburst.
        radius *= 0.94 + 0.08 * math.sin(3 * theta + slot)
        x = lon + horizontal * radius * math.cos(theta)
        y = lat + vertical * radius * math.sin(theta)
        x = max(-179.95, min(179.95, x))
        y = max(-89.95, min(89.95, y))
        coords.append([round(x, 6), round(y, 6)])
    coords.append(coords[0][:])
    return {"type": "Polygon", "coordinates": [coords]}


def plan(slot):
    """Return proposed originator and geometry, leaving all other model fields alone."""
    if slot == 0:
        return "Caribbean regional meteorological service (illustrative)", irregular_polygon(17.8, -70.8, slot, regional=True)
    if slot < 50:
        place, lat, lon = CARIBBEAN[(slot - 1) % len(CARIBBEAN)]
        return CARIBBEAN_ORIGINATORS[place], irregular_polygon(lat, lon, slot)
    _, place, lat, lon = GLOBAL[(slot - 50) % len(GLOBAL)]
    return GLOBAL_ORIGINATORS[place], irregular_polygon(lat, lon, slot)


def valid_demo(record, slot):
    """Protect user records: require reserved UUID AND original demo description."""
    return (record.event_id == demo_uuid(slot)
            and "SYNTHETIC TEST EVENT" in (record.event_description or "")
            and "NOT AN OBSERVED HAZARD" in (record.event_description or ""))


class Command(BaseCommand):
    help = "Update original 100 synthetic CHE events with illustrative originators and irregular polygons (no new fields)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview without writing anything")
        parser.add_argument("--restore", action="store_true", help="Restore original demo originators and rectangular polygons")

    def handle(self, *args, **opts):
        # Snapshot generator's original rectangles, recreating original deterministic
        # per-slot jitter to ensure --restore exactly restores spatial_area.
        from .generate_che_demo_events import polygon
        legacy_rng = random.Random(20261102)
        rectangles = {0: polygon(17.8, -70.8, 16.0, 12.0)}
        for slot in range(1, 50):
            _, lat, lon = CARIBBEAN[(slot - 1) % len(CARIBBEAN)]
            # Reproduce the same draws and ordering as the original generator.
            # Its date RNG calls for some slots interleave with jitter; handle
            # those to retain the exact original shapes.
            if slot > 20:
                legacy_rng.randrange(0, 49)
            jitter_lat = legacy_rng.uniform(-0.08, 0.08)
            jitter_lon = legacy_rng.uniform(-0.08, 0.08)
            rectangles[slot] = polygon(lat + jitter_lat, lon + jitter_lon)
        for slot in range(50, 100):
            _, _, lat, lon = GLOBAL[(slot - 50) % len(GLOBAL)]
            legacy_rng.randrange(0, 55)
            rectangles[slot] = polygon(lat, lon, 0.65, 0.44)

        ids = [demo_uuid(slot) for slot in range(100)]
        records_by_id = {r.event_id: r for r in CHEEvent.objects.filter(event_id__in=ids)}
        updates = []
        missing = []
        for slot in range(100):
            record = records_by_id.get(demo_uuid(slot))
            if record is None:
                missing.append(slot)
                continue
            if not valid_demo(record, slot):
                raise CommandError(f"Safety check failed for slot {slot}; nothing updated.")
            label, shape = (DEMO_ORIGINATOR, rectangles[slot]) if opts["restore"] else plan(slot)
            # Do not overwrite if originator is an unexpected user-edited value.
            allowed_originators = {DEMO_ORIGINATOR, plan(slot)[0]}
            if record.originator not in allowed_originators:
                raise CommandError(f"Originator changed outside demo tool at slot {slot}; nothing updated.")
            if record.originator != label or record.spatial_area != shape:
                record.originator = label
                record.spatial_area = shape
                updates.append(record)

        self.stdout.write(f"Demo UUIDs found: {len(records_by_id)}; missing: {len(missing)}; records to update: {len(updates)}; mode: {'restore' if opts['restore'] else 'refresh'}.")
        if missing:
            self.stdout.write(self.style.WARNING(f"Missing demo slots (not created): {missing}"))
        if opts["dry_run"]:
            self.stdout.write("DRY RUN: no records modified.")
            return
        with transaction.atomic():
            # update_fields intentionally limited to original two attributes;
            # no UUID, linkage, date, status, or description changes.
            CHEEvent.objects.bulk_update(updates, ["originator", "spatial_area"], batch_size=100)
        self.stdout.write(self.style.SUCCESS(f"Updated {len(updates)} synthetic records. All UUIDs and event links preserved."))
        self.stdout.write("Every originator name is an ILLUSTRATIVE TEST LABEL, not an actual submission.")
