"""Stage coverage, resource limits and receipt tests without network or credentials."""
import json
from decimal import Decimal
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_five_language_calls as batch
from five_language_modal import reserve_usd
from export_five_language_calls import check_year, public_result, word_error_rate


def test_every_pair_is_budgeted_once_and_each_language_is_both_source_and_listener():
    plan = batch.plan()
    pairs = plan["routes"]
    assert len({frozenset(pair) for pair in pairs}) == len(pairs) == plan["flow_limit"] == 10
    for code in batch.CLIPS:
        assert sum(a == code for a,b in pairs) == sum(b == code for a,b in pairs) == 2
    assert plan["source_tts"] == plan["retries"] == plan["per_flow"]["voice_enrollments"] == 0
    assert all(plan["per_flow"][key] == 1 for key in ("stt_connections","mt_requests","tts_requests"))


def test_reservation_includes_region_and_teardown_and_rejects_unbounded_duration():
    rates = dict(gpu_hour_cost_a100_80gb="2.50", cpu_hour_cost=".0473", mem_gib_hour_cost=".008")
    assert reserve_usd(rates, 1500, overhead_usd=".05") == Decimal("2.58")
    with pytest.raises(ValueError):
        reserve_usd(rates, 1801)


def test_source_word_error_keeps_missing_words_and_diacritics_visible():
    assert word_error_rate("Hello, राम!", "hello राम") == 0
    assert word_error_rate("दस बजे नहीं", "दस बजे") == pytest.approx(.3333)
    assert word_error_rate("கால்", "கல்") == 1


def test_reference_year_distinguishes_mismatch_from_an_unparsed_spoken_year():
    assert check_year("१९७६", "1976") is None
    assert check_year("१९७६", "1972") == {"reference":"1976", "recognized":"1972"}
    assert check_year("१९७६", "nineteen seventy six") == {"reference":"1976", "recognized":None}


def test_busy_windows_reader_retries_only_the_local_receipt(monkeypatch, tmp_path):
    original = Path.replace
    calls = []
    def busy_once(self, target):
        calls.append(target)
        if len(calls) == 1:
            raise PermissionError("test-only sharing violation")
        return original(self, target)
    monkeypatch.setattr(Path, "replace", busy_once)
    batch.save(tmp_path, {"routes":[]})
    assert len(calls) == 2
    assert json.loads((tmp_path / "report.json").read_text()) == {"routes":[]}


def test_public_report_refuses_rehearsal_or_unclosed_grants(tmp_path):
    rows = [dict(source=a,target=b,status="unattempted") for a,b in batch.STAGE["routes"]]
    report = dict(stage_id=batch.STAGE["id"],real_providers=False,physical_devices=False,routes=rows)
    receipt = dict(stopped=True, before={"metered_cost":"0"}, after={"metered_cost":".05"})
    (tmp_path/"compute.json").write_text(json.dumps(receipt))
    (tmp_path/"report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError):
        public_result(tmp_path)
    report.update(real_providers=True)
    rows[0].update(status="failed",stage="mt",grant_closed=False)
    (tmp_path/"report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError):
        public_result(tmp_path)
