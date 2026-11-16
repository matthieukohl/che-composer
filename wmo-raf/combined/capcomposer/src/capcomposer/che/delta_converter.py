"""Convert WMO-CHE events to DELTA hazardous-event API records."""

import uuid

from .delta_mapping import get_hip_mapping


class DELTAConversionError(ValueError):
    """An event cannot be converted safely for DELTA."""


def convert_che_event(event, hip_ids):
    """Return a DELTA-compatible record without modifying the CHE event."""
    if event.status == "ongoing":
        raise DELTAConversionError(
            "Ongoing CHE events are not eligible for DELTA transfer"
        )

    if not event.event_start:
        raise DELTAConversionError("CHE event is missing its start date")

    if not event.event_end:
        raise DELTAConversionError(
            "CHE event has no end date; DELTA requires an end date"
        )

    mapping = get_hip_mapping(event.event_type)

    if hip_ids.get("hip_code") != mapping["hip_code"]:
        raise DELTAConversionError("Resolved HIP code does not match crosswalk")

    if hip_ids.get("hip_cluster_name", "").strip().casefold() != mapping["hip_cluster"].strip().casefold():
        raise DELTAConversionError(
            "DELTA HIP cluster does not match the CHE crosswalk"
        )

    status_map = {
        "ongoing": "ongoing",
        "completed": "passed",
        "validated": "passed",
    }

    if event.status not in status_map:
        raise DELTAConversionError("Unsupported CHE event status")

    payload = {
        "apiImportId": str(event.event_id),
        "hipHazardId": hip_ids["hipHazardId"],
        "hipClusterId": hip_ids["hipClusterId"],
        "hipTypeId": hip_ids["hipTypeId"],
        "recordOriginator": event.originator,
        "startDate": event.event_start.date().isoformat(),
        "endDate": event.event_end.date().isoformat(),
        "nationalSpecification": event.hazard_specification,
        "description": event.event_description,
        "hazardousEventStatus": status_map[event.status],
    }

    geometry = event.spatial_area

    if geometry:
        if isinstance(geometry, dict) and geometry.get("type") == "Feature":
            geometry = geometry.get("geometry")

        if not isinstance(geometry, dict) or not geometry.get("coordinates"):
            raise DELTAConversionError("Invalid CHE GeoJSON geometry")

        payload["spatialFootprint"] = [{
            "id": str(uuid.uuid4()),
            "title": "CHE Composer event footprint",
            "map_option": "Map coordinates",
            "geojson": {
                "type": "Feature",
                "properties": {
                    "source": "CHE Composer",
                    "che_event_id": str(event.event_id),
                },
                "geometry": geometry,
            },
        }]

    return payload
