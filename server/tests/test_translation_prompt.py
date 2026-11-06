"""Pure prompt parity and deliberately limited output-script rejection."""
import importlib.util
import json
from pathlib import Path

import pytest

from charcha.providers.translation_prompt import PROMPT_VERSION, check_target_script, translation_messages

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("text,target", [("हम 10 बजे मिलेंगे।", "ta"), ("வணக்கம்", "hi"),
    ("আমি আসছি", "te"), ("नमस्ते John 10", "ta")])
def test_clear_other_script_without_target_letters_is_rejected(text, target):
    with pytest.raises(ValueError):
        check_target_script(text, target)


@pytest.mark.parametrize("text,target", [("நாம் 10 மணிக்கு சந்திப்போம், 11 மணிக்கு இல்லை.", "ta"),
    ("John 10", "ta"), ("10:30", "ta"), ("राम 10", "mr"), ("मराठी 10", "hi"),
    ("தமிழ் John 10", "ta"), ("John १२", "en"), ("Meet राम at 10", "en")])
def test_target_script_names_digits_and_shared_hindi_marathi_script_are_allowed(text, target):
    assert check_target_script(text, target) == text


def test_backend_and_standalone_use_identical_explicit_target_prompt_and_version():
    spec = importlib.util.spec_from_file_location("prompt_benchmark_test", ROOT / "scripts/evon_benchmark.py")
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    case = benchmark.load_cases(benchmark.DEFAULT_CORPUS, ["hi-ta-01"])[0]
    plan = benchmark.build_plan([case])
    body = benchmark.request_body(plan, case)
    assert body["messages"] == translation_messages(case["source_text"], "hi", "ta")
    assert plan["prompt_version"] == PROMPT_VERSION
    user = json.loads(body["messages"][1]["content"])
    assert user["target_language"] == "Tamil (தமிழ்)"
    assert "using Tamil script" in user["task"]
    assert user["utterance"] == case["source_text"]
    old = {**plan, "prompt_version": "old-contract"}
    old["plan_sha256"] = benchmark.digest({key: value for key, value in old.items() if key != "plan_sha256"})
    with pytest.raises(ValueError, match="prompt version"):
        benchmark.authorize(old, old["plan_sha256"], True)


@pytest.mark.parametrize("target,text", [
    ("hi", "WhatsApp पर दस बजे"), ("ta", "blue notebook எடுத்துட்டு வா"),
    ("bn", "কাল library-তে দেখা হবে"), ("te", "Water bottle లో నీరు పోయాలి"),
    ("mr", "काल park मध्ये भेटलो"),
])
def test_conversational_prompt_and_script_guard_preserve_identifiers(target, text):
    assert check_target_script(text, target) == text
    system, request = translation_messages(text, "en", target)
    assert "identifiers" in system["content"] and "negation" in system["content"]
    assert json.loads(request["content"])["utterance"] == text
