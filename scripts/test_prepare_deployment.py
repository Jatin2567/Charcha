"""Offline deployment-contract tests. No Docker, DNS, provider or billing access."""
from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prepare_deployment import PreparationError, check, main, prepare, read_env, validate_inputs, validate_reviewer_origins


class DeploymentPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.config_path = self.base / "inputs.json"
        self.env_path = self.base / "provider.env"
        self.output = self.base / "generated"
        self.inputs = {"app_domain": "meet.charcha-fixture.in", "livekit_domain": "rtc.charcha-fixture.in", "turn_domain": "turn.charcha-fixture.in", "public_ipv4": "8.8.4.4"}
        self.config_path.write_text(json.dumps(self.inputs), encoding="utf-8")
        self.env_path.write_text("CHARCHA_MODE=demo\nGNANI_API_KEY=private-$literal-gnani\nEVON_BASE_URL=https://evon.charcha-fixture.in/v1\nEVON_MODEL=actual-evon-served-id\nEVON_API_KEY=private-evon\nLIVEKIT_API_SECRET=must-not-be-reused\n", encoding="utf-8")

    def prepare(self):
        return prepare(self.config_path, self.env_path, self.output)

    def test_offline_generation_and_check(self):
        with patch("socket.socket", side_effect=AssertionError("Networking is forbidden")):
            summary = self.prepare()
            result = check(self.output)
        self.assertEqual(summary["provider_calls"], 0)
        self.assertEqual(result["status"], "configuration_valid")
        self.assertFalse(result["runtime_verified"])
        self.assertNotIn("private-", json.dumps(summary))

    def test_live_configuration_and_private_internal_urls(self):
        self.prepare()
        env = read_env(self.output / "api.env", raw=True)
        self.assertEqual(env["CHARCHA_MODE"], "live")
        self.assertEqual(env["LIVEKIT_URL"], "wss://rtc.charcha-fixture.in")
        self.assertEqual(env["LIVEKIT_INTERNAL_URL"], "ws://127.0.0.1:7880")
        self.assertEqual(env["CORS_ORIGINS"], "https://meet.charcha-fixture.in")
        self.assertEqual(env["USAGE_DB_PATH"], "/app/data/usage.sqlite3")
        self.assertEqual(env["USAGE_REQUIRE_FLOW_APPROVAL"], "true")
        self.assertEqual(env["USAGE_SHOW_PRIVATE_BALANCE"], "false")
        self.assertEqual(env["GNANI_API_KEY"], "private-$literal-gnani")
        self.assertEqual(env["EVON_MODEL"], "actual-evon-served-id")
        self.assertNotEqual(env["LIVEKIT_API_SECRET"], "must-not-be-reused")

    def test_reviewer_origins_survive_generated_runtime_without_extra_settings(self):
        with self.env_path.open("a", encoding="utf-8") as source:
            source.write("REVIEWER_GPU_ALLOWED_ORIGINS=https://GPU.charcha-fixture.in:443/, https://model.charcha-fixture.in\n")
        self.prepare()
        env = read_env(self.output / "api.env", raw=True)
        self.assertEqual(env["REVIEWER_GPU_ALLOWED_ORIGINS"],
                         "https://gpu.charcha-fixture.in,https://model.charcha-fixture.in")
        self.assertEqual(check(self.output)["status"], "configuration_valid")

    def test_reviewer_origins_reject_unsafe_values_without_echoing_them(self):
        invalid = ["http://gpu.charcha-fixture.in", "https://127.0.0.1", "https://169.254.169.254",
                   "https://[::1]", "https://gpu.internal", "https://gpu.company.local",
                   "https://gpu.company.localhost", "https://gpu.home.arpa", "https://localhost",
                   "https://private-secret@gpu.charcha-fixture.in", "https://gpu.charcha-fixture.in:8443",
                   "https://gpu.charcha-fixture.in/v1", "https://gpu.charcha-fixture.in?key=private-secret",
                   "https://gpu.charcha-fixture.in#private-secret", "https://gpu.charcha-fixture.in%2f",
                   "https://gpu.charcha-fixture.in,", "https://gpu.charcha-fixture.in\\@evil.com"]
        for value in invalid:
            with self.subTest(value=value), self.assertRaisesRegex(PreparationError, "REVIEWER_GPU_ALLOWED_ORIGINS") as error:
                validate_reviewer_origins(value)
            self.assertNotIn(value, str(error.exception))
            self.assertNotIn("private-secret", str(error.exception))
        self.assertEqual(validate_reviewer_origins("  "), "")
        self.assertEqual(validate_reviewer_origins("https://gpu.charcha-fixture.in,https://gpu.charcha-fixture.in/"),
                         "https://gpu.charcha-fixture.in")

    def test_optional_serverless_flag_is_preserved_and_strict(self):
        original = self.env_path.read_text(encoding="utf-8")
        for value in ("true", "false"):
            self.output = self.base / ("serverless-" + value)
            self.env_path.write_text(original + "EVON_SERVERLESS=" + value + "\n", encoding="utf-8")
            self.prepare()
            self.assertEqual(read_env(self.output / "api.env", raw=True)["EVON_SERVERLESS"], value)
        self.output = self.base / "serverless-invalid"
        for value in ("TRUE", "yes", "1", "", "private-invalid"):
            self.env_path.write_text(original + "EVON_SERVERLESS=" + value + "\n", encoding="utf-8")
            with self.assertRaisesRegex(PreparationError, "EVON_SERVERLESS"):
                self.prepare()
            self.assertFalse(self.output.exists())

    def test_shared_tls_port_routes_and_owned_stun(self):
        self.prepare()
        caddy = json.loads((self.output / "caddy.json").read_text())
        server = caddy["apps"]["layer4"]["servers"]["main"]
        self.assertEqual(server["listen"], [":443"])
        routes = server["routes"]
        self.assertEqual([r["match"][0]["tls"]["sni"][0] for r in routes], ["turn.charcha-fixture.in", "rtc.charcha-fixture.in", "meet.charcha-fixture.in"])
        self.assertEqual([r["handle"][1]["upstreams"][0]["dial"][0] for r in routes], ["127.0.0.1:5349", "127.0.0.1:7880", "127.0.0.1:8080"])
        self.assertEqual(routes[2]["handle"][0]["connection_policies"][0]["alpn"], ["http/1.1"])
        livekit = (self.output / "livekit.yaml").read_text()
        self.assertIn("development: false", livekit)
        self.assertIn("bind_addresses: [127.0.0.1]", livekit)
        self.assertIn("external_tls: true", livekit)
        self.assertIn('stun_servers: ["turn.charcha-fixture.in:3478"]', livekit)
        self.assertIn("use_external_ip: false", livekit)

    def test_modal_credentials_and_language_voice_overrides_survive_preparation(self):
        values = ("GNANI_API_KEY=private-gnani\nEVON_MODEL=evon\n"
                  "EVON_BASE_URL=https://owned-charcha-serve.modal.run/v1\n"
                  "EVON_MODAL_KEY=private-$literal-modal-key\nEVON_MODAL_SECRET=private-modal-secret\n"
                  "TIMBRE_VOICE_HI=Nalini\nTIMBRE_VOICE_TA=Trisha\nTIMBRE_VOICE_BN=Kirra\n"
                  "TIMBRE_VOICE_TE=Suhana\nTIMBRE_VOICE_MR=Zahira\nUSAGE_MAX_CONCURRENT_STT=5\n"
                  "USAGE_VOICE_ENROLLMENTS_PER_DAY=0\n")
        self.env_path.write_text(values, encoding="utf-8")
        self.prepare()
        env = read_env(self.output / "api.env", raw=True)
        self.assertEqual(env["EVON_MODAL_KEY"], "private-$literal-modal-key")
        self.assertEqual(env["EVON_MODAL_SECRET"], "private-modal-secret")
        self.assertEqual(env["TIMBRE_VOICE_TA"], "Trisha")
        self.assertEqual(env["TIMBRE_VOICE_MR"], "Zahira")
        self.assertEqual(env["USAGE_MAX_CONCURRENT_STT"], "5")
        self.assertEqual(env["USAGE_VOICE_ENROLLMENTS_PER_DAY"], "0")
        self.assertEqual(check(self.output)["status"], "configuration_valid")

    def test_modal_pair_is_validated_before_any_deployment_files_are_written(self):
        for endpoint, key, secret in [
            ("https://owned.modal.run/v1", "private-key", ""),
            ("https://owned.modal.run/v1", "", "private-secret"),
            ("https://evon.charcha-fixture.in/v1", "private-key", "private-secret"),
            ("http://127.0.0.1:8001/v1", "private-key", "private-secret"),
            ("https://owned.modal.run:8443/v1", "private-key", "private-secret"),
            ("https://owned.modal.run/v1", "private key", "private-secret"),
        ]:
            with self.subTest(endpoint=endpoint, key_present=bool(key), secret_present=bool(secret)):
                self.env_path.write_text("GNANI_API_KEY=private-gnani\nEVON_MODEL=evon\n"
                                         f"EVON_BASE_URL={endpoint}\nEVON_MODAL_KEY={key}\nEVON_MODAL_SECRET={secret}\n")
                with self.assertRaisesRegex(PreparationError, "EVON_MODAL") as caught:
                    self.prepare()
                self.assertNotIn("private-", str(caught.exception))
                self.assertFalse(self.output.exists())

    def test_optional_streaming_stt_model_is_preserved_or_omitted_when_unselected(self):
        original = self.env_path.read_text(encoding="utf-8")
        for index, model in enumerate((None, "", "   ", "prisma-v2.5", "prisma-v3.0")):
            with self.subTest(model=model):
                self.output = self.base / f"stt-model-{index}"
                self.env_path.write_text(original + ("" if model is None else f"GNANI_STT_MODEL={model}\n"), encoding="utf-8")
                self.prepare()
                env = read_env(self.output / "api.env", raw=True)
                if model and model.strip():
                    self.assertEqual(env["GNANI_STT_MODEL"], model)
                else:
                    self.assertNotIn("GNANI_STT_MODEL", env)
                self.assertEqual(check(self.output)["status"], "configuration_valid")

    def test_invalid_streaming_stt_model_is_rejected_before_writing_deployment(self):
        original = self.env_path.read_text(encoding="utf-8")
        for model in ("prisma-v3", "private-invalid-model-value", "PRISMA-V3.0"):
            with self.subTest(model=model):
                self.env_path.write_text(original + f"GNANI_STT_MODEL={model}\n", encoding="utf-8")
                with self.assertRaisesRegex(PreparationError, "GNANI_STT_MODEL") as caught:
                    self.prepare()
                self.assertEqual(str(caught.exception), "GNANI_STT_MODEL requires prisma-v2.5 or prisma-v3.0, or leave it unset.")
                self.assertFalse(self.output.exists())
                self.assertEqual(list(self.base.glob(".charcha-prepare-*")), [])

    def test_host_network_single_worker_persistence_and_literal_secrets(self):
        self.prepare()
        compose = json.loads((self.output / "compose.json").read_text())
        services = compose["services"]
        self.assertTrue(all(service["network_mode"] == "host" and "ports" not in service for service in services.values()))
        self.assertEqual(services["livekit"]["image"], "livekit/livekit-server:v1.9.1")
        self.assertNotIn("--dev", services["livekit"]["command"])
        command = services["api"]["command"]
        self.assertEqual(command[command.index("--workers") + 1], "1")
        self.assertEqual(command[command.index("--host") + 1], "127.0.0.1")
        self.assertEqual(services["api"]["env_file"][0]["format"], "raw")
        self.assertEqual(compose["volumes"]["usage-ledger"]["name"], "artha-mesh-usage-ledger")

    def test_missing_credential_writes_nothing(self):
        self.env_path.write_text("GNANI_API_KEY=secret\nEVON_BASE_URL=https://evon.charcha-fixture.in/v1\n")
        with self.assertRaisesRegex(PreparationError, "EVON_MODEL"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_invalid_domains_rejected(self):
        for domain in ["http://meet.charcha-fixture.in", "*.charcha-fixture.in", "localhost", "meet.charcha-fixture.in\nother", "-bad.charcha-fixture.in", "meet.example.com", "meet.example.net", "meet.example.org", "meet.internal", "meet.local", "meet.test", "meet.invalid", "meet.example"]:
            with self.subTest(domain=domain), self.assertRaises(PreparationError):
                validate_inputs({**self.inputs, "app_domain": domain})

    def test_duplicate_domains_and_unknown_json_rejected(self):
        for change in [{"turn_domain": self.inputs["livekit_domain"]}, {"gnani_api_key": "must-not-be-here"}]:
            with self.subTest(change=change), self.assertRaises(PreparationError):
                validate_inputs({**self.inputs, **change})

    def test_nonpublic_ipv4_rejected(self):
        for address in ["127.0.0.1", "192.168.1.2", "::1", "203.0.113.5", "invalid"]:
            with self.subTest(address=address), self.assertRaises(PreparationError):
                validate_inputs({**self.inputs, "public_ipv4": address})

    def test_public_unencrypted_or_credential_urls_rejected(self):
        for url in ["http://evon.charcha-fixture.in/v1", "https://secret@evon.charcha-fixture.in/v1", "https://evon.charcha-fixture.in/v1?api_key=secret", "https://bad host.in/v1", "https://placeholder.example/v1", "https://placeholder.invalid/v1", "https://evon.example.com/v1", "https://example.org/v1", "https://example.net/v1", "https://evon.charcha-fixture.in/v1 "]:
            self.env_path.write_text(f"GNANI_API_KEY=private-secret\nEVON_MODEL=evon\nEVON_BASE_URL='{url}'\n")
            with self.subTest(url=url), self.assertRaises(PreparationError) as caught:
                self.prepare()
            self.assertNotIn("private-secret", str(caught.exception))
            self.assertFalse(self.output.exists())

    def test_whitespace_only_credentials_or_model_rejected(self):
        for name in ["GNANI_API_KEY", "EVON_MODEL"]:
            values = {"GNANI_API_KEY": "secret", "EVON_MODEL": "evon", "EVON_BASE_URL": "https://evon.charcha-fixture.in/v1"}
            values[name] = "'   '"
            self.env_path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
            with self.subTest(name=name), self.assertRaisesRegex(PreparationError, name):
                self.prepare()
            self.assertFalse(self.output.exists())

    def test_private_evon_http_allowed(self):
        self.env_path.write_text("GNANI_API_KEY=secret\nEVON_MODEL=evon\nEVON_BASE_URL=http://10.0.0.6:8000/v1\n")
        self.prepare()
        self.assertEqual(check(self.output)["status"], "configuration_valid")

    def test_zero_resource_limits_preserved(self):
        with self.env_path.open("a") as handle:
            handle.write("USAGE_TTS_REQUESTS_PER_DAY=0\nUSAGE_VOICE_ENROLLMENTS_PER_DAY=0\n")
        self.prepare()
        env = read_env(self.output / "api.env", raw=True)
        self.assertEqual(env["USAGE_TTS_REQUESTS_PER_DAY"], "0")
        self.assertEqual(env["USAGE_VOICE_ENROLLMENTS_PER_DAY"], "0")

    def test_transport_preparation_needs_no_model_or_speech_credentials(self):
        self.env_path.write_text("CHARCHA_MEETING_HOST_EMAIL=host@charcha-fixture.in\n", encoding="utf-8")
        prepare(self.config_path, self.env_path, self.output, mode="transport")
        env = read_env(self.output / "api.env", raw=True)
        self.assertEqual(env["CHARCHA_MODE"], "transport")
        self.assertEqual(env["CHARCHA_MEETING_HOST_EMAIL"], "host@charcha-fixture.in")
        self.assertEqual(env["AUDIO_SCREENING_MODE"], "off")
        self.assertEqual(check(self.output)["status"], "configuration_valid")

    def test_transport_preparation_strips_existing_credentials_and_allowances(self):
        with self.env_path.open("a", encoding="utf-8") as handle:
            handle.write("EVON_MODAL_KEY=private-modal-key\nEVON_MODAL_SECRET=private-modal-secret\nUSAGE_TTS_REQUESTS_PER_DAY=200\n")
        prepare(self.config_path, self.env_path, self.output, mode="transport")
        raw = (self.output / "api.env").read_text(encoding="utf-8")
        self.assertNotIn("private-", raw)
        env = read_env(self.output / "api.env", raw=True)
        self.assertTrue(all(value == "0" for key, value in env.items() if key.startswith("USAGE_") and key.endswith("_PER_DAY")))
        self.assertTrue(all(env[key] == "" for key in ("GNANI_API_KEY", "EVON_API_KEY", "EVON_MODAL_KEY", "EVON_MODAL_SECRET", "EVON_BASE_URL", "EVON_MODEL")))
        self.assertEqual(check(self.output)["status"], "configuration_valid")

    def test_invalid_credit_limit_fails_before_write(self):
        with self.env_path.open("a") as handle:
            handle.write("USAGE_STT_SECONDS_PER_DAY=-1\n")
        with self.assertRaisesRegex(PreparationError, "USAGE_STT_SECONDS_PER_DAY"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_duplicate_environment_names_fail(self):
        with self.env_path.open("a") as handle:
            handle.write("GNANI_API_KEY=second-secret\n")
        with self.assertRaisesRegex(PreparationError, "duplicate"):
            self.prepare()

    def test_output_refuses_overwrite_and_preserves_keys(self):
        self.prepare()
        before = (self.output / "api.env").read_bytes()
        with self.assertRaisesRegex(PreparationError, "already exists"):
            self.prepare()
        self.assertEqual(before, (self.output / "api.env").read_bytes())

    def test_separate_deployments_have_independent_keys(self):
        self.prepare()
        second = self.base / "second"
        prepare(self.config_path, self.env_path, second)
        self.assertNotEqual(read_env(self.output / "api.env", raw=True)["LIVEKIT_API_SECRET"], read_env(second / "api.env", raw=True)["LIVEKIT_API_SECRET"])

    def test_generated_file_tampering_rejected(self):
        self.prepare()
        path = self.output / "livekit.yaml"
        path.write_text(path.read_text().replace("development: false", "development: true"))
        with self.assertRaisesRegex(PreparationError, "livekit.yaml"):
            check(self.output)

    @unittest.skipUnless(os.name == "posix", "Symbolic link creation needs platform privileges")
    def test_symlink_output_rejected(self):
        self.prepare()
        linked = self.base / "linked"
        linked.symlink_to(self.output, target_is_directory=True)
        with self.assertRaisesRegex(PreparationError, "symbolic link"):
            check(linked)

    def test_original_private_env_untouched(self):
        before = self.env_path.read_bytes()
        self.prepare()
        self.assertEqual(before, self.env_path.read_bytes())

    def test_official_caddy_digest_supported_but_other_images_rejected(self):
        digest = "livekit/caddyl4@sha256:" + "a" * 64
        self.assertEqual(validate_inputs({**self.inputs, "caddy_image": digest})["caddy_image"], digest)
        with self.assertRaises(PreparationError):
            validate_inputs({**self.inputs, "caddy_image": "untrusted/other:latest"})

    @unittest.skipUnless(os.name == "posix", "POSIX file modes are enforced on the Linux deployment host")
    def test_private_posix_permissions(self):
        self.prepare()
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        for path in self.output.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_cli_never_prints_provider_values(self):
        self.env_path.write_text("GNANI_API_KEY=do-not-print-this\nEVON_BASE_URL=https://evon.charcha-fixture.in/v1\n")
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["prepare", "--config", str(self.config_path), "--env-file", str(self.env_path), "--output", str(self.output)]), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main()
        self.assertEqual(result, 1)
        self.assertNotIn("do-not-print-this", stdout.getvalue() + stderr.getvalue())
        self.assertIn("EVON_MODEL", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
