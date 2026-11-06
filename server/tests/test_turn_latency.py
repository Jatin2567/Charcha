"""Clock/association/authorization and local RTC doubles; no provider requests."""
import array
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from charcha.config import Settings
from charcha.models import Participant, PerformanceSample
from charcha.services.performance import performance_snapshot
from charcha.services.turn_latency import (BOUNDARY, TOPIC, LatencyObservation, SourceEndTracker,
                                         TurnLatency, register_turn_latency)
from charcha.store import Store
from charcha.transport.livekit import RoomTransport


def pcm(energy=5000):
    return array.array('h', [energy if i % 2 else -energy for i in range(320)]).tobytes()


def voiced(tracker, start):
    for offset in (0, 20, 40, 60):
        tracker.feed(pcm(), start + offset)
    for offset in range(80, 281, 20):
        tracker.feed(pcm(0), start + offset)


def test_source_end_uses_received_quiet_and_preserves_ambiguity():
    tracker = SourceEndTracker()
    voiced(tracker, 1000)
    value = tracker.take(1400)
    assert value['source_boundary'] == BOUNDARY
    assert value['source_end_status'] == 'energy_estimate'
    assert value['source_end_server_ms'] == 1060
    assert value['source_end_to_transcript_ms'] == 340
    assert tracker.take(1450)['source_end_server_ms'] is None
    voiced(tracker, 1500)
    voiced(tracker, 1850)
    assert tracker.take(2200)['source_end_status'] == 'ambiguous_source_boundary'


def test_source_gap_no_silence_and_overlap_never_invent_end():
    tracker = SourceEndTracker()
    for stamp in (1000, 1020, 1040):
        tracker.feed(pcm(), stamp)
    assert tracker.take(2000)['source_end_server_ms'] is None
    tracker.feed(pcm(0), 2100)
    assert tracker.take(2150)['source_end_status'] == 'source_discontinuity'
    voiced(tracker, 2200)
    for stamp in (2500, 2520, 2540):
        tracker.feed(pcm(), stamp)
    assert tracker.take(2600)['source_end_status'] == 'ambiguous_source_boundary'
    tracker.reset('source_audio_overflow')
    assert tracker.take(2700)['source_end_status'] == 'source_audio_overflow'


@pytest.fixture
def timings(monkeypatch):
    time = [1000.0]
    monkeypatch.setattr('charcha.services.turn_latency.clock_ms', lambda: time[0])
    store = Store(Settings(_env_file=None, mode='live'))
    state = store.create_room('Latency test')
    for pid, language in [('speaker', 'hi'), ('listener', 'ta'), ('other', 'bn')]:
        state.room.participants.append(Participant(id=pid, name=pid, language=language))
        store.issue_session(state, pid)
    service = TurnLatency(store)
    store.turn_latency = service
    context = {'utterance_id': 'turn-test', 'source_language': 'hi',
               'source_end_server_ms': 400.0, 'source_end_status': 'energy_estimate'}
    return store, state, service, time, context


def detected(marker, clock, **changes):
    return LatencyObservation(marker_id=marker['marker_id'], status='detected',
        **({'observed_server_ms': 1500.0, 'clock_id': clock['clock_id'], 'clock_rtt_ms': 40.0,
            'clock_age_ms': 500.0, 'poll_interval_ms': 100.0} | changes))


def test_turn_observation_is_scoped_single_use_and_has_uncertainty(timings):
    store, state, service, time, context = timings
    clock = service.clock(state.room.code, 'listener')
    marker = service.issue(state, 'speaker', 'ta', context)
    assert marker['track_name'] == 'translated:speaker:ta'
    time[0] = 1200
    service.first_pcm(marker['marker_id'])
    time[0] = 1550
    with pytest.raises(HTTPException) as denied:
        service.observe(state.room.code, 'other', detected(marker, clock))
    assert denied.value.status_code == 404
    row = service.observe(state.room.code, 'listener', detected(marker, clock))
    assert row['latency_ms'] == 1100 and row['uncertainty_ms'] == 140
    assert row['source_end_to_first_pcm_ms'] == 800
    assert row['client_reported'] and not row['physical_playback_measured']
    assert service.report(state.room.code, 'other')['samples'] == []
    with pytest.raises(HTTPException):
        service.observe(state.room.code, 'listener', detected(marker, clock))
    store.rooms.clear()
    assert service.report(state.room.code)['samples'] == [row]


def test_bad_clocks_future_observations_and_changed_language_are_rejected(timings):
    store, state, service, time, context = timings
    clock = service.clock(state.room.code, 'other')
    marker = service.issue(state, 'speaker', 'ta', context)
    service.first_pcm(marker['marker_id'])
    time[0] = 1550
    with pytest.raises(HTTPException) as wrong:
        service.observe(state.room.code, 'listener', detected(marker, clock))
    assert wrong.value.status_code == 422
    clock = service.clock(state.room.code, 'listener')
    with pytest.raises(HTTPException):
        service.observe(state.room.code, 'listener', detected(marker, clock, observed_server_ms=3000))
    state.room.participants[1].language = 'en'
    with pytest.raises(HTTPException) as changed:
        service.observe(state.room.code, 'listener', detected(marker, clock))
    assert changed.value.status_code == 409
    with pytest.raises(ValidationError):
        detected(marker, clock, poll_interval_ms=800)
    with pytest.raises(ValidationError):
        LatencyObservation(marker_id=marker['marker_id'], status='blocked',
                           observed_server_ms=1400, poll_interval_ms=100)


def test_unknown_source_and_expired_clock_have_no_made_up_latency(timings):
    _, state, service, time, context = timings
    clock = service.clock(state.room.code, 'listener')
    marker = service.issue(state, 'speaker', 'ta', context | {'source_end_server_ms': None})
    service.first_pcm(marker['marker_id'])
    time[0] = 1550
    row = service.observe(state.room.code, 'listener', detected(marker, clock))
    assert row['status'] == 'source_unavailable' and row['latency_ms'] is None
    marker = service.issue(state, 'speaker', 'ta', context)
    service.first_pcm(marker['marker_id'])
    time[0] = 62000
    with pytest.raises(HTTPException):
        service.observe(state.room.code, 'listener', detected(marker, clock, observed_server_ms=62000))
    time[0] = 125000
    assert service.report(state.room.code)['samples'][-1]['status'] == 'unreported'


def test_room_end_records_unanswered_observation_once(timings):
    _, state, service, _, context = timings
    service.issue(state, 'speaker', 'ta', context)
    service.finalize_room(state.room.code)
    service.finalize_room(state.room.code)
    rows = service.report(state.room.code)['samples']
    assert len(rows) == 1 and rows[0]['reason'] == 'meeting_ended_before_report'
    assert rows[0]['latency_ms'] is None and not service.markers


def test_performance_coverage_separates_provider_stt_from_source_interval(timings):
    _, state, _, _, _ = timings
    state.performance_samples.extend([
        PerformanceSample(utterance_id='a', source_language='hi', target_language='ta', input_kind='audio',
            measurement='server_first_pcm', total_ms=150, source_end_to_first_pcm_ms=700,
            source_end_to_transcript_ms=550, source_end_status='energy_estimate'),
        PerformanceSample(utterance_id='b', source_language='hi', target_language='ta', input_kind='audio',
            measurement='server_first_pcm', total_ms=200, stt_ms=20),
        PerformanceSample(utterance_id='c', source_language='hi', target_language='ta', input_kind='text',
            measurement='server_first_pcm', total_ms=100)])
    result = performance_snapshot(state)
    assert result['summary']['stt_measured_count'] == 1
    assert result['summary']['audio_sample_count'] == 2
    assert result['summary']['source_end_measured_count'] == 1
    assert result['summary']['source_end_to_first_pcm_p50_ms'] == 700
    assert result['measurement']['total_coverage'] == 'partial_when_stt_missing'


async def test_transport_marker_precedes_pcm_and_only_targets_listener(timings, monkeypatch):
    _, state, service, time, context = timings
    from livekit import rtc
    events = []
    transport = RoomTransport(service.store, state, None, None)
    source = SimpleNamespace(clear_queue=lambda: events.append('clear'),
        capture_frame=AsyncMock(side_effect=lambda frame: events.append('pcm')), wait_for_playout=AsyncMock())
    output = SimpleNamespace(source=source, sample_rate=24000, tts_active=False)
    transport._output = AsyncMock(return_value=output)
    transport._wait_for_listener = AsyncMock()
    transport._permissions = lambda: None
    transport._screening_allows_output = lambda _: True
    payloads = []
    async def publish(payload, **options):
        events.append('marker')
        payloads.append((json.loads(payload), options))
    transport.room = SimpleNamespace(local_participant=SimpleNamespace(publish_data=publish))
    def callback():
        events.append('callback')
    callback.latency_context = context
    async def chunks():
        yield b'\x10\x00' * 480
    await transport.prepare_output('speaker', 'ta')
    assert events == []
    await transport.speak('speaker', 'ta', chunks(), callback)
    assert events.index('marker') < events.index('pcm') < events.index('callback')
    marker, options = payloads[0]
    assert options['topic'] == TOPIC and options['reliable'] is True
    assert options['destination_identities'] == ['listener']
    assert service.markers[marker['marker_id']].first_pcm_ms == 1000
    assert not output.tts_active


def test_routes_require_exact_room_membership_and_only_return_own_observations(client):
    from conftest import auth, create_member
    app = client.app
    if not hasattr(app.state, 'turn_latency'):
        register_turn_latency(app, app.state.store, app.state.accounts)
    code, member = create_member(client)
    other_code, other = create_member(client)
    base = '/api/rooms/'+code
    assert client.get(base+'/latency-clock').status_code == 401
    assert client.get(base+'/latency-clock', headers=auth(other)).status_code == 403
    clock = client.get(base+'/latency-clock', headers=auth(member))
    assert clock.status_code == 200 and clock.json()['expires_in_ms'] == 60000
    state = app.state.store.room(code)
    source = Participant(id='source', name='Source', language='ta')
    state.room.participants.append(source)
    app.state.store.issue_session(state, source.id)
    service = app.state.turn_latency
    marker = service.issue(state, source.id, 'hi', {'utterance_id':'fixture-turn',
        'source_language':'ta','source_end_server_ms':None,'source_end_status':'no_source_boundary'})
    body = {'marker_id':marker['marker_id'],'status':'blocked','poll_interval_ms':100}
    assert client.post(base+'/latency-observations',json={**body,'audio':'forbidden'},headers=auth(member)).status_code == 422
    result = client.post(base+'/latency-observations',json=body,headers=auth(member))
    assert result.status_code == 200 and result.json()['latency_ms'] is None
    assert len(client.get(base+'/latency-observations',headers=auth(member)).json()['samples']) == 1
    assert client.get('/api/rooms/'+other_code+'/latency-observations',headers=auth(other)).json()['samples'] == []
