"""Apply password settings to the local Keycloak instance over loopback only.

Run as the VM operator. This never reads or calls Gnani or Modal. An optional
disposable guest account can verify the public password flow and then be removed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8180/identity"
PROBE = ROOT / "deploy/gcp/generated/password-probe.json"


def local_admin():
    """Return an authenticated operator client restricted to this local realm."""
    values = {}
    for line in (ROOT / "deploy/gcp/generated/identity.env").read_text().splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    token_data = urlencode({
        "grant_type": "password", "client_id": "admin-cli",
        "username": values["KC_BOOTSTRAP_ADMIN_USERNAME"],
        "password": values["KC_BOOTSTRAP_ADMIN_PASSWORD"],
    }).encode()
    token_request = Request(BASE + "/realms/master/protocol/openid-connect/token", data=token_data)
    with urlopen(token_request, timeout=15) as response:
        token = json.load(response)["access_token"]

    def admin(path, method="GET", data=None):
        request = Request(BASE + "/admin/realms/charcha" + path, method=method,
                          data=json.dumps(data).encode() if data is not None else None,
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urlopen(request, timeout=15) as response:
            body = response.read()
            return json.loads(body) if body else None

    return admin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--create-probe", action="store_true")
    action.add_argument("--remove-probe", action="store_true")
    args = parser.parse_args()
    admin = local_admin()

    if args.remove_probe:
        if not PROBE.is_file():
            print("No disposable password test account to remove.")
            return
        probe = json.loads(PROBE.read_text())
        if not re.fullmatch(r"charcha-probe-[a-f0-9]{12}", probe["username"]):
            raise ValueError("Refusing to remove an unrecognized test identity")
        user = admin("/users/" + probe["id"])
        if user["username"] != probe["username"] or user["email"] != probe["username"] + "@example.invalid":
            raise ValueError("Refusing to remove an identity that does not match the test receipt")
        admin("/users/" + probe["id"], "DELETE")
        PROBE.unlink()
        print("Removed only the disposable password test identity.")
        return

    template = json.loads((ROOT / "deploy/identity/charcha-realm.json").read_text())
    keys = ("passwordPolicy", "verifyEmail", "registrationAllowed", "resetPasswordAllowed",
            "editUsernameAllowed", "duplicateEmailsAllowed", "bruteForceProtected",
            "permanentLockout", "failureFactor")
    admin("", "PUT", {key: template[key] for key in keys})
    [client] = admin("/clients?clientId=charcha-web")
    attributes = {**client.get("attributes", {}), "access.token.lifespan": "14400"}
    admin("/clients/" + client["id"], "PUT", {"attributes": attributes})
    realm = admin("")
    assert realm["passwordPolicy"] == template["passwordPolicy"]
    assert realm["verifyEmail"] and not realm["registrationAllowed"] and not realm["resetPasswordAllowed"]
    assert admin("/identity-provider/instances/google")["enabled"]
    print("Password policy applied; verified Google enrollment and Google recovery preserved.")

    if args.create_probe:
        if PROBE.exists():
            raise ValueError("A disposable test receipt already exists; do not create another identity")
        username = "charcha-probe-" + secrets.token_hex(6)
        password = secrets.token_urlsafe(30)
        admin("/users", "POST", {
            "username": username, "email": username + "@example.invalid",
            "emailVerified": True, "enabled": True,
            "firstName": "Deployment", "lastName": "Check",
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        })
        [user] = admin("/users?" + urlencode({"username": username, "exact": "true"}))
        fd = os.open(PROBE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as file:
            json.dump({"id": user["id"], "username": username, "password": password}, file)
        print("Created one disposable guest test identity. Credentials are in the private receipt only.")


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        raise SystemExit(f"Local identity configuration failed (HTTP {error.code}); no credentials logged.") from None
