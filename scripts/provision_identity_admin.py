"""Prepare a separate password+OTP workspace administrator, only with --apply.

This never stores the user's chosen password: the initial password is temporary,
and Keycloak requires a password change and authenticator enrollment by the owner.
No Google, Gnani or Modal provider is contacted by this local operator action.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
from urllib.error import HTTPError

from configure_identity_passwords import ROOT, local_admin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps({
            "plan_only": True, "username": "charcha-admin",
            "privileges": "Workspace administration, including host-email policy",
            "required_setup": ["Replace temporary password", "Enroll authenticator OTP"],
            "google_login_grants_admin": False, "provider_calls": 0,
        }, indent=2))
        return
    directory = ROOT / "deploy/gcp/generated"
    env_path = directory / "api.env"
    receipt = directory / "administrator-setup.json"
    env = env_path.read_text()
    if "\nCHARCHA_ADMIN_SUBJECT=\n" not in "\n" + env or receipt.exists():
        raise ValueError("Administrator is already configured; refusing to replace credentials")
    admin = local_admin()
    if admin("/users?username=charcha-admin&exact=true"):
        raise ValueError("Administrator username exists; review it before continuing")
    flows = admin("/authentication/flows")
    if not any(flow["alias"] == "charcha-browser" for flow in flows):
        admin("/authentication/flows/browser/copy", "POST", {"newName": "charcha-browser"})
    [flow] = [item for item in admin("/authentication/flows") if item["alias"] == "charcha-browser"]
    executions = admin("/authentication/flows/charcha-browser/executions")
    references = {"auth-username-password-form": "pwd", "auth-otp-form": "otp"}
    configured = set()
    for execution in executions:
        reference = references.get(execution.get("providerId"))
        if not reference:
            continue
        config = {"alias": "charcha-reference-" + reference, "config": {
            "default.reference.value": reference, "default.reference.maxAge": "300",
        }}
        existing = execution.get("authenticationConfig")
        if existing:
            previous = admin("/authentication/config/" + existing)
            if not previous.get("alias", "").startswith("charcha-reference-"):
                raise ValueError("Unexpected authenticator configuration; manual review required")
            admin("/authentication/config/" + existing, "PUT", config)
        else:
            admin("/authentication/executions/" + execution["id"] + "/config", "POST", config)
        configured.add(reference)
    if configured != {"pwd", "otp"}:
        raise ValueError("Password and OTP executions were not both found; administrator remains disabled")
    [client] = admin("/clients?clientId=charcha-web")
    bindings = {**client.get("authenticationFlowBindingOverrides", {}), "browser": flow["id"]}
    admin("/clients/" + client["id"], "PUT", {"authenticationFlowBindingOverrides": bindings})
    mappers = admin("/clients/" + client["id"] + "/protocol-mappers/models")
    [mapper] = [item for item in mappers if item["protocolMapper"] == "oidc-amr-mapper"]
    mapper["config"] = {**mapper.get("config", {}), "claim.name": "amr", "id.token.claim": "true"}
    admin("/clients/" + client["id"] + "/protocol-mappers/models/" + mapper["id"], "PUT", mapper)
    password = secrets.token_urlsafe(30)
    admin("/users", "POST", {
        "username": "charcha-admin", "email": "charcha-admin@workspace.invalid",
        "emailVerified": True, "enabled": True,
        "firstName": "Workspace", "lastName": "Administrator",
        "requiredActions": ["UPDATE_PASSWORD", "CONFIGURE_TOTP"],
        "credentials": [{"type": "password", "value": password, "temporary": True}],
    })
    [user] = admin("/users?username=charcha-admin&exact=true")
    issuer = next(line.split("=", 1)[1] for line in env.splitlines() if line.startswith("CHARCHA_OIDC_ISSUER="))
    with os.fdopen(os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
        json.dump({"username": "charcha-admin", "temporary_password": password,
                   "setup_url": issuer + "/account/", "subject": user["id"],
                   "note": "Finish password change and OTP enrollment here, then sign into the Charcha admin portal. Google-only and password-only grants remain rejected."}, file, indent=2)
    env_path.write_text(env.replace("CHARCHA_ADMIN_SUBJECT=\n", "CHARCHA_ADMIN_SUBJECT=" + user["id"] + "\n"), encoding="utf-8")
    print("Administrator prepared. Owner password change and OTP enrollment are still required; credentials are private.")


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        raise SystemExit(f"Administrator preparation stopped (HTTP {error.code}); no credentials logged.") from None
