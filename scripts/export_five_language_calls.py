"""Export the reviewed stage's aggregate evidence without audio, text or account identifiers."""
import json
from html import escape
import math
import re
import unicodedata

from run_five_language_calls import CLIPS, FLEURS, LIMITS, OUT, ROOT, STAGE


def word_error_rate(reference, recognized):
    def words(text):
        folded = unicodedata.normalize("NFKC", text).casefold()
        return "".join(" " if unicodedata.category(c).startswith("P") else c for c in folded).split()
    expected, actual = words(reference), words(recognized)
    if not expected:
        return None
    previous = list(range(len(actual) + 1))
    for i, token in enumerate(expected, 1):
        row = [i]
        for j, received in enumerate(actual, 1):
            row.append(min(previous[j] + 1, row[-1] + 1, previous[j-1] + (token != received)))
        previous = row
    return round(previous[-1] / len(expected), 4)


def check_year(reference, recognized):
    """Compare explicit calendar years across Indic and ASCII digits, without guessing words."""
    def years(text):
        normalized = "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in text)
        return re.findall(r"(?<![0-9])(?:1[89]|20)[0-9]{2}(?![0-9])", normalized)
    expected, heard = years(reference), years(recognized)
    if len(expected) != 1 or heard == expected:
        return None
    return {"reference":expected[0], "recognized":heard[0] if len(heard) == 1 else None}


def public_result(folder):
    report = json.loads((folder / "report.json").read_text())
    compute = json.loads((folder / "compute.json").read_text())
    if (report["stage_id"] != STAGE["id"] or report["real_providers"] is not True
            or report["physical_devices"] is not False or compute["stopped"] is not True
            or [[r["source"], r["target"]] for r in report["routes"]] != STAGE["routes"]):
        raise ValueError("Expected the stopped real-provider batch in its reviewed route order")
    rows = []
    for route in report["routes"]:
        status = route["status"]
        if status not in ("failed", "unattempted", "receiver_decoded"):
            raise ValueError("Open or unknown route status")
        units = dict.fromkeys(LIMITS, 0) if status == "unattempted" else route.get("used", {})
        if (set(units) != set(LIMITS) or any(type(units[k]) is not int or not 0 <= units[k] <= cap
            for k, cap in LIMITS.items()) or (status != "unattempted" and route.get("grant_closed") is not True)):
            raise ValueError("Invalid or unclosed reservations")
        item = {key:route[key] for key in ("source", "target", "status")}
        item.update(used=units, source_wer=None, year_review=None, stage=None, capture_start_to_receiver_first_pcm_ms=None,
                    stt_processing_ms=None, mt_ms=None, tts_first_pcm_ms=None, server_first_pcm_ms=None)
        if status == "receiver_decoded":
            if (route.get("received_non_silent_pcm") is not True or any(units[k] != 1 for k in
                    ("stt_connections","mt_requests","tts_requests"))):
                raise ValueError("Missing live evidence")
            private = json.loads((folder / f"{item['source']}-{item['target']}.json").read_text(encoding="utf8"))
            item["source_wer"] = word_error_rate(private["reference"], private["recognized"])
            item["year_review"] = check_year(private["reference"], private["recognized"])
            for k in ("capture_start_to_receiver_first_pcm_ms","stt_processing_ms","mt_ms","tts_first_pcm_ms","server_first_pcm_ms"):
                value = route[k]
                if value is None and k == "stt_processing_ms":
                    continue
                if type(value) not in (int,float) or not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid timing")
                item[k] = value
        elif status == "failed":
            stage = route.get("stage")
            item["stage"] = stage if stage in {"rtc_join","speech_recognition","delivery","mt","tts","listener_decode","setup"} else "other"
            if not any(units.values()) and stage == "setup" and route.get("error_kind") == "PermissionError":
                item["stage"] = "local setup before API use"
        rows.append(item)
    delta = float(compute["after"]["metered_cost"]) - float(compute["before"]["metered_cost"])
    return {"stage_id": STAGE["id"], "recorded": True, "routes": rows,
            "modal_stopped": True, "workspace_meter_change_usd": round(delta, 6) if delta >= 0 else None,
            "provider_invoice_inr": None, "physical_listener_latency_ms": None, "meaning_review": "pending"}


def local_listening_page(folder, result):
    """Private disk-only review. Use relative file links; never embed audio in the web bundle."""
    names = {"hi":"Hindi", "ta":"Tamil", "bn":"Bengali", "te":"Telugu", "mr":"Marathi"}
    import os
    from urllib.parse import quote
    cards = []
    for row in result["routes"]:
        source, target = row["source"], row["target"]
        heading = f"<h2>{names[source]} → {names[target]}</h2>"
        if row["status"] != "receiver_decoded":
            cards.append("<section>" + heading + "<p>" + escape(row["status"]) + "</p></section>")
            continue
        prefix = f"{source}-{target}"
        texts = json.loads((folder / f"{prefix}.json").read_text(encoding="utf8"))
        source_file = FLEURS / "recordings" / f"public-fleurs-{source}-{CLIPS[source][0]}.wav"
        href = quote(os.path.relpath(source_file, folder).replace(os.sep, "/"))
        cards.append(f"""<section>{heading}<div class="pair"><div><h3>Source recording</h3>
        <audio controls preload="none" src="{href}"></audio></div>
        <div><h3>Received translation</h3><audio controls preload="none" src="{prefix}.wav"></audio>
        </div></div><details><summary>Compare reference and captions after listening</summary>
        <h3>Published source reference</h3><p>{escape(texts['reference'])}</p>
        <h3>Recognized speech</h3><p>{escape(texts['recognized'])}</p>
        <h3>Translated caption</h3><p>{escape(texts['translated'])}</p></details></section>""")
    (folder / "listen.html").write_text("""<!doctype html><html lang="en"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>Five-language listening review</title>
    <style>body{margin:2rem auto;padding:0 1rem;max-width:56rem;font:1rem/1.6 system-ui;color:#24272e;background:#f4f5f8;accent-color:#365bd6}
    section{padding:1rem 1.4rem;margin:1rem 0;background:white;border:1px solid #d6dbe4;border-radius:.7rem}
    h2,h3{margin:.5rem 0}.pair{display:flex;flex-wrap:wrap;gap:1rem}audio{max-width:100%}summary{cursor:pointer;color:#2847b3}
    details{margin:1rem 0}</style><main><h1>Five-language listening review</h1>
    <p>Compare the public source recording with the audio captured at the receiving RTC client.
    Listen for missing words, changes in meaning and clipped endings. Playback runs from local files.</p>
    <p>Source audio: Google FLEURS, Conneau et al. (2022), CC BY 4.0, converted to PCM16.</p>"""
    + "".join(cards) + "</main></html>", encoding="utf8")


if __name__ == "__main__":
    result = public_result(OUT)
    local_listening_page(OUT, result)
    dest = ROOT / "web/src/data/fiveLanguageStageResults.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
