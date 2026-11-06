/** Browser WebRTC diagnostics only. No audio, addresses, tokens or transcript text. */
export interface TransportMetrics {
  measured_at: string;
  receiving_tracks: number;
  network_rtt_ms: number | null;
  jitter_ms: number | null;
  jitter_buffer_ms: number | null;
  packet_loss_percent: number | null;
  packets_received: number | null;
  packets_lost: number | null;
}
export type MetricStat = Record<string, unknown>;
const finite = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0;
const mean = (values: number[]) =>
  values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;

export function transportMetrics(
  reports: Iterable<MetricStat>,
  receivingTracks: number,
): TransportMetrics {
  // A report may be repeated by multiple track getters on the same peer connection.
  const unique = new Map<string, MetricStat>();
  for (const report of reports) {
    if (typeof report.id === 'string') unique.set(report.id, report);
  }
  const selected = new Set<string>();
  for (const report of unique.values()) {
    if (report.type === 'transport' && typeof report.selectedCandidatePairId === 'string')
      selected.add(report.selectedCandidatePairId);
  }
  const rtt: number[] = [];
  const jitter: number[] = [];
  const buffers: number[] = [];
  let received = 0;
  let lost = 0;
  let hasReceived = false;
  let hasLost = false;
  for (const report of unique.values()) {
    if (
      report.type === 'candidate-pair' &&
      (selected.has(report.id as string) ||
        (!selected.size && report.nominated === true && report.state === 'succeeded')) &&
      finite(report.currentRoundTripTime)
    )
      rtt.push(report.currentRoundTripTime * 1000);
    if (report.type !== 'inbound-rtp' || (report.kind ?? report.mediaType) !== 'audio') continue;
    if (finite(report.jitter)) jitter.push(report.jitter * 1000);
    if (
      finite(report.jitterBufferDelay) &&
      finite(report.jitterBufferEmittedCount) &&
      report.jitterBufferEmittedCount > 0
    )
      buffers.push((report.jitterBufferDelay / report.jitterBufferEmittedCount) * 1000);
    if (finite(report.packetsReceived)) {
      hasReceived = true;
      received += report.packetsReceived;
    }
    // RTCP can briefly report a negative cumulative loss after late packet arrival.
    if (typeof report.packetsLost === 'number' && Number.isFinite(report.packetsLost)) {
      hasLost = true;
      lost += Math.max(0, report.packetsLost);
    }
  }
  return {
    measured_at: new Date().toISOString(),
    receiving_tracks: receivingTracks,
    network_rtt_ms: rtt.length ? Math.max(...rtt) : null,
    jitter_ms: mean(jitter),
    jitter_buffer_ms: mean(buffers),
    packet_loss_percent:
      hasReceived && hasLost && received + lost > 0 ? (lost / (received + lost)) * 100 : null,
    packets_received: hasReceived ? received : null,
    packets_lost: hasLost ? lost : null,
  };
}

export function transportChannel(roomCode: string, participantId: string): string {
  return `charcha.transport.${roomCode}.${participantId}`;
}

export function isTransportMetrics(value: unknown): value is TransportMetrics {
  if (!value || typeof value !== 'object') return false;
  const row = value as Record<string, unknown>;
  return (
    typeof row.measured_at === 'string' &&
    Number.isFinite(Date.parse(row.measured_at)) &&
    finite(row.receiving_tracks) &&
    Number.isInteger(row.receiving_tracks) &&
    [
      'network_rtt_ms',
      'jitter_ms',
      'jitter_buffer_ms',
      'packet_loss_percent',
      'packets_received',
      'packets_lost',
    ].every((key) => row[key] === null || finite(row[key])) &&
    (row.packet_loss_percent === null || (row.packet_loss_percent as number) <= 100)
  );
}

/** Open metrics without unmounting the meeting, then sever the new tab's opener. */
export function openPerformancePage(sessionScope?: string | null): boolean {
  // Explicitly copy safe membership into the new same-origin tab. Modern target=_blank
  // links use noopener by default, which would lose sessionStorage membership.
  const destination = new URL(window.location.href);
  destination.hash = '/performance';
  const child = window.open(destination.toString(), '_blank');
  if (!child) return false;
  try {
    const key = sessionScope ? `charcha.membership.${sessionScope}` : 'charcha.membership';
    const member = sessionStorage.getItem(key);
    if (member) child.sessionStorage.setItem(key, member);
    child.opener = null;
    return true;
  } catch {
    child.close();
    return false;
  }
}
