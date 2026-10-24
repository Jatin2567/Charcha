"""The public HTTP route must use the financial-redaction boundary."""
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from artha_mesh.config import Settings
from artha_mesh.main import create_app


def test_public_usage_hides_manual_balance_and_never_calls_a_provider():
    app = create_app(Settings(mode="live", usage_require_flow_approval=True, _env_file=None))
    app.state.usage.record_programme_balance(
        balance=3210.45, unit="INR", observed_at=datetime.now(UTC), source="user_reported",
    )
    with TestClient(app) as client:
        report = client.get("/api/usage").json()
    assert report["programme"]["balance"] is None
    assert report["programme"]["unit"] is None
    assert report["approval"]["status"] == "locked"
    assert all(resource["used"] == 0 for resource in report["resources"])
    assert "3210.45" not in str(report)
