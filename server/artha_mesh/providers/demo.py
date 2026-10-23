"""Hand-authored examples only. These are not translation or speech recognition."""
from __future__ import annotations

from ..errors import ProviderError

SAMPLES: list[dict[str, str]] = [
    {"hi": "नमस्ते, आप कैसे हैं?", "ta": "வணக்கம், நீங்கள் எப்படி இருக்கிறீர்கள்?", "bn": "নমস্কার, আপনি কেমন আছেন?", "en": "Hello, how are you?"},
    {"hi": "मुझे पचास डिब्बे चाहिए।", "ta": "எனக்கு ஐம்பது பெட்டிகள் வேண்டும்.", "bn": "আমার পঞ্চাশটি বাক্স চাই।", "en": "I need fifty cartons."},
    {"hi": "प्रति डिब्बा 1500 रुपये हैं।", "ta": "ஒரு பெட்டியின் விலை 1500 ரூபாய்.", "bn": "প্রতি বাক্সের দাম 1500 টাকা।", "en": "The price is 1500 rupees per carton."},
    {"hi": "मेरी पुष्टि के बाद ही शुक्रवार को भेजें।", "ta": "நான் உறுதிசெய்த பிறகு மட்டுமே வெள்ளிக்கிழமை அனுப்புங்கள்.", "bn": "আমি নিশ্চিত করার পরেই শুক্রবার পাঠাবেন।", "en": "Dispatch on Friday only after I confirm."},
    {"hi": "कुल राशि 75000 रुपये है।", "ta": "மொத்தத் தொகை 75000 ரூபாய்.", "bn": "মোট অর্থের পরিমাণ 75000 টাকা।", "en": "The total amount is 75000 rupees."},
    {"hi": "कृपया मात्रा और कीमत फिर से बताएं।", "ta": "தயவுசெய்து அளவையும் விலையையும் மீண்டும் சொல்லுங்கள்.", "bn": "দয়া করে পরিমাণ এবং দাম আবার বলুন।", "en": "Please repeat the quantity and the price."},
    {"hi": "मैंने विवरण समझ लिया है।", "ta": "விவரங்களைப் புரிந்துகொண்டேன்.", "bn": "আমি বিবরণ বুঝেছি।", "en": "I understand the details."},
]


def normalize(text: str) -> str:
    return " ".join(text.strip().split()).rstrip(".।?!").casefold()


def sample_for(text: str, source: str) -> dict[str, str] | None:
    return next((row for row in SAMPLES if normalize(row[source]) == normalize(text)), None)


class DemoTranslator:
    async def translate(self, text: str, source: str, target: str) -> str:
        row = sample_for(text, source)
        if row is None:
            raise ProviderError("This local demonstration supports its listed sample phrases only", False)
        return row[target]
