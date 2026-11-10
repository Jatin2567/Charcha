"""Deployment profile checks that use dummy credentials and make no provider requests."""
import unittest

from prepare_deployment import PreparationError
from prepare_meeting_features import feature_environment


class MeetingProfileTests(unittest.TestCase):
    def test_original_audio_has_zero_daily_allowances(self):
        env = feature_environment(None)
        self.assertEqual(env["CHARCHA_MODE"], "transport")
        self.assertEqual(env["AUDIO_SCREENING_MODE"], "off")
        self.assertEqual(env["AUDIO_SCREENING_ON_DEMAND"], "true")
        self.assertEqual(env["GNANI_API_KEY"], "")
        self.assertEqual(env["EVON_BASE_URL"], "")
        self.assertEqual(env["EVON_SERVERLESS"], "false")
        self.assertTrue(all(value == "0" for key, value in env.items() if key.endswith("_PER_DAY")))

    def test_live_profile_keeps_existing_identity_and_usage_ledger(self):
        env = feature_environment({
            "GNANI_API_KEY": "fixture-only", "EVON_BASE_URL": "http://127.0.0.1:8001/v1",
            "EVON_MODEL": "fixture", "USAGE_TTS_CHARACTERS_PER_DAY": "300",
            "CHARCHA_ADMIN_SUBJECT": "unexpected", "LIVEKIT_API_SECRET": "unexpected",
            "CHARCHA_AUTH_CLIENT_SECRET": "unexpected", "USAGE_DB_PATH": "unexpected",
            "USAGE_REQUIRE_FLOW_APPROVAL": "false", "USAGE_STT_MAX_RETRIES": "1",
            "USAGE_VOICE_ENROLLMENTS_PER_DAY": "5", "USAGE_SHOW_PRIVATE_BALANCE": "true",
        })
        self.assertEqual(env["CHARCHA_MODE"], "live")
        self.assertEqual(env["USAGE_TTS_CHARACTERS_PER_DAY"], "300")
        self.assertEqual(env["USAGE_MAX_CONCURRENT_STT"], "5")
        self.assertEqual(env["USAGE_REQUIRE_FLOW_APPROVAL"], "true")
        self.assertEqual(env["USAGE_REQUIRE_ROOM_SCOPE"], "true")
        self.assertEqual(env["USAGE_STT_MAX_RETRIES"], "0")
        self.assertEqual(env["USAGE_VOICE_ENROLLMENTS_PER_DAY"], "0")
        self.assertEqual(env["USAGE_SHOW_PRIVATE_BALANCE"], "false")
        self.assertFalse({"CHARCHA_ADMIN_SUBJECT", "CHARCHA_AUTH_CLIENT_SECRET",
                          "LIVEKIT_API_SECRET", "USAGE_DB_PATH"}.intersection(env))

    def test_incomplete_private_config_rejects_live_mode(self):
        with self.assertRaises(PreparationError):
            feature_environment({})
        with self.assertRaises(PreparationError):
            feature_environment({"GNANI_API_KEY": "fixture-only", "EVON_MODEL": "fixture",
                                 "EVON_BASE_URL": "https://example.com/v1"})

    def test_reviewer_allowlist_is_preserved_and_can_be_explicitly_cleared(self):
        base = {"GNANI_API_KEY":"fixture-only", "EVON_MODEL":"fixture",
                "EVON_BASE_URL":"https://evon.charcha-fixture.in/v1"}
        for value, expected in [("https://GPU.charcha-fixture.in/", "https://gpu.charcha-fixture.in"), ("", "")]:
            env = feature_environment({**base, "REVIEWER_GPU_ALLOWED_ORIGINS":value})
            self.assertEqual(env["REVIEWER_GPU_ALLOWED_ORIGINS"], expected)
        with self.assertRaises(PreparationError):
            feature_environment({**base, "REVIEWER_GPU_ALLOWED_ORIGINS":"https://127.0.0.1"})

    def test_serverless_flag_survives_live_feature_environment(self):
        base = {"GNANI_API_KEY":"fixture-only", "EVON_MODEL":"fixture",
                "EVON_BASE_URL":"https://evon.charcha-fixture.in/v1"}
        for value in ("true", "false"):
            self.assertEqual(feature_environment({**base, "EVON_SERVERLESS":value})["EVON_SERVERLESS"], value)
        with self.assertRaises(PreparationError):
            feature_environment({**base, "EVON_SERVERLESS":"yes"})


if __name__ == "__main__":
    unittest.main()
