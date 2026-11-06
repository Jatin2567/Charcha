export type UserFeedbackEntry = {
  id: string;
  name: string;
  role: string;
  feature: string;
  quote: string;
  initials: string;
  photoUrl?: string;
};

// Publish only feedback whose wording and attribution have been approved.
// Harsh's approval was confirmed by the project owner on 8 November 2026.
// No profile photo was supplied; the UI uses an initials avatar.
export const userFeedback: UserFeedbackEntry[] = [
  {
    id: 'harsh-vardhan',
    name: 'Harsh Vardhan',
    role: 'Software Engineer',
    feature: 'Voice cloning',
    quote:
      'The voice cloning made the conversation feel natural, as if I were hearing the other person’s own voice.',
    initials: 'HV',
  },
];
