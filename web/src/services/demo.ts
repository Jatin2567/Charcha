import type { AppEvent, Language, Membership, Room, Turn, VoiceMode } from '../types/domain';
import { isScriptedLanguage } from '../types/domain';
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
  if (!isScriptedLanguage(language))
    throw new Error(
      'Scripted examples cover Hindi, Tamil, Bengali and English. Other languages require live setup.',
    );
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
    text: 'कल सुबह 10 बजे सामुदायिक केंद्र के मुख्य दरवाजे पर मिलते हैं।',
    translations: {
      en: "Let us meet tomorrow at 10 in the morning at the community centre's main entrance.",
      ta: 'நாளை காலை 10 மணிக்கு சமூக மையத்தின் பிரதான நுழைவாயிலில் சந்திப்போம்.',
      bn: 'আগামীকাল সকাল 10টায় কমিউনিটি সেন্টারের প্রধান দরজায় দেখা করি।',
    },
  },
  {
    speaker_id: 'sample-1',
    speaker_name: 'Kavya Raman',
    source_language: 'ta',
    text: 'ஆம், நாளை காலை 10 மணிக்கு, இன்று இல்லை.',
    translations: {
      en: 'Yes, tomorrow at 10 in the morning, not today.',
      hi: 'हाँ, कल सुबह 10 बजे, आज नहीं।',
      bn: 'হ্যাঁ, আগামীকাল সকাল 10টায়, আজ নয়।',
    },
  },
  {
    speaker_id: 'sample-2',
    speaker_name: 'Riya Sen',
    source_language: 'bn',
    text: 'ঘরটি AM-204। দয়া করে Wi-Fi-এর নাম আবার বলুন।',
    translations: {
      en: 'The room is AM-204. Please repeat the Wi-Fi name.',
      hi: 'कमरा AM-204 है। कृपया Wi-Fi का नाम फिर से बताइए।',
      ta: 'அறை AM-204. தயவுசெய்து Wi-Fi பெயரை மீண்டும் சொல்லுங்கள்.',
    },
  },
  {
    speaker_id: 'sample-0',
    speaker_name: 'Arjun Mehta',
    source_language: 'hi',
    text: 'मेरे आने तक बैठक शुरू मत कीजिए।',
    translations: {
      en: 'Please do not start the meeting until I arrive.',
      ta: 'நான் வரும் வரை கூட்டத்தைத் தொடங்க வேண்டாம்.',
      bn: 'আমি না আসা পর্যন্ত সভা শুরু করবেন না।',
    },
  },
  {
    speaker_id: 'sample-1',
    speaker_name: 'Kavya Raman',
    source_language: 'ta',
    text: 'நான் இரண்டாவது தளத்தில் இருக்கிறேன், மூன்றாவது தளத்தில் இல்லை.',
    translations: {
      en: 'I am on the second floor, not the third.',
      hi: 'मैं दूसरी मंज़िल पर हूँ, तीसरी पर नहीं।',
      bn: 'আমি দ্বিতীয় তলায় আছি, তৃতীয় তলায় নয়।',
    },
  },
  {
    speaker_id: 'sample-2',
    speaker_name: 'Riya Sen',
    source_language: 'bn',
    text: 'প্রথমে বাঁ দিকে ঘুরুন, তারপর 200 মিটার সোজা যান।',
    translations: {
      en: 'First turn left, then go straight for 200 metres.',
      hi: 'पहले बाएँ मुड़िए, फिर 200 मीटर सीधे चलिए।',
      ta: 'முதலில் இடதுபுறம் திரும்பி, பிறகு 200 மீட்டர் நேராகச் செல்லுங்கள்.',
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
