"""CHE to DELTA HIP classification mapping.

The scientific crosswalk comes from the user-supplied Excel workbook.
DELTA API lookups will resolve installation-specific internal IDs later.
"""

import json
from functools import lru_cache
from pathlib import Path


CROSSWALK_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "che_hip_crosswalk_v1.json"
)


class CHEHIPMappingError(ValueError):
    """A CHE event type has no usable HIP mapping."""


@lru_cache(maxsize=1)
def load_crosswalk():
    with CROSSWALK_PATH.open(encoding="utf-8") as file:
        data = json.load(file)

    mappings = {}

    for row in data["mappings"]:
        che_type = row["che_event_type"].strip()

        if che_type in mappings:
            raise CHEHIPMappingError(
                f"Duplicate CHE mapping: {che_type}"
            )

        if not all(
            row.get(field)
            for field in ("hip_code", "hip_cluster", "hip_hazard")
        ):
            raise CHEHIPMappingError(
                f"Incomplete HIP mapping: {che_type}"
            )

        mappings[che_type] = row

    return mappings


def get_hip_mapping(che_event_type):
    """Return the agreed HIP classification for a CHE event type."""
    mapping = load_crosswalk().get(che_event_type)

    if mapping is None:
        raise CHEHIPMappingError(
            f"No HIP classification for CHE event type: {che_event_type}"
        )

    return mapping
