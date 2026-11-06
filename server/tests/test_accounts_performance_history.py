"""Persistent report lifecycle and account isolation; no live providers."""
import json
import sqlite3
import time

from charcha.accounts import COOKIE
from charcha.models import PerformanceSample, Turn
from charcha.services.performance_history import PerformanceHistory
from charcha.services.listener_metrics import PendingProbe
from test_accounts import site, identity, JOIN


def joined(site, subject="host"):
    app, client = site
    cookie = identity(site, subject)
    room = client.post('/api/rooms', json={'title': 'Planning the weekend'}).json()
    member = client.post(f"/api/rooms/{room['code']}/join", json=JOIN).json()
    return room['code'], member, cookie


def sample(state):
    state.performance_samples.append(PerformanceSample(utterance_id='test-utterance',
        source_language='hi', target_language='ta', input_kind='audio',
        measurement='server_first_pcm', total_ms=123, stt_ms=20, mt_ms=35, tts_first_pcm_ms=68))


def leave(client, code, member):
    return client.post(f'/api/rooms/{code}/leave',
        json={'participant_id': member['participant']['id']},
        headers={'Authorization': 'Bearer '+member['session_token']})


CONNECTION = {'measured_at': '2026-11-06T07:00:00Z', 'receiving_tracks': 1,
              'network_rtt_ms': 42, 'jitter_ms': 4, 'jitter_buffer_ms': None,
              'packet_loss_percent': 0, 'packets_received': 100, 'packets_lost': 0}


def test_report_survives_leave_new_login_and_disk_reopen_without_transcript(site):
    app, client = site
    assert client.get('/api/account/performance-history').status_code == 401
    code, member, _ = joined(site)
    state = app.state.store.room(code)
    state.turns.append(Turn(speaker_id='test-speaker', speaker_name='Private spoken name',
                           source_language='hi', text='Private transcript must never be archived'))
    sample(state)
    response = client.post(f'/api/rooms/{code}/connection-metrics', json=CONNECTION,
                           headers={'Authorization': 'Bearer '+member['session_token']})
    assert response.status_code == 200
    assert client.get('/api/account/call-performance').json()['view'] == 'live'
    assert leave(client, code, member).status_code == 200
    report = client.get('/api/account/call-performance').json()
    assert report['view'] == 'saved' and report['status'] == 'completed'
    assert report['summary']['p50_ms'] == 123 and report['connection']['network_rtt_ms'] == 42
    assert len(client.get('/api/account/performance-history').json()['reports']) == 1
    assert client.portal.call(app.state.performance_history.flush)
    identity(site, 'host')  # A new account session, same authenticated OIDC subject.
    assert client.get('/api/account/performance-history/'+state.room.id).json()['summary']['p95_ms'] == 123
    history = PerformanceHistory(app.state.settings, app.state.listener_metrics)
    history.initialize()
    app.state.store.rooms.clear()
    assert client.get('/api/account/call-performance').json()['summary']['p50_ms'] == 123
    text = json.dumps(report)
    assert member['session_token'] not in text
    assert 'speaker_name' not in text and 'embedding' not in text
    assert 'Private spoken name' not in text and 'Private transcript must never be archived' not in text


def test_unrelated_account_and_admin_cannot_read_another_meeting(site):
    app, client = site
    code, member, _ = joined(site)
    report_id = app.state.store.room(code).room.id
    leave(client, code, member)
    for subject, admin in [('outsider', False), ('operator', True)]:
        identity(site, subject, admin=admin)
        assert client.get('/api/account/performance-history').json()['reports'] == []
        assert client.get('/api/account/call-performance').json() is None
        assert client.get('/api/account/performance-history/'+report_id).status_code == 404


def test_guest_history_requires_admission_and_receiver_data_stays_listener_private(site):
    app, client = site
    code, host_member, host_cookie = joined(site)
    base = '/api/rooms/'+code
    guest_cookie = identity(site, 'guest')
    client.post(base+'/admission')
    assert client.get('/api/account/performance-history').json()['reports'] == []
    client.cookies.set(COOKIE, host_cookie)
    [entry] = client.get(base+'/admission/requests').json()['requests']
    client.post(base+'/admission/requests/'+entry['id'], json={'decision':'approve'})
    client.cookies.set(COOKIE, guest_cookie)
    guest_member = client.post(base+'/join', json=JOIN).json()
    state = app.state.store.room(code)
    for member in (host_member, guest_member):
        pid = member['participant']['id']
        probe = PendingProbe('probe-'+pid, code, pid, time.monotonic()+30)
        app.state.listener_metrics._append(probe, 'detected', elapsed_ms=80, poll_interval_ms=20)
        # Pending conversation markers must become explicit unreported records
        # at meeting end, and each listener sees only their own observation.
        marker = app.state.store.turn_latency.issue(state, pid, 'hi',
            {'utterance_id':'marker-'+pid, 'source_language':'hi'})
        assert marker is not None
    app.state.service.save_performance(state)
    report = client.get('/api/account/performance-history/'+state.room.id).json()
    assert len(report['receiver_audio']['samples']) == 1
    assert report['receiver_audio']['samples'][0]['listener_id'] == guest_member['participant']['id']
    assert leave(client, code, guest_member).status_code == 200
    assert client.get('/api/account/call-performance').json()['status'] == 'active'
    client.cookies.set(COOKIE, host_cookie)
    leave(client, code, host_member)
    client.cookies.set(COOKIE, guest_cookie)
    completed = client.get('/api/account/call-performance').json()
    assert completed['status'] == 'completed'
    assert len(completed['turn_latency']['samples']) == 1
    observation = completed['turn_latency']['samples'][0]
    assert observation['listener_id'] == guest_member['participant']['id']
    assert observation['status'] == 'unreported' and observation['latency_ms'] is None


def test_report_saved_on_expiry_and_interrupted_after_restart(site):
    app, client = site
    code, member, _ = joined(site)
    state = app.state.store.room(code)
    sample(state)
    app.state.service.save_performance(state)
    assert client.portal.call(app.state.performance_history.flush)
    app.state.performance_history.initialize()
    saved = client.get('/api/account/performance-history/'+state.room.id).json()
    assert saved['status'] == 'interrupted' and saved['ended_at'] is None
    state.expires_at = time.time()-1
    # Creating the next room runs the real expiry cleanup path.
    assert client.post('/api/rooms', json={'title': 'Next meeting'}).status_code == 201
    assert client.get('/api/account/call-performance').json()['status'] == 'completed'


def test_missing_timings_stay_null_and_connection_rejects_extra_or_other_seat_data(site):
    app, client = site
    code, member, _ = joined(site)
    auth = {'Authorization': 'Bearer '+member['session_token']}
    route = f'/api/rooms/{code}/connection-metrics'
    assert client.post(route, json={**CONNECTION, 'audio': 'not allowed'}, headers=auth).status_code == 422
    identity(site, 'outsider')
    assert client.post(route, json=CONNECTION, headers=auth).status_code == 403
    identity(site, 'host')
    report = client.get('/api/account/performance-history/'+app.state.store.room(code).room.id).json()
    assert report['summary']['p50_ms'] is None and report['connection'] is None


def test_retention_deletes_old_reports_and_reader_grants(site):
    app, client = site
    code, member, _ = joined(site)
    report_id = app.state.store.room(code).room.id
    leave(client, code, member)
    assert client.portal.call(app.state.performance_history.flush)
    with sqlite3.connect(app.state.performance_history.path) as db:
        db.execute('UPDATE reports SET updated=?', (time.time()-91*86400,))
    assert client.get('/api/account/performance-history').json()['reports'] == []
    assert client.get('/api/account/performance-history/'+report_id).status_code == 404
