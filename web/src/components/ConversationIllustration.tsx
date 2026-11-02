import './ConversationIllustration.css';

/** Detailed artwork is reserved for large, decorative placements. */
export function ConversationIllustration() {
  return (
    <img
      className="conversation-illustration"
      src={`${import.meta.env.BASE_URL}artha-mesh-mark-transparent.png`}
      alt=""
      width={1254}
      height={1254}
      decoding="async"
    />
  );
}
