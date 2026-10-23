import type { AppEvent, Language, Membership, Room, Turn, VoiceMode } from '../types/domain';
const stamp = () => new Date().toISOString();
const id = () => crypto.randomUUID();
const rooms = new Map<string, Room>();
export function createDemoRoom(title: string): Room {
  const code = `demo-${id().slice(0, 8)}`;
  const room: Room = { id: id(), code, title, created_at: stamp(), mode: 'demo', participants: [] };
  rooms.set(code, room);
  return room;
}
export function getDemoRoom(code: string): Room {
  const existing = rooms.get(code);
  if (existing) return existing;
  const room: Room = {
    id: code,
    code,
    title: 'Across languages, together',
    created_at: stamp(),
    mode: 'demo',
    participants: [],
  };
  rooms.set(code, room);
  return room;
}
export function joinDemo(
  code: string,
  name: string,
  language: Language,
  voice_mode: VoiceMode,
): Membership {
  const room = getDemoRoom(code);
  const participant = {
    id: id(),
    name,
    language,
    voice_mode,
    muted: true,
    is_agent: false,
    is_demo: false,
    joined_at: stamp(),
  };
  room.participants = [
    participant,
    ...[
      { name: 'Arjun Mehta', language: 'hi' as Language },
      { name: 'Kavya Raman', language: 'ta' as Language },
      { name: 'Riya Sen', language: 'bn' as Language },
    ].map((p, i) => ({
      id: `sample-${i}`,
      name: p.name,
      language: p.language,
      voice_mode: 'standard' as const,
      muted: false,
      is_agent: false,
      is_demo: true,
      joined_at: stamp(),
    })),
  ];
  return { room, participant, session_token: `local-${id()}`, livekit: null, localDemo: true };
}
export const SCRIPTED_TURNS: Omit<Turn, 'id' | 'created_at' | 'confirmed_by' | 'status'>[] = [
  {
    speaker_id: 'sample-0',
    speaker_name: 'Arjun Mehta',
    source_language: 'hi',
    text: 'नमस्ते! क्या हम इस सप्ताह के ऑर्डर पर बात कर सकते हैं?',
    translations: {
      en: 'Hello! Can we discuss this week’s order?',
      ta: 'வணக்கம்! இந்த வார ஆர்டரைப் பற்றிப் பேசலாமா?',
      bn: 'নমস্কার! আমরা কি এই সপ্তাহের অর্ডার নিয়ে কথা বলতে পারি?',
    },
  },
  {
    speaker_id: 'sample-1',
    speaker_name: 'Kavya Raman',
    source_language: 'ta',
    text: 'ஆம். எங்களுக்கு 50 பெட்டிகள் தேவை, ஒவ்வொன்றும் ₹1,500.',
    translations: {
      en: 'Yes. We need 50 cartons at ₹1,500 each.',
      hi: 'हाँ। हमें 50 कार्टन चाहिए, हर कार्टन ₹1,500 का।',
      bn: 'হ্যাঁ। আমাদের 50টি কার্টন দরকার, প্রতিটি ₹1,500।',
    },
  },
  {
    speaker_id: 'sample-2',
    speaker_name: 'Riya Sen',
    source_language: 'bn',
    text: 'মোট ₹75,000। শুক্রবার পাঠানো সম্ভব হবে?',
    translations: {
      en: 'That is ₹75,000 in total. Is dispatch on Friday possible?',
      hi: 'कुल ₹75,000 होंगे। क्या शुक्रवार को भेजना संभव है?',
      ta: 'மொத்தம் ₹75,000. வெள்ளிக்கிழமை அனுப்ப முடியுமா?',
    },
  },
  {
    speaker_id: 'sample-0',
    speaker_name: 'Arjun Mehta',
    source_language: 'hi',
    text: 'जी, लेकिन आपकी पुष्टि मिलने के बाद ही भेजेंगे।',
    translations: {
      en: 'Yes, but we will dispatch only after your confirmation.',
      ta: 'ஆம், ஆனால் உங்கள் உறுதிப்படுத்தலுக்குப் பிறகுதான் அனுப்புவோம்.',
      bn: 'হ্যাঁ, তবে আপনার নিশ্চিতকরণ পাওয়ার পরেই পাঠাব।',
    },
  },
  {
    speaker_id: 'sample-1',
    speaker_name: 'Kavya Raman',
    source_language: 'ta',
    text: 'சரி. 50 பெட்டிகள், மொத்தம் ₹75,000. முகவரியை நான் அனுப்புகிறேன்.',
    translations: {
      en: 'Agreed. 50 cartons, ₹75,000 total. I will send the address.',
      hi: 'ठीक है। 50 कार्टन, कुल ₹75,000। मैं पता भेजती हूँ।',
      bn: 'ঠিক আছে। 50টি কার্টন, মোট ₹75,000। আমি ঠিকানাটি পাঠাচ্ছি।',
    },
  },
  {
    speaker_id: 'sample-2',
    speaker_name: 'Riya Sen',
    source_language: 'bn',
    text: 'ধন্যবাদ। পাঠানোর আগে আমরা সবাই তথ্য যাচাই করব।',
    translations: {
      en: 'Thank you. We will all check the details before dispatch.',
      hi: 'धन्यवाद। भेजने से पहले हम सभी विवरण जाँच लेंगे।',
      ta: 'நன்றி. அனுப்புவதற்கு முன் நாம் அனைவரும் விவரங்களைச் சரிபார்ப்போம்.',
    },
  },
];
export function demoEvent(type: string, payload: Record<string, unknown>): AppEvent {
  return { id: id(), type, timestamp: stamp(), payload };
}
export function makeDemoTurn(index: number): Turn {
  return {
    ...SCRIPTED_TURNS[index],
    id: `example-${index}`,
    created_at: stamp(),
    confirmed_by: [],
    status: 'complete',
  };
}
export function demoLookup(text: string, language: Language): string | null {
  const found = SCRIPTED_TURNS.find(
    (t) => t.text === text || Object.values(t.translations).includes(text),
  );
  return found
    ? found.source_language === language
      ? found.text
      : (found.translations[language] ?? null)
    : null;
}
