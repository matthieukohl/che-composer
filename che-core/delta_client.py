"""DELTA API client for resolving HIP classification identifiers."""

import json
import urllib.error
import urllib.parse
import urllib.request

from .delta_security import check_delta_destination_dns
from .delta_transport import secure_delta_request


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent DELTA requests, including API keys, being redirected."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


DELTA_OPENER = urllib.request.build_opener(NoRedirectHandler, urllib.request.ProxyHandler({}))


class DELTAAPIError(Exception):
    """A DELTA API request or classification lookup failed."""


def fetch_hip_records(base_url, api_key, category):
    """Fetch all pages of a DELTA HIP classification endpoint."""
    if category not in {"hazard", "cluster"}:
        raise ValueError("Unsupported HIP category")

    base_url = check_delta_destination_dns(base_url)

    records = []
    page_size = 100

    for page in range(1, 51):
        query = urllib.parse.urlencode({
            "page": page,
            "pageSize": page_size,
        })
        api_path = (
            "/en/api/hips/"
            + category
            + "/list?"
            + query
        )

        try:
            payload = secure_delta_request(base_url, api_path, api_key)
        except Exception as error:
            raise DELTAAPIError(
                f"Unable to retrieve DELTA {category} classifications"
            ) from error

        if not isinstance(payload, dict):
            raise DELTAAPIError(
                f"Invalid DELTA {category} API response"
            )

        data = payload.get("data", {})
        items = data.get("items")
        pagination = data.get("pagination", {})

        if not isinstance(items, list):
            raise DELTAAPIError(
                f"Invalid DELTA {category} API response"
            )

        records.extend(items)
        total = pagination.get("totalItems")

        if not isinstance(total, int):
            raise DELTAAPIError(
                f"Missing DELTA {category} pagination information"
            )

        if len(records) >= total:
            return records

        if not items:
            raise DELTAAPIError(
                f"Incomplete DELTA {category} catalogue"
            )

    raise DELTAAPIError(
        f"DELTA {category} catalogue exceeds the pagination limit"
    )


def resolve_hip_ids(base_url, api_key, hip_code):
    """Resolve a HIP code to destination-specific DELTA identifiers."""
    hazards = fetch_hip_records(base_url, api_key, "hazard")

    matches = [
        hazard for hazard in hazards
        if hazard.get("code") == hip_code
    ]

    if len(matches) != 1:
        raise DELTAAPIError(
            f"Expected one DELTA hazard for HIP code {hip_code}; "
            f"found {len(matches)}"
        )

    hazard = matches[0]
    clusters = fetch_hip_records(base_url, api_key, "cluster")

    cluster = next(
        (
            item for item in clusters
            if item.get("id") == hazard.get("clusterId")
        ),
        None,
    )

    if cluster is None:
        raise DELTAAPIError(
            f"DELTA cluster not found for HIP code {hip_code}"
        )

    if not all((
        hazard.get("id"),
        cluster.get("id"),
        cluster.get("typeId"),
    )):
        raise DELTAAPIError(
            f"Incomplete DELTA identifiers for HIP code {hip_code}"
        )

    return {
        "hipHazardId": hazard["id"],
        "hipClusterId": cluster["id"],
        "hipTypeId": cluster["typeId"],
        "hip_code": hip_code,
        "hip_hazard_name": hazard.get("name", {}).get("en", ""),
        "hip_cluster_name": cluster.get("name", {}).get("en", ""),
    }


def upsert_hazardous_event(base_url, api_key, event_payload):
    """Create or update one DELTA event by its CHE import identifier.

    Approval status is deliberately omitted so DELTA retains control
    of its own validation workflow.
    """
    if not event_payload.get("apiImportId"):
        raise DELTAAPIError("CHE event identifier is missing")

    if "approvalStatus" in event_payload:
        raise DELTAAPIError(
            "CHE transfers must not set DELTA approval status"
        )

    try:
        result = secure_delta_request(
            base_url,
            "/en/api/hazardous-event/upsert",
            api_key,
            payload=[event_payload],
        )
    except Exception as error:
        raise DELTAAPIError(
            "DELTA transfer failed or its response was invalid"
        ) from error

    if not isinstance(result, dict) or result.get("ok") is not True:
        raise DELTAAPIError(
            "DELTA rejected the event transfer"
        )

    records = result.get("res", [])

    if (
        len(records) != 1
        or records[0].get("ok") is not True
        or records[0].get("status") not in {"create", "update"}
        or not records[0].get("id")
    ):
        raise DELTAAPIError(
            "DELTA returned an unexpected transfer result"
        )

    return {
        "status": records[0]["status"],
        "delta_event_id": records[0]["id"],
    }
