import conferencePlan from './fiveLanguagePlan.json';

export const TEST_STAGES = [
  {
    id: 'local-audio',
    title: 'Local audio',
    subtitle: 'Start here · no speech API',
    setup:
      'Run npm run dev:local. Open the printed local address. Create a room and join its invitation in a separate browser profile or private window, with different display names. Use headphones; unmute only the speaking participant.',
    gate: 'Both directions are audible, mute stops audio, and leaving removes the participant. This checks original audio only.',
    mode: 'transport',
  },
  {
    id: 'device-check',
    title: 'Two-device audio',
    subtitle: 'Free · real microphones and cameras',
    setup:
      'Use two computers with headphones and a person on each. Open the same trusted HTTPS invitation on both; localhost cannot reach this laptop from another device. Use the prepared original-audio LAN stack, not live interpretation mode. Confirm the workspace says Original audio / Raw audio test, join muted, then enable each device intentionally. Follow docs/TWO_DEVICE_TESTING.md for the certificate and media setup; do not bypass a browser security warning.',
    gate: 'Both directions, sustained playback, camera on/off and explicit reconnect work on the actual devices. Save only outcomes you observed. These checks use no speech API and do not verify translation.',
    mode: 'transport',
  },
  {
    id: 'interpretation',
    title: 'Two-user interpretation',
    subtitle: 'Standard voices · local first',
    setup:
      'Requires the Gnani speech configuration and an actual Evon endpoint with its model name. Switch to live mode only for an explicitly approved, bounded test. Choose Hindi for A and Tamil for B; test both directions. English lines below describe the intended meaning: each person should say them naturally in their selected source language.',
    gate: 'A bilingual reviewer accepts meaning in both directions, each listener hears only the intended translated audio, and failures remain visible.',
    mode: 'live',
  },
  {
    id: 'five-language',
    title: 'Five-language calls',
    subtitle: '20 directions · listener review',
    setup:
      'Choose a direction below. Both people join the same room with standard voices and their own language selected. Read the source phrase once. Ask the listener to repeat the key details before showing the transcript. Use an operator-approved allowance for live speech.',
    gate: 'Record the listener’s answer, whether names, numbers and corrections survived, and any unexpected audio. Each direction has its own result. A received audio frame alone cannot pass this review.',
    mode: 'live',
  },
  {
    id: 'second-device',
    title: 'Second device',
    subtitle: 'Secure connection · same scripts',
    setup:
      'Repeat the accepted two-user scripts on a second device using trusted HTTPS/WSS addresses for the app, API and media. A localhost invitation points to that device itself. Confirm the secure connection and media reachability before speaking.',
    gate: 'Both microphones and speakers work on the actual devices, with no self echo, original double playback or silent translated track.',
    mode: 'live',
  },
  {
    id: 'sites',
    title: 'Hosted interface',
    subtitle: 'Sites + reachable backend',
    setup:
      'After local checks pass, use the Sites frontend with the same reachable HTTPS API and WSS/media service. Sites hosts the interface; the Python agent and LiveKit need their own running server. Use an explicit allowed frontend origin.',
    gate: 'Repeat the second-device checks from the hosted interface. Opening the static preview alone does not establish live audio or translation.',
    mode: 'live',
  },
  {
    id: 'multi-party',
    title: 'Group calls',
    subtitle: 'Three to five participants',
    setup:
      'After two-device checks, start with three independent sessions. Add Telugu and Marathi for the five-person script. Use headphones and standard voices. A live group call needs its own reviewed allowance for each distinct target language.',
    gate: 'Each listener hears the other speakers in their chosen language. Check self echo, overlapping turns, duplicated translations and stale output after someone leaves.',
    mode: 'live',
  },
  {
    id: 'cloning',
    title: 'Voice cloning',
    subtitle: 'Deferred until earlier gates pass',
    setup:
      'Use only each consenting participant’s own spoken reference. Approve enrollment and synthesis as a separate test. Compare the same sentence with the standard voice, then assess similarity, intelligibility and extra delay.',
    gate: 'Consent, enrollment, playback, deletion and the return to a standard voice are verified. Voice similarity is reviewed by people; it is not inferred from an embedding response.',
    mode: 'live',
  },
] as const;
export type TestStageId = (typeof TEST_STAGES)[number]['id'];
export interface TestScenario {
  id: string;
  title: string;
  sourceLanguage?: string;
  focus: string;
  stages: TestStageId[];
  script: string[];
  expected: string[];
}
const languageStages: TestStageId[] = ['interpretation', 'second-device', 'sites'];
const mixedPhrases: Record<string, [string, string]> = {
  hi: [
    'WhatsApp पर दस बजे का reminder लगाना, ग्यारह बजे का नहीं।',
    'The app is WhatsApp. Set the reminder for ten and reject eleven.',
  ],
  ta: [
    'Blue notebook எடுத்துட்டு வா, red notebook வேண்டாம்.',
    'Bring the blue notebook. The red notebook is explicitly rejected.',
  ],
  bn: [
    'কাল সকাল নটায় library-তে দেখা হবে, আজ নয়।',
    'Meet at the library tomorrow morning at nine. Today is rejected.',
  ],
  te: [
    'Water bottle లో ఒకటిన్నర లీటర్లు పోయాలి, నూట యాభై మిల్లీలీటర్లు కాదు.',
    'Fill the bottle with 1.5 litres. Reject 150 millilitres.',
  ],
  mr: [
    'काल संध्याकाळी park मध्ये भेटलो. आजचा plan अजून ठरलेला नाही.',
    'The park meeting happened yesterday evening. Today’s plan is still undecided.',
  ],
};
const reviewLanguages = Object.fromEntries(
  conferencePlan.languages.map((language) => [language.code, language.name]),
);
export const TEST_SCENARIOS: TestScenario[] = [
  ...conferencePlan.routes.map((route): TestScenario => {
    const [phrase, meaning] = mixedPhrases[route.source_language];
    return {
      id: `review-${route.source_language}-${route.target_language}`,
      sourceLanguage: route.source_language,
      title: `${reviewLanguages[route.source_language]} → ${reviewLanguages[route.target_language]}`,
      stages: ['five-language'],
      focus: 'Code-mixed speech and listener understanding',
      script: [
        phrase,
        'Ask the listener to repeat the meaning in their own words. Then compare the source caption, translated caption and received speech.',
      ],
      expected: [
        meaning,
        'Accept natural wording. Mark a changed detail, silent output, doubled original or wrong listening language as a failure.',
      ],
    };
  }),
  {
    id: 'device-permissions',
    title: 'Recover from denied microphone access',
    focus: 'Permission recovery without unexpected capture',
    stages: ['device-check'],
    script: [
      'A leaves the microphone off. B joins with microphone permission blocked and tries to unmute.',
      'B uses the browser’s site settings to allow the microphone, then reconnects media and explicitly unmutes. B says: “I can hear you. Can you hear me?”',
    ],
    expected: [
      'The denial is visible; A does not hear B and no microphone remains active.',
      'Reconnection keeps capture off until B unmutes. Both people hear the original speech clearly, without an API request.',
    ],
  },
  {
    id: 'device-sustained',
    title: 'Keep a conversation going',
    focus: 'Five-minute playback and mute reliability',
    stages: ['device-check'],
    script: [
      'Talk for five minutes, taking turns about a weekend plan, a favourite meal and a recent journey.',
      'Every minute, each person mutes and unmutes intentionally. Note any silence, repeated words, cuts or echo.',
    ],
    expected: [
      'Original audio stays audible in both directions throughout the actual test, with no self echo or growing backlog.',
      'Mute stops new speech reaching the other device. Mark Fail if sound drops or a muted device continues to transmit.',
    ],
  },
  {
    id: 'device-reconnect',
    title: 'Reconnect after losing the network',
    focus: 'Recovery with microphone and camera off',
    stages: ['device-check'],
    script: [
      'A briefly disconnects Wi-Fi, then reconnects to the same trusted network. B stays in the room.',
      'A checks the connection state, uses Reconnect media if needed, and explicitly enables the microphone again. Say: “I am back in the room.”',
    ],
    expected: [
      'The interrupted connection is visible. Recovery never silently restarts A’s microphone or camera.',
      'After deliberate unmute, B hears the new phrase once. No stale buffered speech, duplicate participant or unexpected video remains.',
    ],
  },
  {
    id: 'device-camera',
    title: 'Share and stop camera video',
    focus: 'Video delivery and hardware release',
    stages: ['device-check'],
    script: [
      'A turns the camera on, waves, then turns it off while both continue speaking. Repeat with B.',
      'Leave the room on one device and check its camera and microphone indicators.',
    ],
    expected: [
      'The other device sees the correct live camera tile. Turning video off removes the picture and preserves audio.',
      'Leaving releases that device’s microphone and camera. A frozen picture or continued capture is a failure.',
    ],
  },
  {
    id: 'device-overlap',
    title: 'Speak together, then take turns',
    focus: 'Two-source mixing and self-echo checks',
    stages: ['device-check'],
    script: [
      'With headphones, A counts one to five while B says the days of the week. Stop after a short overlap.',
      'Repeat one at a time, then B leaves and rejoins using the invitation.',
    ],
    expected: [
      'Each person hears the other, with no self audio or repeated track. Record overlap intelligibility honestly.',
      'The joined membership works without duplicate sound. This checks two original-audio sources, not live translation capacity.',
    ],
  },
  {
    id: 'device-input',
    title: 'Change or disconnect a microphone',
    focus: 'Deliberate device selection and capture-off recovery',
    stages: ['device-check'],
    script: [
      'While connected, A selects another available microphone in room Settings. If available, unplug a USB headset during a separate attempt.',
      'Confirm capture is off, select the intended device, then unmute and say: “This is the selected microphone.” If no alternate device is available, mark Blocked.',
    ],
    expected: [
      'Changing or losing the input stops capture. The browser does not silently start a different microphone.',
      'Only the deliberately selected device is shared after unmute. Record any required browser/device recovery.',
    ],
  },
  {
    id: 'greeting',
    title: 'Say hello, then reply',
    focus: 'Audio in both directions',
    stages: ['local-audio', ...languageStages],
    script: [
      'A: “नमस्ते! क्या मेरी आवाज़ साफ़ सुनाई दे रही है?” (Hello! Can you hear me clearly?)',
      'B: “ஆம், தெளிவாகக் கேட்கிறது. உங்களுக்கு என் குரல் கேட்கிறதா?” (Yes, clearly. Can you hear my voice?)',
    ],
    expected: [
      'Local audio: each listener hears the other person’s original language, without hearing their own voice.',
      'Interpretation stages: both questions and the affirmative reply keep their meaning; each listener hears their selected language.',
    ],
  },
  {
    id: 'mute-leave',
    title: 'Mute, resume and leave',
    focus: 'Control and cleanup',
    stages: ['local-audio', ...languageStages],
    script: [
      'A says “The blue notebook is on the table”, mutes, then repeats it while muted.',
      'A unmutes and says “Now I am speaking again”. B replies, then leaves the room.',
    ],
    expected: [
      'B hears no new words spoken while A is muted; already buffered audio may finish.',
      'Speech resumes after unmute. The departing participant disappears and produces no new audio. A does not hear their own microphone.',
    ],
  },
  {
    id: 'negation',
    title: 'Keep the “not”',
    focus: 'Negation and correction',
    stages: languageStages,
    script: [
      'A: “मुझे लाल किताब नहीं, नीली किताब चाहिए।” (I want the blue book, not the red book.)',
      'B repeats which book A wants before replying.',
    ],
    expected: [
      'Blue remains the requested colour and red remains rejected. Losing or reversing “not” fails this check.',
      'A reviewer compares the source transcript, translated text and audible reply to locate any recognition, translation or synthesis error.',
    ],
  },
  {
    id: 'time',
    title: 'Correct the meeting time',
    focus: 'Time and correction',
    stages: languageStages,
    script: [
      'A: “कल शाम साढ़े छह बजे मिलते हैं, साढ़े पाँच बजे नहीं।” (Let us meet tomorrow evening at 6:30, not 5:30.)',
      'B asks “Tomorrow evening at 6:30?” A confirms.',
    ],
    expected: [
      'Tomorrow, evening, 6:30 and rejected 5:30 all survive. No date or time zone is invented.',
      'Review both directions and the final confirmation; a fluent-sounding wrong time fails.',
    ],
  },
  {
    id: 'units',
    title: 'Check a number and its unit',
    focus: 'Decimals, units and alternatives',
    stages: languageStages,
    script: [
      'A: “डेढ़ लीटर पानी लाना, डेढ़ सौ मिलीलीटर नहीं।” (Bring 1.5 litres of water, not 150 millilitres.)',
      'B repeats the amount and unit.',
    ],
    expected: [
      'The requested quantity remains 1.5 litres; 150 millilitres remains rejected.',
      'Equivalent natural wording is acceptable. Changing the quantity, unit or correction fails.',
    ],
  },
  {
    id: 'question',
    title: 'A question stays a question',
    focus: 'Intent and politeness',
    stages: languageStages,
    script: [
      'A: “क्या आप खिड़की बंद कर सकते हैं?” (Could you close the window?)',
      'B: “இப்போதே ஜன்னலை மூடவா?” (Shall I close the window now?)',
    ],
    expected: [
      'The request does not become “I closed the window” or a claim that it is already closed.',
      'The reply remains a question about doing it now. Check meaning as well as natural speech.',
    ],
  },
  {
    id: 'code-mix',
    title: 'A familiar mixed-language message',
    focus: 'Code mixing and named identifiers',
    stages: languageStages,
    script: [
      'A: “Room AM-204 में मिलते हैं। Wi-Fi का नाम Lotus Guest है।” (Meet in Room AM-204. The Wi-Fi name is Lotus Guest.)',
      'B repeats the room code and network name.',
    ],
    expected: [
      'AM-204 and Lotus Guest remain identifiable. The system does not translate the network name into a different identifier.',
      'Inspect recognition separately if letters or digits are misheard; do not accept a plausible substitute.',
    ],
  },
  {
    id: 'ambiguity',
    title: 'Clarify an ambiguous word',
    focus: 'Context without invented certainty',
    stages: languageStages,
    script: [
      'A first says “कल मिलते हैं।” (See you tomorrow in this context.) Then says “कल मैं पुस्तकालय गया था।” (I went to the library yesterday.)',
      'B checks whether each use of “कल” means tomorrow or yesterday; A clarifies if needed.',
    ],
    expected: [
      'Future and past context are preserved. A clarification should repair uncertainty instead of silently inventing a date.',
      'A source-only ambiguous phrase has no single compulsory translation. Record ambiguity and whether clarification resolved it.',
    ],
  },
  {
    id: 'recovery',
    title: 'Disconnect between two short turns',
    focus: 'Visible failure and recovery',
    stages: languageStages,
    script: [
      'Finish a short sentence, mute both microphones, then briefly interrupt one browser’s network.',
      'Restore the connection, use reconnect if prompted, then send “We are back. The library closes at seven.”',
    ],
    expected: [
      'The interface shows a disconnect or recovery state instead of claiming a completed translation.',
      'The new sentence arrives once after recovery. Missing speech during the outage is reported as missing, never marked passed by a timing graph.',
    ],
  },
  {
    id: 'six-routes',
    title: 'One sentence from each speaker',
    focus: 'All six directed routes',
    stages: ['multi-party'],
    script: [
      'A in Hindi: “पार्क का गेट सात बजे खुलता है।” (The park gate opens at seven.)',
      'B in Tamil: “நான் நீல நிறத் தண்ணீர் பாட்டிலைக் கொண்டு வருகிறேன்.” (I am bringing the blue water bottle.)',
      'C in Bengali: “আমরা লাইব্রেরির সামনে দেখা করব।” (We will meet in front of the library.)',
    ],
    expected: [
      'Record A→B, A→C, B→A, B→C, C→A and C→B separately in the notes. All six meanings must be reviewed.',
      'Each listener receives two other speakers in their listening language. No self track, wrong-language track or duplicated source audio is accepted.',
    ],
  },
  {
    id: 'five-person-fan-out',
    title: 'Five listeners’ languages in one room',
    focus: 'Twenty directed deliveries',
    stages: ['multi-party'],
    script: [
      'Join five sessions using Hindi, Tamil, Bengali, Telugu and Marathi. Keep everyone muted until it is their turn. In each language, use the matching everyday phrase from Five-language calls.',
      'For each source, have the four other participants record the detail they heard. Then have two participants select Tamil and repeat one short phrase under a separate allowance.',
    ],
    expected: [
      'With five distinct languages each turn needs one recognition stream and four translated outputs. No speaker hears their own output. Check all twenty listener answers separately.',
      'Listeners who share a language hear the same translated track. Review a missing or duplicate route before testing overlapping speech.',
    ],
  },
  {
    id: 'overlap',
    title: 'Interrupt, then take turns',
    focus: 'Concurrency and stale output',
    stages: ['multi-party'],
    script: [
      'A and B begin two short sentences at once; C listens. Then all three repeat one at a time.',
      'Mute or remove one participant before their next turn.',
    ],
    expected: [
      'Observe overlap intelligibility and queueing; record delay per speaker, without assuming simultaneous speech will sound clear.',
      'No self echo, incorrect speaker attribution, new muted speech or new output after a participant leaves. Any failure blocks this gate.',
    ],
  },
  {
    id: 'clone-comparison',
    title: 'Compare a consenting voice',
    focus: 'Similarity, clarity and deletion',
    stages: ['cloning'],
    script: [
      'After a separate approval, enroll 5–30 seconds of your own natural speech. Compare “The weather is pleasant today” in standard and personal voice.',
      'Delete the session profile and repeat using a standard voice.',
    ],
    expected: [
      'Listeners review identity resemblance and intelligibility separately. Capture the additional measured delay where available.',
      'Enrollment cannot happen without consent. Deletion removes the profile and standard voice works afterward. No cloned-voice acceptance is inferred from HTTP success.',
    ],
  },
];
