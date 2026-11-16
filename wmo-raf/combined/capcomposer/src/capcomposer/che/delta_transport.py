"""Low-level transport support for the CHE-to-DELTA connector."""

import ipaddress
import socket

from urllib3.connection import HTTPSConnection

from .delta_security import DELTADestinationError


class VerifiedHTTPSConnection(HTTPSConnection):
    """Connect to an explicitly validated address while checking TLS hostname."""

    def _new_conn(self):
        addresses = socket.getaddrinfo(
            self._dns_host,
            self.port,
            type=socket.SOCK_STREAM,
        )

        permitted = [
            entry for entry in addresses
            if ipaddress.ip_address(entry[4][0]).is_global
        ]

        if len(permitted) != len(addresses) or not permitted:
            raise DELTADestinationError(
                "DELTA resolves to a restricted network address."
            )

        last_error = None

        for family, socktype, proto, _, address in permitted:
            sock = socket.socket(family, socktype, proto)
            try:
                sock.settimeout(self.timeout)
                for level, option, value in self.socket_options or []:
                    sock.setsockopt(level, option, value)
                if self.source_address:
                    sock.bind(self.source_address)
                sock.connect(address)
                return sock
            except OSError as error:
                last_error = error
                sock.close()

        raise OSError("Unable to connect to the verified DELTA destination") from last_error


def secure_delta_request(base_url, api_path, api_key, payload=None):
    """Make an authenticated DELTA request through a checked connection."""
    import json
    import urllib.parse
    import urllib.request

    import urllib3

    from .delta_security import check_delta_destination_dns

    base_url = check_delta_destination_dns(base_url)

    if not api_path.startswith("/") or api_path.startswith("//"):
        raise DELTADestinationError("Invalid DELTA API path.")

    parsed = urllib.parse.urlsplit(api_path)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise DELTADestinationError("Invalid DELTA API path.")

    headers = {
        "X-Auth": api_key,
        "Accept": "application/json",
    }

    if payload is not None:
        headers["Content-Type"] = "application/json"

    method = "POST" if payload is not None else "GET"
    body = json.dumps(payload).encode("utf-8") if payload is not None else None

    if base_url == "http://host.docker.internal:3000":
        from .delta_client import DELTA_OPENER

        request = urllib.request.Request(
            base_url + api_path,
            data=body,
            headers=headers,
            method=method,
        )
        with DELTA_OPENER.open(request, timeout=30) as response:
            return json.load(response)

    Pool = type(
        "VerifiedDELTAPool",
        (urllib3.HTTPSConnectionPool,),
        {"ConnectionCls": VerifiedHTTPSConnection},
    )

    hostname = urllib.parse.urlsplit(base_url).hostname
    pool = Pool(
        hostname,
        port=443,
        cert_reqs="CERT_REQUIRED",
        retries=False,
        timeout=urllib3.Timeout(connect=10, read=30),
    )

    try:
        response = pool.request(
            method,
            api_path,
            body=body,
            headers=headers,
            redirect=False,
        )

        if response.status != 200:
            raise DELTADestinationError(
                f"DELTA API returned HTTP {response.status}"
            )

        return json.loads(response.data)
    finally:
        pool.close()
