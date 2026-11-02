# Five-language real-speech collection kit

Prepared 29 October 2026. **Start with 60 original clips: 30 live human recordings and 30 standard, non-cloned AI recordings.** These are collection and error-discovery tests. They are not enough on their own to prove general accuracy or justify shortening the live detector's window. No API generation, GPU rental or voice cloning is required or authorized by this kit.

**Public-data alternative:** the [FLEURS human-speech pilot](PUBLIC_HUMAN_SCREENING.md)
now supplies 50 public human readings across all five languages, so you do not
need to record the human half to start local false-alarm testing. That separate
manifest preserves public-licence provenance and unknown speaker identities; do
not relabel the public clips as personally consented recordings in this kit.
The matched human/AI recording protocol below remains useful for later controlled
tests and real-microphone coverage.

## Exactly what to collect

| Language | Code | Human originals | AI originals | Total |
| --- | --- | ---: | ---: | ---: |
| Hindi | hi | 6 | 6 | 12 |
| Tamil | ta | 6 | 6 | 12 |
| Bengali | bn | 6 | 6 | 12 |
| Telugu | te | 6 | 6 | 12 |
| Marathi | mr | 6 | 6 | 12 |
| Total | | 30 | 30 | 60 |

For each language, use these four roles. A and B must be different actual identities, not different filenames for the same voice.

| Role | Source | Read these three scripts | Split | Example filenames |
| --- | --- | --- | --- | --- |
| HA | Human speaker A, live microphone | C01, C02, C03 | Calibration/preparation | `hi_HA_C01.wav`, `hi_HA_C02.wav`, `hi_HA_C03.wav` |
| HB | Different human speaker B, live microphone | E01, E02, E03 | Held-out evaluation | `hi_HB_E01.wav`, `hi_HB_E02.wav`, `hi_HB_E03.wav` |
| AA | Standard AI voice A, no cloning | C01, C02, C03 | Calibration/preparation | `hi_AA_C01.wav`, `hi_AA_C02.wav`, `hi_AA_C03.wav` |
| AB | Different standard AI voice B, no cloning | E01, E02, E03 | Held-out evaluation | `hi_AB_E01.wav`, `hi_AB_E02.wav`, `hi_AB_E03.wav` |

Replace `hi` with `ta`, `bn`, `te` or `mr` for the other languages. The generated CSV lists every exact filename and its text. There are two human speaker assignments and two stock AI voice assignments per language. A fluent multilingual person may cover more than one language, but must keep the same anonymous identity and **one global split** throughout: never A in one language and B in another. Apply the same rule to multilingual AI voice identities.

The human and AI sources read the same text within each split. Evaluation uses different wording from calibration. Read the native scripts below naturally. A fluent speaker must review the script and English meaning before collection; these are drafts. If a correction is needed, update the prompt bank and generate a new kit before recording. Do not silently edit the fixed script columns in a partly completed checklist.

## Audio requirements

- Target **8–15 seconds** per clip; the collection checker accepts **8–20 seconds**. Use continuous natural speech, not silence/repetition to reach the length. Do not rush a long sentence to fit; report a script that needs adjustment.
- Final analysis files: **WAV, mono, 16 kHz, signed 16-bit uncompressed PCM**. Keep the untouched originals separately. If a phone gives M4A, stereo or another sample rate, keep that original for a documented local conversion before import. Renaming an extension does not convert audio. The checker itself performs no conversion.
- Begin speaking promptly, ideally with no more than about a quarter-second of leading silence. Do not prepend a beep, spoken name, “this is human/AI”, consent statement or introduction. Keep consent and source evidence in the separate private log.
- Human clips must be newly spoken into a microphone by a consenting fluent adult, at a normal level and pace. Use one speaker, a quiet room and no background conversation or music. Record the actual device/software and note unavoidable microphone processing.
- AI clips must be direct original outputs from a **known stock TTS voice**, with known generator/model/voice information. No cloned reference voice, voice conversion, celebrity imitation, or loudspeaker re-recording in the clean baseline. Do not use online clips whose origin is merely suspected.
- No denoising, pitch/speed alteration, voice effects, splicing or repeated-prefix padding. Document necessary resampling/channel conversion and preserve the original. Keep raw and converted audio private; none belongs in Git.

Use existing recordings only if their origin, permission, script and format meet the selected slot. Otherwise keep them as separately labelled extras instead of forcing them into a matching filename. **Do not spend Gnani, Modal or another provider's credits to fill these slots.** Use already-owned suitable stock-TTS outputs or a local offline stock-voice generator. If those are unavailable, provide the human half first and leave the AI slots pending.

An optional offline source to investigate separately is [AI4Bharat Indic Parler-TTS](https://huggingface.co/ai4bharat/indic-parler-tts), which documents predefined voices for these languages and CPU fallback. Its repository requires the owner to accept access conditions; this kit does not download or run it. RAM, speed and output quality on this laptop have not been verified. There is no need to provide a personal voice sample for stock-voice synthesis.

## Files and private provenance

The local kit is `work/speech-screening-kit/`:

```text
speech-screening-kit/
  recordings/                 # The 60 final analysis WAVs
  originals/                  # Untouched recordings/exports
  private-provenance/         # Anonymous permission/source references
  checklist.csv               # 60 planned rows, confirmations initially false
  manifest.pending.jsonl      # Intended slots; deliberately not ready to score
  collection-plan.json
```

Keep recordings on this laptop; sharing them in chat is unnecessary. No passwords, provider keys, personal names, contact details or identity documents are required. Use anonymous IDs such as `human-01` and `tts-voice-01`.

In `checklist.csv`, fill only the confirmation/provenance fields after the file exists:

| Field | Human clip | Standard AI clip |
| --- | --- | --- |
| `collected`, `prompt_reviewed`, `consent` | `true` after actual confirmation | `true` after actual confirmation/permission to use the output |
| `confirmed_label` | `genuine` | `spoof` (synthetic origin; not a claim of malicious intent) |
| `origin` | `live_microphone` | `standard_tts` |
| `speaker_group` | Same anonymous ID for the same real person in all languages/clips | Same stable anonymous ID for the same stock voice in all languages/clips |
| `source_group` | ID for this original recorded utterance | ID for this original synthesis output |
| `label_evidence` | Private reference confirming observed live recording and permission | Private reference identifying generation/export, permission and source |
| `generator`, `model_version`, `voice_id` | Leave blank | Actual generator, model/version and stock voice ID; disclose a version the provider does not publish rather than inventing it |
| `voice_is_cloned` | Leave blank | Explicitly `false` |

For one human speaker, keep the same `speaker_group` across all three utterances. Each independently recorded utterance has its own `source_group`. Later codec/noise/replay derivatives keep their parent's source group and split. The checker catches declared group leakage, duplicate decoded audio and stock-voice reuse across splits; it cannot prove that a person honestly supplied the correct identity, consent or origin.

Keep evidence outside the test WAV. For example, a private text log can say that participant `human-01` agreed to local detector evaluation and no cloning, and was observed reading the listed scripts live. An AI log should record generator/model/voice, generation/export date, relevant use permission and transformations, without API headers or secrets.

## Local preparation and checks

The kit has already been prepared in this checkout. To prepare a separate new copy later:

```powershell
.\server\.venv\Scripts\python.exe scripts/prepare_speech_screening_kit.py --output-dir work/speech-screening-kit-new
```

An existing kit is never overwritten. After placing files and filling confirmations, check the current one:

```powershell
.\server\.venv\Scripts\python.exe scripts/prepare_speech_screening_kit.py --check work/speech-screening-kit --manifest-output work/speech-screening-kit/manifest.checked.jsonl
```

Missing recordings, consent, origin, native review, correct WAV format or split groups keep it blocked. The check uses **no model inference and no provider request**. It writes a new checked manifest only if all declarations and technical checks pass. A missing file never becomes a successful test. Preserve the checklist, originals and manifest version with each result.

The whole-pilot runner also defaults to a plan that reads no audio and loads no model:

```powershell
.\server\.venv\Scripts\python.exe scripts/run_speech_screening_study.py --plan
```

Only **after the completed kit passes**, run the paired CPU study locally:

```powershell
.\server\.venv\Scripts\python.exe scripts/run_speech_screening_study.py --manifest work/speech-screening-kit/manifest.checked.jsonl --execute --output work/speech-screening-kit/study-01.json
```

This uses the already installed model once, with two CPU threads, sequential batches of at most five sources, and at most 300 analysis calls. The default 180-second admission budget stops new calls when reached; a running synchronous model load or analysis can finish afterwards. Missing, failed and unattempted results remain visible. Use a new report filename for each run; existing results are never overwritten. The report omits audio paths, private evidence and group identifiers. Conditions are anonymized; the private manifest records this clean pilot as `clean_direct` for both classes, while the checklist retains their different origins. No provider or GPU connection is made and no live-screening policy is changed.

## What the actual comparison will measure

After review, the local study will analyze the **same opening 4.0375 seconds** from each source, then its 0.5/1/2/3-second prefixes under the existing isolated experiment. The unexamined remainder of an 8–20-second clip is not certified clean. Each source contributes one paired observation per duration; five crops are not five independent people.

Thresholds remain frozen at the current experimental values. Calibration rows stay out of the held-out headline. Results must show per-language and per-duration genuine false alarms, synthetic misses, unknowns, failed analyses, classified coverage, raw counts and compute time. Unknowns cannot be counted as correct. This kit's held-out set has just **three genuine and three AI clips per language**, from one identity per class, so it is a pilot rather than proof of reliable accuracy.

Before reducing the live window, the full-window baseline must meet the intended operating targets, followed by a larger paired held-out comparison with declared acceptable error changes and uncertainty that accounts for shared speakers/voices. A possible follow-up target is 400 source clips: eight human speakers and eight stock AI voices per language, five fresh utterances each; two identities/class for calibration and six for evaluation. This target is not a guarantee of statistical power. Different generators, microphones, natural accents, noise, codecs and held-out generator families need their own coverage. Do not tune on the final evaluation results or claim unseen-generator performance from a single generator.

## Optional challenges after the clean pilot

You need not supply these to start. We can prepare documented codec/noise variants locally from the originals without provider credits; they remain correlated derivatives. For physical replay testing, an optional later set has ten recordings: one human-origin replay and one AI-origin replay per language. Record playback device, recording device, distance and room condition. Human replay remains **human-origin replay**, not AI-generated speech; report replay protection separately from AI-versus-human detection. No voice cloning is involved.

## Native recording scripts

Each language has C01–C03 for HA/AA and E01–E03 for HB/AB. English meanings are review aids, not words to read aloud. The scripts and recording duration must be reviewed by a fluent speaker before use.

### Hindi (hi)

**C01 — HA and AA**

कल सुबह पुस्तकालय के सामने मुझसे दस बजे मिलना, ग्यारह बजे नहीं। अगर सामने का दरवाज़ा बंद हो, तो बाईं ओर बड़े पेड़ के पास इंतज़ार करना।

Meaning: Meet outside the library tomorrow morning at ten, not eleven. If the front door is closed, wait near the large tree on the left.

**C02 — HA and AA**

नीली किताब मेज़ पर रख दो, लाल वाली नहीं। साथ में दो खाली बोतलें और आधा लीटर पानी ले आना। बाकी सामान अलमारी में ही रहने देना।

Meaning: Put the blue book on the table, not the red one. Bring two empty bottles and half a litre of water. Leave the other things in the cupboard.

**C03 — HA and AA**

मैं पार्क के मुख्य दरवाज़े के पास हूँ। बाईं ओर की छोटी सड़क से आना, फिर चाय की दुकान के पास रुकना। पहुँचने पर मुझे बता देना।

Meaning: I am near the park's main gate. Come along the small road on the left and stop near the tea shop. Tell me when you arrive.

**E01 — HB and AB**

आज दोपहर हमारी कक्षा ऊपर वाले कमरे में होगी। एक कॉपी और पेंसिल लाना, लेकिन बड़ा बैग नीचे छोड़ देना। सबके आने के बाद हम पढ़ाई शुरू करेंगे।

Meaning: This afternoon's class is in the upstairs room. Bring a notebook and pencil, leave the large bag downstairs, and start studying after everyone arrives.

**E02 — HB and AB**

योजना बदल गई है। अब हम शनिवार की जगह रविवार को बगीचे में जाएँगे। तीन कप और पीने का पानी साथ लाना। अगर बारिश हुई, तो हम घर पर ही रहेंगे।

Meaning: The garden visit changes from Saturday to Sunday. Bring three cups and drinking water. If it rains, stay at home.

**E03 — HB and AB**

दरवाज़े के पास वाली खिड़की खोल दो और अलमारी के पास वाली बंद कर दो। छोटी कुर्सी कोने में रख देना। थोड़ा धीरे बोलना, ताकि सब लोग बात समझ सकें।

Meaning: Open the window near the door, close the window near the cupboard, and put the small chair in the corner. Speak more slowly so everyone understands.

### Tamil (ta)

**C01 — HA and AA**

நாளை காலை நூலகத்தின் முன் என்னைப் பத்து மணிக்குச் சந்திக்கவும், பதினொரு மணிக்கு அல்ல. முன்பக்கக் கதவு மூடியிருந்தால், இடது பக்கத்தில் இருக்கும் பெரிய மரத்தின் அருகில் காத்திருக்கவும். நான் அங்கே வந்து உங்களைச் சந்திப்பேன்.

Meaning: Meet outside the library tomorrow morning at ten, not eleven. If the front door is closed, wait near the large tree on the left; I will meet you there.

**C02 — HA and AA**

நீல நிறப் புத்தகத்தை மேசையின் மீது வைக்கவும், சிவப்பு நிறப் புத்தகத்தை அல்ல. இரண்டு காலி பாட்டில்களையும் அரை லிட்டர் தண்ணீரையும் கொண்டு வரவும். மற்ற பொருட்களை எடுத்துவர வேண்டாம்; அவை அலமாரியிலேயே இருக்கட்டும்.

Meaning: Put the blue book on the table, not the red one. Bring two empty bottles and half a litre of water. Leave the other items in the cupboard.

**C03 — HA and AA**

நான் பூங்காவின் முக்கிய நுழைவாயிலுக்கு அருகில் நிற்கிறேன். இடது பக்கத்தில் உள்ள சிறிய சாலை வழியாக வந்து, தேநீர்க் கடைக்கு அருகில் நிற்கவும். நீங்கள் அங்கே வந்தவுடன் எனக்குத் தெரிவிக்கவும்; நான் உங்களைப் பார்க்கிறேன்.

Meaning: I am near the park's main entrance. Come along the small road on the left and stop near the tea shop. Tell me when you arrive so I can find you.

**E01 — HB and AB**

இன்று பிற்பகல் நமது வகுப்பு மாடியில் உள்ள அறையில் நடைபெறும். ஒரு குறிப்பேடும் பென்சிலும் கொண்டு வரவும், ஆனால் பெரிய பையைக் கீழே விட்டுவிடவும். அனைவரும் வந்து சேர்ந்த பிறகு நாம் பாடத்தைத் தொடங்கலாம்.

Meaning: This afternoon's class is in the upstairs room. Bring a notebook and pencil, leave the large bag downstairs, and begin the lesson after everyone arrives.

**E02 — HB and AB**

நமது திட்டம் மாறிவிட்டது. சனிக்கிழமைக்குப் பதிலாக ஞாயிற்றுக்கிழமை தோட்டத்திற்குச் செல்வோம். மூன்று கோப்பைகளையும் குடிப்பதற்குத் தண்ணீரையும் கொண்டு வரவும். அன்று மழை பெய்தால், நாம் வெளியே செல்லாமல் வீட்டிலேயே இருப்போம்; வேறொரு நாளில் செல்லலாம்.

Meaning: The garden visit changes from Saturday to Sunday. Bring three cups and drinking water. If it rains, stay home and go another day.

**E03 — HB and AB**

கதவுக்கு அருகில் உள்ள ஜன்னலைத் திறந்து, அலமாரிக்கு அருகில் உள்ள ஜன்னலை மூடவும். சிறிய நாற்காலியை அறையின் மூலையில் வைக்கவும். அனைவருக்கும் புரியும் வகையில் கொஞ்சம் மெதுவாகப் பேசவும்; முக்கியமான விவரங்களைத் தெளிவாகச் சொல்லவும்.

Meaning: Open the window near the door, close the one near the cupboard, and put the small chair in the corner. Speak slowly and clearly so everyone understands the details.

### Bengali (bn)

**C01 — HA and AA**

কাল সকালে গ্রন্থাগারের সামনে আমার সঙ্গে দশটায় দেখা করো, এগারোটায় নয়। সামনের দরজা বন্ধ থাকলে বাঁ দিকের বড় গাছটার কাছে অপেক্ষা করো। আমি সেখানেই তোমার সঙ্গে দেখা করব।

Meaning: Meet outside the library tomorrow morning at ten, not eleven. If the front door is closed, wait by the large tree on the left; I will meet you there.

**C02 — HA and AA**

নীল বইটা টেবিলের ওপর রেখে দাও, লালটা নয়। সঙ্গে দুটো খালি বোতল আর আধা লিটার জল নিয়ে এসো। অন্য জিনিসগুলো আলমারিতেই থাকতে দাও, সেগুলো আনার দরকার নেই।

Meaning: Put the blue book on the table, not the red one. Bring two empty bottles and half a litre of water. Leave the other items in the cupboard.

**C03 — HA and AA**

আমি পার্কের প্রধান ফটকের কাছে দাঁড়িয়ে আছি। বাঁ দিকের ছোট রাস্তা দিয়ে এসো, তারপর চায়ের দোকানের পাশে দাঁড়াও। সেখানে পৌঁছে আমাকে জানিয়ো, আমি তোমাকে খুঁজে নেব।

Meaning: I am near the park's main gate. Come along the small road on the left and stop beside the tea shop. Tell me when you arrive so I can find you.

**E01 — HB and AB**

আজ বিকেলে আমাদের ক্লাস ওপরের ঘরে হবে। একটা খাতা আর পেন্সিল নিয়ে এসো, কিন্তু বড় ব্যাগটা নিচে রেখে দাও। সবাই এসে পৌঁছানোর পরে আমরা পড়া শুরু করব।

Meaning: This afternoon's class is in the upstairs room. Bring a notebook and pencil, leave the large bag downstairs, and start studying after everyone arrives.

**E02 — HB and AB**

আমাদের পরিকল্পনা বদলেছে। শনিবারের বদলে রবিবার বাগানে যাব। সঙ্গে তিনটে কাপ আর খাওয়ার জল নিয়ে এসো। সেদিন বৃষ্টি হলে আমরা বাড়িতেই থাকব, অন্য একদিন যাওয়া যাবে।

Meaning: The garden visit changes from Saturday to Sunday. Bring three cups and drinking water. If it rains, stay home and go another day.

**E03 — HB and AB**

দরজার কাছের জানলাটা খুলে দাও আর আলমারির পাশের জানলাটা বন্ধ করো। ছোট চেয়ারটা ঘরের কোণে রাখো। একটু ধীরে কথা বলো, যাতে সবাই তোমার কথা ভালো করে বুঝতে পারে।

Meaning: Open the window near the door, close the window beside the cupboard, and put the small chair in the corner. Speak more slowly so everyone understands.

### Telugu (te)

**C01 — HA and AA**

రేపు ఉదయం గ్రంథాలయం ముందు నన్ను పది గంటలకు కలవండి, పదకొండు గంటలకు కాదు. ముందున్న తలుపు మూసి ఉంటే, ఎడమ వైపున ఉన్న పెద్ద చెట్టు దగ్గర వేచి ఉండండి. నేను అక్కడికి వస్తాను.

Meaning: Meet outside the library tomorrow morning at ten, not eleven. If the front door is closed, wait near the large tree on the left; I will come there.

**C02 — HA and AA**

నీలం రంగు పుస్తకాన్ని బల్ల మీద పెట్టండి, ఎరుపు రంగు పుస్తకాన్ని కాదు. రెండు ఖాళీ సీసాలు, అర లీటరు నీళ్లు తీసుకురండి. మిగతా వస్తువులు అలమారాలోనే ఉండనివ్వండి, వాటిని ఇప్పుడు తీసుకురావాల్సిన అవసరం లేదు.

Meaning: Put the blue book on the table, not the red one. Bring two empty bottles and half a litre of water. Leave the other items in the cupboard.

**C03 — HA and AA**

నేను పార్కు ప్రధాన ద్వారం దగ్గర నిలబడి ఉన్నాను. ఎడమ వైపున ఉన్న చిన్న రోడ్డు మీదుగా వచ్చి, టీ దుకాణం పక్కన ఆగండి. మీరు అక్కడికి చేరుకున్న వెంటనే నాకు చెప్పండి, నేను మిమ్మల్ని కలుస్తాను.

Meaning: I am near the park's main gate. Come along the small road on the left and stop beside the tea shop. Tell me when you arrive; I will meet you.

**E01 — HB and AB**

ఈ రోజు మధ్యాహ్నం మన తరగతి మేడ మీద ఉన్న గదిలో జరుగుతుంది. ఒక నోటు పుస్తకం, పెన్సిల్ తీసుకురండి, కానీ పెద్ద సంచిని కిందే ఉంచండి. అందరూ వచ్చిన తర్వాత మనం పాఠం మొదలుపెడదాం.

Meaning: This afternoon's class is in the upstairs room. Bring a notebook and pencil, leave the large bag downstairs, and begin the lesson after everyone arrives.

**E02 — HB and AB**

మన ప్రణాళిక మారింది. శనివారం బదులు ఆదివారం తోటకు వెళ్దాం. మూడు కప్పులు, తాగడానికి నీళ్లు తీసుకురండి. ఆ రోజు వర్షం పడితే బయటకు వెళ్లకుండా ఇంట్లోనే ఉందాం, మరో రోజు వెళ్లడానికి సమయం చూసుకుందాం.

Meaning: The garden visit changes from Saturday to Sunday. Bring three cups and drinking water. If it rains, stay home and find another day to go.

**E03 — HB and AB**

తలుపు దగ్గర ఉన్న కిటికీని తెరిచి, అలమారా పక్కన ఉన్న కిటికీని మూసేయండి. చిన్న కుర్చీని గది మూలలో పెట్టండి. అందరికీ అర్థమయ్యేలా కొంచెం నెమ్మదిగా మాట్లాడండి, ముఖ్యమైన విషయాలు స్పష్టంగా చెప్పండి. నేను జాగ్రత్తగా వింటాను.

Meaning: Open the window near the door, close the one beside the cupboard, and put the small chair in the corner. Speak slowly and clearly so everyone understands; I will listen carefully.

### Marathi (mr)

**C01 — HA and AA**

उद्या सकाळी ग्रंथालयासमोर मला दहा वाजता भेटा, अकरा वाजता नाही. समोरचा दरवाजा बंद असेल, तर डाव्या बाजूच्या मोठ्या झाडाजवळ थांबा. मी तिथे येऊन तुम्हाला भेटेन, तोपर्यंत तिथेच थांबा.

Meaning: Meet outside the library tomorrow morning at ten, not eleven. If the front door is closed, wait near the large tree on the left until I arrive.

**C02 — HA and AA**

निळे पुस्तक टेबलावर ठेवा, लाल पुस्तक नाही. सोबत दोन रिकाम्या बाटल्या आणि अर्धा लिटर पाणी आणा. बाकीच्या वस्तू कपाटातच राहू द्या, त्या वस्तू आत्ता आणण्याची गरज नाही.

Meaning: Put the blue book on the table, not the red one. Bring two empty bottles and half a litre of water. Leave the other items in the cupboard.

**C03 — HA and AA**

मी उद्यानाच्या मुख्य प्रवेशद्वाराजवळ तुमची वाट पाहत आहे. डाव्या बाजूच्या छोट्या रस्त्याने या आणि चहाच्या दुकानाजवळ थांबा. तुम्ही तिथे पोहोचल्यावर मला कळवा, मग मी तुम्हाला भेटायला येईन. घाई करण्याची गरज नाही.

Meaning: I am waiting near the park's main gate. Come along the small road on the left and stop near the tea shop. Tell me when you arrive; there is no need to hurry.

**E01 — HB and AB**

आज दुपारी आपला वर्ग वरच्या खोलीत होईल. एक वही आणि पेन्सिल आणा, पण मोठी पिशवी खालीच ठेवा. सर्वजण आल्यावर आपण अभ्यास सुरू करू. तोपर्यंत आपल्या जागेवर शांतपणे बसा.

Meaning: This afternoon's class is in the upstairs room. Bring a notebook and pencil, leave the large bag downstairs, and begin studying after everyone arrives. Sit quietly until then.

**E02 — HB and AB**

आपला बेत बदलला आहे. शनिवारी जाण्याऐवजी आपण रविवारी बागेत जाऊ. सोबत तीन कप आणि पिण्याचे पाणी आणा. त्या दिवशी पाऊस पडला, तर आपण घरीच थांबू आणि दुसऱ्या दिवशी जाण्याचा विचार करू.

Meaning: The garden visit changes from Saturday to Sunday. Bring three cups and drinking water. If it rains, stay home and consider going on another day.

**E03 — HB and AB**

दरवाजाजवळची खिडकी उघडा आणि कपाटाजवळची खिडकी बंद करा. लहान खुर्ची खोलीच्या कोपऱ्यात ठेवा. सगळ्यांना तुमचे बोलणे समजावे म्हणून थोडे हळू बोला आणि महत्त्वाचे मुद्दे स्पष्ट सांगा. मी लक्ष देऊन ऐकेन.

Meaning: Open the window near the door, close the window near the cupboard, and put the small chair in the corner. Speak slowly and clearly so everyone understands; I will listen carefully.

