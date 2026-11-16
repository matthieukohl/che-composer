"""Create clearly marked, repeatable, geographically distributed SYNTHETIC CHE data.

This command is for UI / interoperability testing only; no event is observed.
It never edits or deletes a user-created event. Its deterministic UUIDs make it
safe to rerun without duplicate records. The current CHEEvent.event_linkage field
permits only one parent UUID per record; this is not a general event graph.
"""

import random
import uuid
from datetime import datetime, timedelta, timezone as datetime_timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from capcomposer.che.models import CHEEvent


DEMO_ORIGINATOR = "SYNTHETIC CHE DEMO (NOT REAL EVENTS)"
NAMESPACE = uuid.UUID("b80141b5-7d64-4984-a39a-d1d97f5a64cd")
BASE_DATE = datetime(2026, 9, 1, 8, 0, tzinfo=datetime_timezone.utc)

# Approximate locations only. Geometry below is an intentionally artificial
# bounding polygon, NOT an observed hazard footprint or administrative border.
CARIBBEAN = [
    ("Jamaica", 18.11, -77.30),
    ("Haiti", 18.98, -72.29),
    ("Dominican Republic", 18.75, -70.16),
    ("Cuba", 22.00, -79.50),
    ("Puerto Rico", 18.22, -66.59),
    ("Dominica", 15.41, -61.35),
    ("Martinique", 14.64, -61.02),
    ("Guadeloupe", 16.27, -61.55),
    ("Barbados", 13.19, -59.54),
    ("Saint Lucia", 13.91, -60.98),
    ("Grenada", 12.11, -61.68),
    ("Trinidad and Tobago", 10.69, -61.22),
    ("Antigua and Barbuda", 17.06, -61.80),
    ("Saint Kitts and Nevis", 17.30, -62.73),
    ("Saint Vincent and the Grenadines", 13.25, -61.20),
    ("Bahamas", 24.25, -76.00),
    ("Aruba", 12.52, -69.97),
    ("Curaçao", 12.17, -68.99),
    ("Cayman Islands", 19.31, -81.25),
    ("Turks and Caicos", 21.69, -71.80),
]

GLOBAL = [
    ("Africa", "Kenya", -0.02, 37.91),
    ("Africa", "Ghana", 7.95, -1.02),
    ("Africa", "Mozambique", -18.66, 35.53),
    ("Africa", "Morocco", 31.79, -7.09),
    ("Africa", "Ethiopia", 9.15, 40.49),
    ("Africa", "Madagascar", -18.77, 46.87),
    ("Africa", "Senegal", 14.50, -14.45),
    ("Africa", "South Africa", -30.56, 22.94),
    ("Asia", "Indonesia", -6.85, 107.61),
    ("Asia", "Philippines", 14.60, 121.00),
    ("Asia", "Bangladesh", 23.68, 90.35),
    ("Asia", "India", 20.59, 78.96),
    ("Asia", "Japan", 36.20, 138.25),
    ("Asia", "Vietnam", 16.05, 108.20),
    ("Asia", "Pakistan", 30.38, 69.35),
    ("Asia", "Thailand", 15.87, 100.99),
    ("Asia", "Nepal", 28.39, 84.12),
    ("Europe", "Switzerland", 46.82, 8.23),
    ("Europe", "France", 46.60, 2.21),
    ("Europe", "Germany", 51.17, 10.45),
    ("Europe", "Italy", 41.87, 12.57),
    ("Europe", "Spain", 40.46, -3.75),
    ("Europe", "Greece", 39.07, 21.82),
    ("Europe", "Norway", 60.47, 8.47),
    ("North America", "United States", 39.83, -98.58),
    ("North America", "Canada", 56.13, -106.35),
    ("North America", "Mexico", 23.63, -102.55),
    ("North America", "Costa Rica", 9.75, -83.75),
    ("North America", "Panama", 8.54, -80.78),
    ("South America", "Brazil", -14.23, -51.92),
    ("South America", "Colombia", 4.57, -74.30),
    ("South America", "Peru", -9.19, -75.02),
    ("South America", "Chile", -33.45, -70.67),
    ("South America", "Argentina", -34.60, -58.38),
    ("South America", "Ecuador", -1.83, -78.18),
    ("Oceania", "Australia", -25.27, 133.78),
    ("Oceania", "New Zealand", -41.28, 174.78),
    ("Oceania", "Fiji", -17.71, 178.07),
    ("Oceania", "Vanuatu", -15.38, 166.96),
    ("Oceania", "Papua New Guinea", -6.32, 143.96),
    ("Oceania", "Samoa", -13.76, -172.10),
]

# Use common event names as preferences; pick only from actual CHE model choices.
HAZARDS = [
    ("Rain", "Heavy rainfall"),
    ("Flooding", "River flooding"),
    ("Drought", "Drought conditions"),
    ("Wind", "Strong winds"),
    ("Heat", "Extreme heat"),
    ("Storm", "Severe storm"),
]


def actual_choice(preferences):
    """Return a DB choice value, preferring exact before partial text matches."""
    field = CHEEvent._meta.get_field("event_type")
    choices = list(field.flatchoices)
    if not choices:
        raise CommandError("CHEEvent.event_type has no choices; inspect the CHE model first.")
    for pref in preferences:
        for value, label in choices:
            if str(value).lower() == pref.lower() or str(label).lower() == pref.lower():
                return value
    for pref in preferences:
        for value, label in choices:
            if pref.lower() in str(value).lower() or pref.lower() in str(label).lower():
                return value
    raise CommandError("No suitable event type found among installed CHE choices: " + ", ".join(str(label) for _, label in choices))


def map_event_type(hazard):
    aliases = {
        "Rain": ["Rain", "Heavy rainfall", "Precipitation"],
        "Flooding": ["Flooding", "Flood", "River flood"],
        "Drought": ["Drought"],
        "Wind": ["Wind", "Strong wind", "Severe wind", "Storm"],
        "Heat": ["Heat", "High temperature", "Extreme temperature", "Temperature"],
        "Storm": ["Storm", "Tropical cyclone", "Wind"],
    }
    try:
        return actual_choice(aliases[hazard])
    except CommandError:
        # If a less common category is unavailable, use Rain with an explicit
        # description of the simulated hazard. Never write an invalid choice.
        return actual_choice(["Rain", "Flood", "Wind"])


def choose_status(i):
    choices = list(CHEEvent._meta.get_field("status").flatchoices)
    desired = ("ongoing", "completed", "validated")[i % 3]
    for value, label in choices:
        if desired in (str(value).lower(), str(label).lower()):
            return value, desired
    if not choices:
        raise CommandError("CHEEvent.status has no choices")
    value = choices[0][0]
    return value, str(choices[0][1]).lower()


def polygon(lat, lon, width=0.50, height=0.38):
    """Small closed approximate rectangle in GeoJSON lon-lat coordinates."""
    left, right = lon - width / 2, lon + width / 2
    bottom, top = lat - height / 2, lat + height / 2
    return {"type": "Polygon", "coordinates": [[[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]]}


def demo_uuid(slot):
    return uuid.uuid5(NAMESPACE, f"che-demo-2026-v1-{slot}")


class Command(BaseCommand):
    help = "Create 50 fictional Caribbean and 50 fictional global CHE events (100 total), safely and repeatably."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show planned totals without inserting anything")
        parser.add_argument("--clear-demo", action="store_true", help="Delete ONLY records with this generator's UUIDs AND originator")

    def handle(self, *args, **options):
        if options["clear_demo"]:
            candidates = [demo_uuid(i) for i in range(100)]
            count, _ = CHEEvent.objects.filter(event_id__in=candidates, originator=DEMO_ORIGINATOR).delete()
            self.stdout.write(self.style.WARNING(f"Deleted {count} synthetic demo records only."))
            return

        if options["dry_run"]:
            self.stdout.write("Would generate 100 clearly marked synthetic events: 50 Caribbean (including one tropical-cyclone parent), 50 global; 20 Caribbean records would link to the parent. No changes made.")
            return

        rng = random.Random(20261102)
        cyclone_uuid = demo_uuid(0)
        records = []

        # A single, fictional regional parent. This is not a real named storm.
        # Find the closest official WMO CHE choice from installed choices.
        try:
            cyclone_type = actual_choice(["Tropical cyclone", "Tropical storm", "Cyclone", "Storm"])
        except CommandError:
            cyclone_type = actual_choice(["Wind", "Rain"])
        parent_status, parent_status_name = choose_status(1)
        records.append(dict(slot=0, place="Caribbean region", hazard="Fictional tropical cyclone", event_type=cyclone_type,
                            start=BASE_DATE + timedelta(days=15), status=parent_status, status_name=parent_status_name,
                            area=polygon(17.8, -70.8, 16.0, 12.0), parent=None))

        # 49 island-level demo events. 20 distinct sites point to the cyclone.
        for i in range(1, 50):
            place, lat, lon = CARIBBEAN[(i - 1) % len(CARIBBEAN)]
            hazard, specification = HAZARDS[(i - 1) % len(HAZARDS)]
            if i <= 20:
                # Cyclone's associated effects; keep type consistent with the physical event.
                hazard, specification = [HAZARDS[0], HAZARDS[1], HAZARDS[3]][i % 3]
            status, status_name = choose_status(i)
            records.append(dict(slot=i, place=place, hazard=specification, event_type=map_event_type(hazard),
                                start=BASE_DATE + timedelta(days=(15 + i % 4) if i <= 20 else rng.randrange(0, 49), hours=i % 18),
                                status=status, status_name=status_name, area=polygon(lat + rng.uniform(-0.08, 0.08), lon + rng.uniform(-0.08, 0.08)),
                                parent=cyclone_uuid if i <= 20 else None))

        # 50 additional events across six continents (not all countries).
        for i in range(50, 100):
            continent, place, lat, lon = GLOBAL[(i - 50) % len(GLOBAL)]
            hazard, specification = HAZARDS[(i - 50) % len(HAZARDS)]
            status, status_name = choose_status(i)
            records.append(dict(slot=i, place=f"{place} ({continent})", hazard=specification,
                                event_type=map_event_type(hazard), start=BASE_DATE + timedelta(days=rng.randrange(0, 55), hours=i % 18),
                                status=status, status_name=status_name, area=polygon(lat, lon, 0.65, 0.44), parent=None))

        created, skipped = 0, 0
        with transaction.atomic():
            for row in records:
                key = demo_uuid(row["slot"])
                if CHEEvent.objects.filter(event_id=key).exists():
                    # Protect existing records even if a UUID collision were to occur.
                    skipped += 1
                    continue
                end = None if row["status_name"] == "ongoing" else row["start"] + timedelta(hours=18 + row["slot"] % 72)
                CHEEvent.objects.create(
                    event_id=key,
                    originator=DEMO_ORIGINATOR,
                    event_start=row["start"],
                    event_end=end,
                    event_type=row["event_type"],
                    hazard_specification=row["hazard"],
                    spatial_area=row["area"],
                    event_description=(f"SYNTHETIC TEST EVENT — NOT AN OBSERVED HAZARD. "
                                       f"Illustrative {row['hazard'].lower()} in {row['place']}. "
                                       f"Generated for CHE Composer search, map and link demonstrations. "
                                       f"The polygon is approximate, not an actual event footprint."),
                    event_linkage=row["parent"],
                    status=row["status"],
                    impact="",
                    affected_sectors="",
                )
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Synthetic CHE events created: {created}; previously present/skipped: {skipped}; total planned: 100."))
        self.stdout.write(f"Synthetic regional cyclone UUID: {cyclone_uuid}")
        self.stdout.write("20 island-level records link to the cyclone via event_linkage. All events are fictional.")
