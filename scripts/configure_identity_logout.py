"""Apply Charcha's logout callbacks to its existing Delhi identity client."""
import argparse
from pathlib import Path
from urllib.parse import urlsplit

from configure_identity_passwords import ROOT, local_admin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    config = Path(ROOT, "deploy/gcp/generated/api.env").read_text().splitlines()
    origin = next(line.split("=", 1)[1] for line in config if line.startswith("CHARCHA_PUBLIC_ORIGIN=")).rstrip("/")
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or origin != "https://" + parsed.hostname:
        raise ValueError("Expected a deployed HTTPS origin")
    admin = local_admin()
    [client] = admin("/clients?clientId=charcha-web")
    path = "/clients/" + client["id"]
    old = admin(path)
    desired = {"post.logout.redirect.uris": origin + "/",
               "backchannel.logout.url": origin + "/api/account/backchannel-logout",
               "backchannel.logout.session.required": "true"}
    def matches(current):
        return current.get("frontchannelLogout") is False and all(
            current.get("attributes", {}).get(key) == value for key, value in desired.items())
    if matches(old):
        print("Charcha logout callbacks are configured.")
        return
    if not args.apply:
        print("The existing Charcha web client needs the session logout callback settings.")
        return
    admin(path, "PUT", {"frontchannelLogout": False, "attributes": {**old["attributes"], **desired}})
    assert matches(admin(path))
    print("Verified Charcha post-logout return and signed back-channel notification settings.")


if __name__ == "__main__":
    main()
