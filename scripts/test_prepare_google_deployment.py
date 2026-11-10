"""Verify that the Google-URL deployment stays isolated from paid AI providers."""
import json
import unittest

from prepare_deployment import PreparationError
from prepare_google_deployment import render, validate


class GoogleDeploymentTests(unittest.TestCase):
    def bundle(self, identity=None):
        return render("https://charcha-example-uc.a.run.app", "8.8.8.8", "10.54.0.10", identity or {})

    def test_provider_isolation_and_india_identity(self):
        files = self.bundle({"GNANI_API_KEY": "must-not-be-copied", "EVON_API_KEY": "also-private", "EVON_SERVERLESS":"true"})
        env = dict(line.split("=", 1) for line in files["api.env"].splitlines() if line and not line.startswith("#"))
        self.assertEqual(env["CHARCHA_MODE"], "transport")
        self.assertEqual(env["CHARCHA_IDENTITY_PROVIDER"], "keycloak")
        self.assertEqual(env["AUDIO_SCREENING_MODE"], "off")
        self.assertEqual(env["CHARCHA_ADMIN_SUBJECT"], "")
        self.assertEqual(env["EVON_BASE_URL"], "")
        self.assertEqual(env["EVON_SERVERLESS"], "false")
        self.assertEqual(env["GNANI_API_KEY"], "")
        self.assertTrue(all(value == "0" for key, value in env.items() if key.startswith("USAGE_") and key.endswith("_PER_DAY")))
        self.assertNotIn("must-not-be-copied", "".join(files.values()))
        self.assertNotIn("also-private", "".join(files.values()))

    def test_private_ports_and_single_state_owner(self):
        files = self.bundle()
        services = json.loads(files["compose.json"])["services"]
        self.assertEqual(services["identity"]["ports"], ["127.0.0.1:8180:8080"])
        self.assertNotIn("ports", services["identity-db"])
        self.assertIn("127.0.0.1", services["api"]["command"])
        self.assertIn("1", services["api"]["command"])
        self.assertIn("listen 10.54.0.10:8080;", files["nginx.conf"])
        self.assertIn("location /rtc", files["nginx.conf"])
        self.assertIn("location /identity/admin/ { return 404; }", files["nginx.conf"])
        self.assertIn("udp_port: 7882", files["livekit.yaml"])
        self.assertIn("KC_HOSTNAME=https://charcha-example-uc.a.run.app/identity\n", files["identity.env"])

    def test_explicit_reviewer_origins_survive_without_copying_provider_credentials(self):
        files = self.bundle({"REVIEWER_GPU_ALLOWED_ORIGINS":"https://GPU.charcha-fixture.in/",
                             "GNANI_API_KEY":"private-do-not-copy", "EVON_MODAL_SECRET":"private-do-not-copy"})
        env = dict(line.split("=", 1) for line in files["api.env"].splitlines() if line and not line.startswith("#"))
        self.assertEqual(env["REVIEWER_GPU_ALLOWED_ORIGINS"], "https://gpu.charcha-fixture.in")
        self.assertEqual(env["CHARCHA_MODE"], "transport")
        self.assertNotIn("private-do-not-copy", "".join(files.values()))
        with self.assertRaises(PreparationError):
            self.bundle({"REVIEWER_GPU_ALLOWED_ORIGINS":"https://169.254.169.254"})

    def test_google_is_not_advertised_without_credentials(self):
        files = self.bundle()
        realm = json.loads(files["charcha-realm.json"])
        self.assertIn("basic", realm["clients"][0]["defaultClientScopes"])
        self.assertFalse(realm["identityProviders"][0]["enabled"])
        self.assertFalse(json.loads(files["manifest.json"])["google_oauth_supplied"])
        self.assertNotIn("${", files["charcha-realm.json"])

    def test_google_credential_pair_and_callback(self):
        with self.assertRaises(PreparationError):
            self.bundle({"GOOGLE_CLIENT_ID": "client"})
        files = self.bundle({"GOOGLE_CLIENT_ID": "client", "GOOGLE_CLIENT_SECRET": "sentinel-oauth-secret"})
        realm = json.loads(files["charcha-realm.json"])
        self.assertTrue(realm["identityProviders"][0]["enabled"])
        self.assertEqual(realm["identityProviders"][0]["config"]["clientSecret"], "sentinel-oauth-secret")
        self.assertNotIn("sentinel-oauth-secret", files["manifest.json"])
        self.assertEqual(realm["clients"][0]["redirectUris"], ["https://charcha-example-uc.a.run.app/api/account/callback"])

    def test_reject_untrusted_origin_and_wrong_network_addresses(self):
        for origin in ("http://charcha.run.app", "https://example.com", "https://charcha.run.app/api", "https://user@charcha.run.app", "https://charcha.run.app:443", "https://charcha.run.app?x=1"):
            with self.subTest(origin=origin), self.assertRaises(PreparationError):
                validate(origin, "8.8.8.8", "10.54.0.10")
        for private in ("127.0.0.1", "0.0.0.0", "8.8.4.4", "169.254.0.1"):
            with self.subTest(private=private), self.assertRaises(PreparationError):
                validate("https://charcha.run.app", "8.8.8.8", private)


if __name__ == "__main__":
    unittest.main()
