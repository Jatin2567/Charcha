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
// Sathvika's publication consent was also confirmed by the project owner.
// Keep her complete feedback, including the observation about response latency.
// No profile photos were supplied; the UI uses initials avatars.
export const userFeedback: UserFeedbackEntry[] = [
  {
    id: 'sathvika',
    name: 'Sathvika',
    role: 'Tech student · Telugu speaker',
    feature: 'Multilingual conversations',
    quote:
      'The platform provides a really useful way to communicate with people who speak different languages through both text and voice translation. I liked how it makes conversations more accessible and helps people understand each other better. The experience was engaging and easy to follow, although there is some scope to improve response latency. Overall, it’s a useful platform that can help people connect without language barriers.',
    initials: 'S',
  },
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
