"""Refresh the self-hosted LiveKit IPv4 at boot on the Delhi GCE meeting VM."""
import ipaddress
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request

BUNDLE = Path("/opt/charcha/deploy/gcp/generated")


def with_address(config: str, address: str) -> str:
    public = ipaddress.IPv4Address(address)
    if not public.is_global or public.is_multicast:
        raise ValueError("Expected the instance's public unicast IPv4 address")
    updated, fields = re.subn(r"(?m)^(  node_ip: )[0-9.]+$", lambda match: match[1] + str(public), config)
    if fields != 1:
        raise ValueError("Expected exactly one RTC node_ip field")
    return updated


def main():
    path = BUNDLE / "livekit.yaml"
    request = urllib.request.Request(
        "http://169.254.169.254/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip",
        headers={"Metadata-Flavor": "Google"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=5) as response:
        if response.headers.get("Metadata-Flavor") != "Google":
            raise RuntimeError("Unexpected metadata response")
        address = response.read(64).decode("ascii").strip()
    original = path.read_text()
    updated = with_address(original, address)
    if updated != original:
        with tempfile.NamedTemporaryFile(mode="w", dir=BUNDLE, delete=False) as file:
            temporary = Path(file.name)
            file.write(updated)
        try:
            os.chmod(temporary, path.stat().st_mode & 0o777)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    # Rebind the updated file even after an interrupted previous startup.
    subprocess.run(["docker", "compose", "-f", str(BUNDLE / "compose.json"), "up", "-d",
                    "--no-deps", "--force-recreate", "livekit"], check=True)


if __name__ == "__main__":
    main()
