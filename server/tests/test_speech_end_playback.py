"""Shared-clock PCM annotation checks. Synthetic files only; no audio/API capture."""
from array import array
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import wave

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("speech_end_playback_tests", ROOT / "scripts/measure_speech_end_playback.py")
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)


def test_recording_retains_the_room_screening_mode(tmp_path):
    path, annotations = recording(tmp_path)
    assert measure.analyze(path, {**annotations, "screening_mode": "monitor"})["screening_mode"] == "monitor"
    with pytest.raises(measure.Rejected):
        measure.analyze(path, {**annotations, "screening_mode": "invalid"})


def recording(tmp_path, *, rate=16000, frames=None, source_end=None, output_start=None,
              source_signal=True, output_signal=True, channels=2, width=2):
    frames = frames or rate * 3
    source_end = source_end if source_end is not None else rate
    output_start = output_start if output_start is not None else rate * 3 // 2
    path = tmp_path / "isolated-stereo.wav"
    samples = array("h")
    for index in range(frames):
        left = 4000 if source_signal and max(0, source_end-rate//50) <= index < source_end else 0
        right = -5000 if output_signal and output_start <= index < min(frames,output_start+rate//50) else 0
        samples.extend((left,right) if channels == 2 else (left+right,))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(width)
        audio.setframerate(rate)
        audio.writeframes(samples.tobytes() if width == 2 else b"\x80" * frames * channels)
    annotations = {
        "recording_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "trial_id":"hi-ta-warm-01","source_language":"hi","target_language":"ta",
        "condition":"warm_route","provider_kind":"live","capture_kind":"acoustic_two_channel",
        "voice_mode":"standard","status":"complete","source_speech_end_sample":source_end,
        "listener_audio_start_sample":output_start,"capture_attested":True,
        "annotations_reviewed":True,"meaning_reviewed":False,
    }
    return path, annotations


@pytest.mark.parametrize("rate", [8000,16000,48000,96000])
def test_one_recording_clock_gives_known_500ms_without_device_clock_subtraction(tmp_path, rate):
    path, annotations = recording(tmp_path, rate=rate)
    original = path.read_bytes()
    result = measure.analyze(path,annotations)
    assert result["latency_ms"] == 500
    assert result["sample_rate_hz"] == rate and result["recording_frames"] == rate*3
    assert result["annotation_resolution_ms"] == round(1000/rate,6)
    assert result["clock"] == "single_recording_sample_index"
    assert result["physical_playback_measured"] is True
    assert result["recording_channels"] == 2
    assert result["source_channel_index"] == 0 and result["listener_channel_index"] == 1
    assert result["meaning_reviewed"] is False
    assert result["acceptance"] == "requires_aggregate_gate_and_human_review"
    assert path.read_bytes() == original and str(path) not in json.dumps(result)


@pytest.mark.parametrize("rate", [8000,16000,48000])
def test_mono_acoustic_recording_uses_same_channel_for_known_500ms_offset(tmp_path,rate):
    path,annotations = recording(tmp_path,rate=rate,channels=1)
    annotations["capture_kind"] = "acoustic_single_channel"
    result = measure.analyze(path,annotations)
    assert result["latency_ms"] == 500 and result["physical_playback_measured"] is True
    assert result["recording_channels"] == 1
    assert result["source_channel_index"] == result["listener_channel_index"] == 0
    assert result["capture_provenance"] == "operator_attested"
    assert result["meaning_reviewed"] is False
    assert any("overlapping voices" in value for value in result["limitations"])


@pytest.mark.parametrize("kind,channels", [
    ("acoustic_single_channel",2),("acoustic_two_channel",1),
    ("electrical_loopback_two_channel",1),("browser_render_dual_channel",1),
])
def test_capture_kind_cannot_be_relabelled_to_accept_wrong_channel_count(tmp_path,kind,channels):
    path,annotations = recording(tmp_path,channels=channels)
    annotations["capture_kind"] = kind
    with pytest.raises(measure.Rejected,match="mono only"):
        measure.analyze(path,annotations)


def test_mono_overlap_remains_signed_evidence_for_aggregate_gate_to_reject(tmp_path):
    path,annotations = recording(tmp_path,channels=1,output_start=8000)
    annotations["capture_kind"] = "acoustic_single_channel"
    result = measure.analyze(path,annotations)
    assert result["latency_ms"] == -500
    assert result["acceptance"] == "requires_aggregate_gate_and_human_review"


@pytest.mark.parametrize("field", ["capture_attested","annotations_reviewed"])
def test_mono_capture_needs_explicit_attestation_and_annotation_review(tmp_path,field):
    path,annotations = recording(tmp_path,channels=1)
    annotations.update(capture_kind="acoustic_single_channel",**{field:False})
    assert measure.analyze(path,annotations)["physical_playback_measured"] is False


def test_negative_offset_is_retained_as_overlap_without_clamping(tmp_path):
    path, annotations = recording(tmp_path,output_start=8000)
    result = measure.analyze(path,annotations)
    assert result["latency_ms"] == -500
    assert any("Negative offsets" in text for text in result["limitations"])


def test_hash_mismatch_is_rejected_before_audio_is_analyzed(tmp_path, monkeypatch):
    path, annotations = recording(tmp_path)
    annotations["recording_sha256"] = "0"*64
    monkeypatch.setattr(measure.wave,"open",lambda *_a,**_k:pytest.fail("Unreviewed audio decoded"))
    with pytest.raises(measure.Rejected,match="SHA-256"):
        measure.analyze(path,annotations)


@pytest.mark.parametrize("value", [0,-1,48001,True,False,16000.0,"16000",None])
def test_source_end_requires_a_strict_integer_in_the_recording(tmp_path,value):
    path,annotations = recording(tmp_path)
    annotations["source_speech_end_sample"] = value
    with pytest.raises(measure.Rejected,match="Source speech end"):
        measure.analyze(path,annotations)


@pytest.mark.parametrize("value", [-1,48000,True,False,24000.0,"24000",None])
def test_complete_listener_onset_requires_a_strict_integer_inside_the_recording(tmp_path,value):
    path,annotations = recording(tmp_path)
    annotations["listener_audio_start_sample"] = value
    with pytest.raises(measure.Rejected,match="onset index"):
        measure.analyze(path,annotations)


def test_source_end_may_equal_recording_length_and_output_may_start_at_zero(tmp_path):
    path,annotations = recording(tmp_path,source_end=48000,output_start=0)
    result = measure.analyze(path,annotations)
    assert result["latency_ms"] == -3000


@pytest.mark.parametrize("status", ["error","timeout"])
def test_unsuccessful_trial_keeps_null_latency_and_requires_no_output_signal(tmp_path,status):
    path,annotations = recording(tmp_path,output_signal=False)
    annotations.update(status=status,listener_audio_start_sample=None)
    result = measure.analyze(path,annotations)
    assert result["status"] == status and result["latency_ms"] is None
    assert result["listener_audio_start_sample"] is None and result["physical_playback_measured"] is False


@pytest.mark.parametrize("status", ["error","timeout"])
def test_failed_status_cannot_carry_a_successful_onset(tmp_path,status):
    path,annotations = recording(tmp_path)
    annotations["status"] = status
    with pytest.raises(measure.Rejected,match="failed outputs"):
        measure.analyze(path,annotations)


@pytest.mark.parametrize("field", ["capture_attested","annotations_reviewed","meaning_reviewed"])
@pytest.mark.parametrize("value", [1,0,"true","false",None])
def test_attestations_are_booleans_without_truthiness_coercion(tmp_path,field,value):
    path,annotations = recording(tmp_path)
    annotations[field] = value
    with pytest.raises(measure.Rejected,match="explicit booleans"):
        measure.analyze(path,annotations)


@pytest.mark.parametrize("capture,attested,reviewed,expected", [
    ("browser_render_dual_channel",True,True,False),
    ("acoustic_two_channel",False,True,False),
    ("acoustic_two_channel",True,False,False),
    ("electrical_loopback_two_channel",True,True,True),
])
def test_capture_flags_separate_browser_estimates_from_attested_output(tmp_path,capture,attested,reviewed,expected):
    path,annotations = recording(tmp_path)
    annotations.update(capture_kind=capture,capture_attested=attested,annotations_reviewed=reviewed)
    result = measure.analyze(path,annotations)
    assert result["physical_playback_measured"] is expected
    assert result["capture_provenance"] == result["provider_provenance"] == "operator_attested"
    assert result["screening_mode"] == "off" and result["voice_cloning"] is False


def test_duplicate_identity_survives_relabelling_and_review_flag_changes(tmp_path):
    path,annotations = recording(tmp_path)
    first = measure.analyze(path,annotations)
    annotations.update(trial_id="renamed-as-new-trial",condition="first_route",
                       capture_kind="browser_render_dual_channel",provider_kind="double",
                       meaning_reviewed=True,capture_attested=False)
    second = measure.analyze(path,annotations)
    assert first["observation_id"] == second["observation_id"]
    annotations["listener_audio_start_sample"] += 1
    third = measure.analyze(path,annotations)
    assert third["observation_id"] != first["observation_id"]


@pytest.mark.parametrize("channel", ["source","listener"])
def test_nonzero_channel_consistency_is_not_invented_for_silence(tmp_path,channel):
    path,annotations = recording(tmp_path,source_signal=channel!="source",output_signal=channel!="listener")
    with pytest.raises(measure.Rejected,match="signal"):
        measure.analyze(path,annotations)


@pytest.mark.parametrize("changes", [
    {"trial_id":"unsafe\nfield"},{"trial_id":"x"*65},{"trial_id":True},
    {"source_language":"xx"},{"target_language":"hi"},{"condition":"warm"},
    {"provider_kind":"unverified"},{"capture_kind":"separate_clocks"},
    {"voice_mode":"cloned"},{"status":"success"},
])
def test_metadata_must_use_supported_fixed_fields_without_unsafe_text(tmp_path,changes):
    path,annotations = recording(tmp_path)
    annotations.update(changes)
    with pytest.raises(measure.Rejected):
        measure.analyze(path,annotations)


@pytest.mark.parametrize("change", ["extra","missing"])
def test_annotation_schema_rejects_added_or_missing_fields(tmp_path,change):
    path,annotations = recording(tmp_path)
    if change == "extra": annotations["secret"] = "must-not-export"
    else: annotations.pop("meaning_reviewed")
    with pytest.raises(measure.Rejected,match="exactly"):
        measure.analyze(path,annotations)


@pytest.mark.parametrize("options", [{"channels":1},{"width":1},{"rate":7999},{"rate":96001}])
def test_unsupported_audio_format_is_rejected(tmp_path,options):
    path,annotations = recording(tmp_path,**options)
    with pytest.raises(measure.Rejected,match="two-channel PCM16"):
        measure.analyze(path,annotations)


def test_truncated_pcm_does_not_get_a_measurement(tmp_path):
    path,annotations = recording(tmp_path)
    path.write_bytes(path.read_bytes()[:-4])
    annotations["recording_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(measure.Rejected,match="incomplete sample"):
        measure.analyze(path,annotations)


def test_default_plan_never_reads_audio_annotations_or_opens_network(monkeypatch,capsys):
    def forbidden(*_args,**_kwargs): pytest.fail("Default plan performed runtime work")
    monkeypatch.setattr(measure,"analyze",forbidden)
    monkeypatch.setattr(measure.wave,"open",forbidden)
    monkeypatch.setattr(Path,"read_text",forbidden)
    monkeypatch.setattr(Path,"read_bytes",forbidden)
    monkeypatch.setattr(socket,"socket",forbidden)
    assert measure.main(["--wav","missing.wav","--annotations","missing.json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["provider_calls"] == 0 and result["hardware_capture_started"] is False
    assert result["plan_only"] is True and result["acceptance"] == "not_verified"
    assert result["signed_offsets"] is True


def test_cli_writes_fresh_observation_without_modifying_or_overwriting_evidence(tmp_path,capsys):
    path,annotations = recording(tmp_path)
    annotation_path = tmp_path / "annotations.json"
    annotation_path.write_text(json.dumps(annotations))
    output = tmp_path / "observation.json"
    argv = ["--analyze","--wav",str(path),"--annotations",str(annotation_path),"--output",str(output)]
    assert measure.main(argv) == 0
    result = json.loads(output.read_text())
    assert result["latency_ms"] == 500
    saved = output.read_bytes()
    assert measure.main(argv) == 1
    assert output.read_bytes() == saved
    assert "not imported" in capsys.readouterr().err
