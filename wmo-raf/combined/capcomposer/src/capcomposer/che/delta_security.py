"""Initial destination validation for the CHE to DELTA connector."""

import ipaddress
from urllib.parse import urlsplit


class DELTADestinationError(ValueError):
    """An invalid or unsupported DELTA destination."""


def validate_delta_url(value):
    """Validate a DELTA website URL before connecting."""
    if not isinstance(value, str) or not value.strip():
        raise DELTADestinationError("Enter the DELTA website URL.")

    value = value.strip()

    if len(value) > 2048:
        raise DELTADestinationError("The DELTA website URL is too long.")

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise DELTADestinationError("Enter a valid DELTA website URL.") from None

    if parsed.username or parsed.password:
        raise DELTADestinationError(
            "The DELTA URL must not contain login credentials."
        )

    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise DELTADestinationError(
            "Enter the website address without an API path."
        )

    hostname = (parsed.hostname or "").lower()

    # Explicit exception for our local Docker development environment.
    if parsed.scheme == "http" and hostname == "host.docker.internal" and port == 3000:
        return "http://host.docker.internal:3000"

    if parsed.scheme != "https":
        raise DELTADestinationError(
            "DELTA requires HTTPS except for the local test installation."
        )

    if port not in (None, 443):
        raise DELTADestinationError(
            "Use the standard HTTPS port."
        )

    if not hostname or hostname == "localhost" or hostname.endswith(".localhost"):
        raise DELTADestinationError("This destination is not permitted.")

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise DELTADestinationError(
            "Enter a DELTA website hostname rather than an IP address."
        )

    return "https://" + hostname


def check_delta_destination_dns(base_url):
    """Reject remote destinations resolving to non-public IP addresses.

    The approved local Docker development endpoint is handled separately.
    """
    import socket

    url = validate_delta_url(base_url)
    parsed = urlsplit(url)

    if url == "http://host.docker.internal:3000":
        return url

    try:
        results = socket.getaddrinfo(
            parsed.hostname,
            443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        raise DELTADestinationError(
            "The DELTA website hostname could not be resolved."
        ) from None

    addresses = {
        result[4][0]
        for result in results
    }

    if not addresses:
        raise DELTADestinationError(
            "No network address was found for the DELTA website."
        )

    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise DELTADestinationError(
                "The DELTA website resolves to a restricted network address."
            )

    return url
