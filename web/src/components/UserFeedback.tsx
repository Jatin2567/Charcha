import { AudioLines, Quote } from 'lucide-react';
import { userFeedback } from '../data/userFeedback';
import './UserFeedback.css';

export function UserFeedback() {
  if (!userFeedback.length) return null;

  return (
    <section className="user-feedback" aria-labelledby="user-feedback-heading">
      <div className="user-feedback-intro">
        <span className="eyebrow">USER FEEDBACK</span>
        <h2 id="user-feedback-heading">In their own words.</h2>
        <p>Experiences shared with permission, including what we can improve.</p>
      </div>
      <div className="user-feedback-list">
        {userFeedback.map((entry) => (
          <figure className="user-feedback-card" key={entry.id}>
            <div className="user-feedback-card-top">
              <Quote size={25} aria-hidden="true" />
              <span className="user-feedback-feature">
                <AudioLines size={15} aria-hidden="true" />
                {entry.feature}
              </span>
            </div>
            <blockquote>{entry.quote}</blockquote>
            <figcaption>
              {entry.photoUrl ? (
                <img
                  className="user-feedback-avatar"
                  src={entry.photoUrl}
                  alt=""
                  width={48}
                  height={48}
                  loading="lazy"
                />
              ) : (
                <span className="user-feedback-avatar" aria-hidden="true">
                  {entry.initials}
                </span>
              )}
              <span className="user-feedback-person">
                <strong>{entry.name}</strong>
                <span>{entry.role}</span>
              </span>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
