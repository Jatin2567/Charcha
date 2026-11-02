import { useEffect, useState } from 'react';
import { phonePreview } from '../services/phonePreview';

export function PhonePreview({ file }: { file: File }) {
  const [enabled, setEnabled] = useState(false);
  const [noise, setNoise] = useState(false);
  const [urls, setUrls] = useState<string[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    setUrls([]);
    setError('');
    if (!enabled) return;
    let active = true;
    const links: string[] = [];
    void file
      .arrayBuffer()
      .then((data) => {
        if (!active) return;
        const narrowband = phonePreview(data, noise);
        links.push(URL.createObjectURL(file), URL.createObjectURL(narrowband));
        setUrls(links);
      })
      .catch(() => {
        if (active) setError('The phone-line preview could not be prepared.');
      });
    return () => {
      active = false;
      links.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [enabled, file, noise]);
  return (
    <div className="phone-preview">
      <button
        className="button secondary"
        aria-expanded={enabled}
        onClick={() => setEnabled(!enabled)}
      >
        {enabled ? 'Close phone-line preview' : 'Compare with an 8 kHz phone line'}
      </button>
      {enabled && (
        <>
          <label className="audio-lab-checkbox">
            <input
              type="checkbox"
              checked={noise}
              onChange={(event) => setNoise(event.target.checked)}
            />
            Add quiet background hiss
          </label>
          {urls.length === 2 && (
            <>
              <p>
                Original · 16 kHz
                <audio controls src={urls[0]} aria-label="Play original 16 kHz recording" />
              </p>
              <p>
                Phone line · 8 kHz
                <audio controls src={urls[1]} aria-label="Play phone-line preview" />
              </p>
            </>
          )}
          <small>
            Local 300–3400 Hz bandpass simulation. This preview uses PCM and stays in your browser.
            Recognition accuracy requires a separate test.
          </small>
          {error && <p role="status">{error}</p>}
        </>
      )}
    </div>
  );
}
