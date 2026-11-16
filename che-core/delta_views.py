"""User interface for transferring CHE events to DELTA Resilience.

The initial page is read-only. API-key handling and transfer operations
will be added after server-side security checks are implemented.
"""

from django.contrib.auth.decorators import permission_required
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from wagtail.admin.auth import require_admin_access

from .models import CHEEvent
from .delta_mapping import get_hip_mapping, CHEHIPMappingError


@require_GET
@require_admin_access
@permission_required("che.view_cheevent", raise_exception=True)
@permission_required("che.change_cheevent", raise_exception=True)
def delta_push_page(request):
    """Display the protected CHE-to-DELTA transfer interface."""
    events = []
    for event in CHEEvent.objects.all().order_by("-event_start"):
        try:
            mapping = get_hip_mapping(event.event_type)
            hip_code = mapping["hip_code"]
            hip_hazard = mapping["hip_hazard"]
        except CHEHIPMappingError:
            hip_code = ""
            hip_hazard = "Mapping unavailable"

        events.append({
            "uuid": str(event.event_id),
            "event_type": event.event_type,
            "originator": event.originator,
            "start_date": event.event_start,
            "status": event.status,
            "transfer_eligible": (
                event.status in ("completed", "validated")
                and bool(event.event_start)
                and bool(event.event_end)
                and bool(hip_code)
            ),
            "hip_code": hip_code,
            "hip_hazard": hip_hazard,
        })

    event_types = sorted({event["event_type"] for event in events})

    return render(request, "che/delta_push.html", {
        "events": events,
        "event_types": event_types,
    })


@require_POST
@require_admin_access
@permission_required("che.view_cheevent", raise_exception=True)
@permission_required("che.change_cheevent", raise_exception=True)
def delta_test_connection(request):
    """Check DELTA credentials without transferring CHE events."""
    from .delta_transport import secure_delta_request

    base_url = request.POST.get("delta_url", "").strip()
    api_key = request.POST.get("api_key", "")

    if not base_url or not api_key:
        return JsonResponse(
            {"ok": False, "message": "Enter the DELTA website URL and API key."},
            status=400,
        )

    try:
        result = secure_delta_request(
            base_url,
            "/en/api/hips/hazard/list?page=1&pageSize=1",
            api_key,
        )
        if not isinstance(result.get("data", {}).get("items"), list):
            raise ValueError("Unexpected DELTA API response")
    except Exception:
        return JsonResponse(
            {
                "ok": False,
                "message": "Connection failed. Check the DELTA URL, API key, and server accessibility.",
            },
            status=400,
        )

    return JsonResponse({
        "ok": True,
        "message": "Connection successful. DELTA API access verified.",
    })


@require_POST
@require_admin_access
@permission_required("che.view_cheevent", raise_exception=True)
@permission_required("che.change_cheevent", raise_exception=True)
def delta_push_selected(request):
    """Transfer selected CHE events individually to the chosen DELTA."""
    import uuid

    from .delta_client import resolve_hip_ids, upsert_hazardous_event
    from .delta_converter import convert_che_event, DELTAConversionError
    from .delta_security import DELTADestinationError, validate_delta_url

    selected = request.POST.getlist("event_ids")
    base_url = request.POST.get("delta_url", "").strip()
    api_key = request.POST.get("api_key", "")

    if not selected or len(selected) > 25 or len(set(selected)) != len(selected):
        return JsonResponse({
            "ok": False,
            "message": "Select between 1 and 25 different CHE events.",
        }, status=400)

    try:
        selected = [str(uuid.UUID(value)) for value in selected]
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({
            "ok": False,
            "message": "The event selection contains an invalid identifier.",
        }, status=400)

    if not api_key:
        return JsonResponse({
            "ok": False,
            "message": "Enter your DELTA API key.",
        }, status=400)

    try:
        base_url = validate_delta_url(base_url)
    except DELTADestinationError:
        return JsonResponse({
            "ok": False,
            "message": "Enter a permitted DELTA website URL.",
        }, status=400)

    results = []

    for event_uuid in selected:
        try:
            event = CHEEvent.objects.get(event_id=event_uuid)
            mapping = get_hip_mapping(event.event_type)
            hip_ids = resolve_hip_ids(
                base_url, api_key, mapping["hip_code"]
            )
            payload = convert_che_event(event, hip_ids)
            transferred = upsert_hazardous_event(
                base_url, api_key, payload
            )

            results.append({
                "uuid": event_uuid,
                "status": (
                    "Created"
                    if transferred["status"] == "create"
                    else "Updated"
                ),
                "delta_event_id": str(transferred["delta_event_id"]),
            })

        except CHEEvent.DoesNotExist:
            results.append({
                "uuid": event_uuid,
                "status": "Failed",
                "message": "CHE event not found.",
            })
        except DELTAConversionError as error:
            results.append({
                "uuid": event_uuid,
                "status": "Failed",
                "message": str(error),
            })
        except Exception:
            results.append({
                "uuid": event_uuid,
                "status": "Failed",
                "message": "HIP mapping, connection, or DELTA transfer failed.",
            })

    successful = sum(
        result["status"] in ("Created", "Updated")
        for result in results
    )

    return JsonResponse({
        "ok": successful == len(results),
        "message": (
            f"{successful} of {len(results)} events transferred successfully."
        ),
        "results": results,
    })
