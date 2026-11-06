"""Hand-authored examples only. These are not translation or speech recognition."""
from __future__ import annotations

from ..errors import ProviderError

SAMPLES: list[dict[str, str]] = [
    {"hi": "नमस्ते, आप कैसे हैं?", "ta": "வணக்கம், நீங்கள் எப்படி இருக்கிறீர்கள்?", "bn": "নমস্কার, আপনি কেমন আছেন?", "en": "Hello, how are you?"},
    {"hi": "कल सुबह 10 बजे सामुदायिक केंद्र के मुख्य दरवाजे पर मिलते हैं।", "ta": "நாளை காலை 10 மணிக்கு சமூக மையத்தின் பிரதான நுழைவாயிலில் சந்திப்போம்.", "bn": "আগামীকাল সকাল 10টায় কমিউনিটি সেন্টারের প্রধান দরজায় দেখা করি।", "en": "Let us meet tomorrow at 10 in the morning at the community centre's main entrance."},
    {"hi": "हाँ, कल सुबह 10 बजे, आज नहीं।", "ta": "ஆம், நாளை காலை 10 மணிக்கு, இன்று இல்லை.", "bn": "হ্যাঁ, আগামীকাল সকাল 10টায়, আজ নয়।", "en": "Yes, tomorrow at 10 in the morning, not today."},
    {"hi": "मेरे आने तक बैठक शुरू मत कीजिए।", "ta": "நான் வரும் வரை கூட்டத்தைத் தொடங்க வேண்டாம்.", "bn": "আমি না আসা পর্যন্ত সভা শুরু করবেন না।", "en": "Please do not start the meeting until I arrive."},
    {"hi": "मैं दूसरी मंज़िल पर हूँ, तीसरी पर नहीं।", "ta": "நான் இரண்டாவது தளத்தில் இருக்கிறேன், மூன்றாவது தளத்தில் இல்லை.", "bn": "আমি দ্বিতীয় তলায় আছি, তৃতীয় তলায় নয়।", "en": "I am on the second floor, not the third."},
    {"hi": "कमरा AM-204 है। कृपया Wi-Fi का नाम फिर से बताइए।", "ta": "அறை AM-204. தயவுசெய்து Wi-Fi பெயரை மீண்டும் சொல்லுங்கள்.", "bn": "ঘরটি AM-204। দয়া করে Wi-Fi-এর নাম আবার বলুন।", "en": "The room is AM-204. Please repeat the Wi-Fi name."},
    {"hi": "पहले बाएँ मुड़िए, फिर 200 मीटर सीधे चलिए।", "ta": "முதலில் இடதுபுறம் திரும்பி, பிறகு 200 மீட்டர் நேராகச் செல்லுங்கள்.", "bn": "প্রথমে বাঁ দিকে ঘুরুন, তারপর 200 মিটার সোজা যান।", "en": "First turn left, then go straight for 200 metres."},
]


def normalize(text: str) -> str:
    return " ".join(text.strip().split()).rstrip(".।?!").casefold()


def sample_for(text: str, source: str) -> dict[str, str] | None:
    return next((row for row in SAMPLES if source in row and normalize(row[source]) == normalize(text)), None)


class DemoTranslator:
    async def translate(self, text: str, source: str, target: str) -> str:
        row = sample_for(text, source)
        if row is None or target not in row:
            raise ProviderError("This local demonstration supports its listed sample phrases only", False)
        return row[target]
