import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Badge } from './ui';
import './LaterWork.css';

export function LaterWork({ children }: { children?: ReactNode }) {
  return (
    <details className="panel later-work">
      <summary>
        <strong>Later phases · optional research</strong>
        <Badge tone="neutral">Outside the current call setup</Badge>
      </summary>
      <div className="later-work-body">
        <p>
          Live conferencing uses standard voices. VoiceShield can monitor original microphone audio
          with a local experimental classifier. Deepfake accuracy validation, latency optimization
          and voice cloning are later work.
        </p>
        <p>
          The research targets below do not gate joining, camera sharing or an approved
          interpretation flow. Historical tests keep their original measurement boundaries.
        </p>
        <Link className="text-link" to="/audio-lab">
          Open the optional audio research lab →
        </Link>
        {children}
      </div>
    </details>
  );
}
