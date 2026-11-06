import { Link } from 'react-router-dom';
import { AudioLines, ShieldCheck, Check, ArrowRight, Leaf } from 'lucide-react';
import { PageHeading, Badge } from '../components/ui';
import { VoiceEnrollment } from '../components/VoiceEnrollment';
import { useApp } from '../state/AppContext';
export function VoiceStudio() {
  const { membership } = useApp();
  return (
    <>
      <PageHeading
        eyebrow="THE HUMAN PART OF EVERY CONVERSATION"
        title="A voice that feels like you."
        description="Set up your own voice for interpreted meetings, with your consent. Your profile lasts only for this meeting."
        action={
          membership ? (
            <Link className="button secondary" to={`/room/${membership.room.code}`}>
              Back to conversation
              <ArrowRight size={15} />
            </Link>
          ) : undefined
        }
      />
      <div className="voice-grid">
        <section className="panel">
          <div className="panel-head">
            <h2>Your voice reference</h2>
            <Badge tone="neutral">Meeting voice</Badge>
          </div>
          <p className="panel-intro">
            Record 5–30 seconds of natural speech. A quiet room and your normal speaking voice work
            best.
          </p>
          <VoiceEnrollment />
        </section>
        <aside className="voice-guide">
          <div className="voice-quote">
            <span className="feature-icon green">
              <AudioLines size={23} />
            </span>
            <h2>
              New words.
              <br />A familiar voice.
            </h2>
            <p>Help the people on the other side hear the person behind the conversation.</p>
            <div className="voice-quote-lines">
              {[13, 27, 42, 20, 54, 35, 61, 29, 45, 24, 40, 18, 29, 13].map((h, i) => (
                <i key={i} style={{ height: h }} />
              ))}
            </div>
          </div>
          <section className="panel">
            <h3>A little guidance</h3>
            <div className="voice-guide-step">
              <span>01</span>
              <div>
                <strong>Make it your own</strong>
                <p>Read something naturally. Include a few different sentences and pauses.</p>
              </div>
            </div>
            <div className="voice-guide-step">
              <span>02</span>
              <div>
                <strong>Keep the room quiet</strong>
                <p>Avoid music, other speakers and heavy background noise.</p>
              </div>
            </div>
            <div className="voice-guide-step">
              <span>03</span>
              <div>
                <strong>Listen before you enroll</strong>
                <p>Preview the clip. Clear speech matters more than a perfect delivery.</p>
              </div>
            </div>
            <div className="divider" />
            <div className="voice-policy">
              <ShieldCheck size={20} />
              <p>Only enroll your own voice. You can delete your session profile at any time.</p>
            </div>
          </section>
        </aside>
      </div>
      <div className="voice-assurance">
        <Leaf size={16} />
        <span>Your voice is used for interpreted speech.</span>
        <Check size={14} />
        <span>You can listen without enrolling. Voice setup is required to speak in interpreted meetings.</span>
      </div>
    </>
  );
}
