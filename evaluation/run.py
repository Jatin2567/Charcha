"""Collect actual server results and combine external bilingual ratings.

No automatic semantic-accuracy score, provider calls without explicit collect,
or invented measurements. Standard-library only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import time
import unicodedata
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "everyday_cases.jsonl"
RATING_COLUMNS = [
    "case_id", "reviewer_id", "source_fluent", "target_fluent", "meaning_1_to_5",
    "critical_values_correct", "negation_condition_correct", "naturalness_1_to_5",
    "reference_approved", "notes",
]


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number}: invalid JSON") from exc
    return rows


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        # Treat provider/reviewer strings as data when opened in spreadsheet apps.
        writer.writerows({key: ("'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value)
                          for key, value in row.items()} for row in rows)


def normalized_digits(text: str) -> str:
    """Only numeric surface preservation; this is not semantic validation."""
    chars = []
    for char in unicodedata.normalize("NFKC", text):
        try:
            chars.append(str(unicodedata.decimal(char)))
        except (ValueError, TypeError):
            chars.append(char)
    return "".join(chars)


def numeric_values(text: str) -> list[str]:
    # Currency grouping commas do not change the number. Decimal points do.
    return re.findall(r"\d+(?:\.\d+)?", re.sub(r"(?<=\d),(?=\d)", "", normalized_digits(text)))


def number_surface_check(case: dict, translated: str) -> str:
    expected = [str(value) for value in case.get("critical_values", {}).get("numeric", [])]
    if not expected:
        return "not_applicable"
    observed = numeric_values(translated)
    return "present_unverified" if all(value in observed for value in expected) else "review_needed"


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    # Nearest-rank: the same definition is used for small and large runs.
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def http_json(base: str, method: str, path: str, body=None, token=None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = request.Request(base.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=45) as response:
            return json.load(response)
    except error.HTTPError as exc:
        # Do not store raw responses: they might contain credentials/upstream data.
        raise RuntimeError(f"HTTP {exc.code} at {method} {path.split('?')[0]}") from exc


def collect(args) -> None:
    cases = load_jsonl(args.dataset)
    if args.limit:
        cases = cases[:args.limit]
    health = http_json(args.api_url, "GET", "/api/health")
    if health.get("mode") != args.expected_mode:
        raise SystemExit(f"Expected {args.expected_mode!r}, server reports {health.get('mode')!r}.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        for case in cases:
            row = {
                "case_id": case["id"], "mode": health["mode"],
                "measurement": "server_pipeline", "input_kind": "typed_text",
                "source_language": case["source_language"],
                "target_language": case["target_language"], "status": "error",
                "translation": "", "server_pipeline_ms": None,
            }
            memberships = []
            code = None
            started = time.monotonic()
            try:
                room = http_json(args.api_url, "POST", "/api/rooms", {"title": "Evaluation " + case["id"]})
                code = room["code"]
                for name, language in (("Evaluation source", case["source_language"]),
                                       ("Evaluation listener", case["target_language"])):
                    membership = http_json(args.api_url, "POST", f"/api/rooms/{code}/join", {
                        "name": name, "language": language, "voice_mode": "standard", "consent": health["mode"] == "live",
                    })
                    memberships.append(membership)
                token = memberships[0]["session_token"]
                posted = http_json(args.api_url, "POST", f"/api/rooms/{code}/text", {"text": case["source_text"]}, token)
                deadline = time.monotonic() + args.timeout
                turn = None
                while time.monotonic() < deadline:
                    snapshot = http_json(args.api_url, "GET", f"/api/rooms/{code}/transcript", token=token)
                    turn = next((item for item in snapshot.get("turns", []) if item["id"] == posted["utterance_id"]), None)
                    if turn and turn.get("status") in {"complete", "error"}:
                        break
                    time.sleep(0.1)
                if not turn or turn.get("status") != "complete":
                    raise RuntimeError("Turn did not complete before the timeout or failed upstream.")
                translated = turn.get("translations", {}).get(case["target_language"], "")
                if not translated:
                    raise RuntimeError("Completed turn has no requested target translation.")
                metrics = snapshot.get("metrics", {})
                # Fresh room, one turn: no previous turn can contaminate this value.
                row.update(status="complete", translation=translated,
                           server_pipeline_ms=metrics.get("total_ms"),
                           stt_ms=metrics.get("stt_ms"), mt_ms=metrics.get("mt_ms"),
                           tts_ms=metrics.get("tts_ms"))
            except Exception as exc:
                row["error"] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
            finally:
                row["request_to_result_ms"] = round((time.monotonic() - started) * 1000, 2)
                for membership in memberships:
                    try:
                        http_json(args.api_url, "POST", f"/api/rooms/{code}/leave",
                                  {"participant_id": membership["participant"]["id"]}, membership["session_token"])
                    except Exception:
                        pass
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            print(f"{row['case_id']}: {row['status']} ({row['mode']})")


def _approved(value: str | None) -> bool:
    return (value or "").strip().lower() in {"yes", "true", "1"}


def _rating(value: str | None) -> float | None:
    try:
        number = float(value or "")
        return number if 1 <= number <= 5 else None
    except ValueError:
        return None


def report(args) -> None:
    cases = {case["id"]: case for case in load_jsonl(args.dataset)}
    predictions = load_jsonl(args.predictions)
    ids = [row["case_id"] for row in predictions]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate case IDs in run; report each run separately.")
    ratings: dict[str, list[dict]] = {}
    if args.ratings:
        with args.ratings.open(encoding="utf-8-sig", newline="") as stream:
            for rating in csv.DictReader(stream):
                ratings.setdefault(rating["case_id"], []).append(rating)
    rows = []
    for prediction in predictions:
        case = cases.get(prediction["case_id"])
        if not case:
            raise SystemExit(f"Unknown case ID: {prediction['case_id']}")
        human = [rating for rating in ratings.get(case["id"], [])
                 if rating.get("reviewer_id", "").strip()
                 and _approved(rating.get("source_fluent"))
                 and _approved(rating.get("target_fluent"))]
        meaning = [value for rating in human if (value := _rating(rating.get("meaning_1_to_5"))) is not None]
        explicit_critical = [rating for rating in human
                             if rating.get("critical_values_correct", "").strip().lower() in {"yes", "no"}]
        row = dict(prediction)
        row.update(
            source_text=case["source_text"], reference_draft=case["reference_draft"],
            reference_status=case["reference_status"],
            numeric_surface_check=number_surface_check(case, prediction.get("translation", "")),
            bilingual_ratings=len(human),
            mean_meaning_rating=round(statistics.mean(meaning), 3) if meaning else "",
            human_critical_pass=(all(_approved(rating["critical_values_correct"]) for rating in explicit_critical)
                                 if explicit_critical else "unrated"),
            human_reference_approved=(all(_approved(rating.get("reference_approved")) for rating in human)
                                      if human else "unrated"),
        )
        rows.append(row)
    fields = ["case_id", "mode", "input_kind", "status", "source_language", "target_language",
              "source_text", "translation", "reference_draft", "reference_status",
              "numeric_surface_check", "bilingual_ratings", "mean_meaning_rating",
              "human_critical_pass", "human_reference_approved", "measurement",
              "server_pipeline_ms", "stt_ms", "mt_ms", "tts_ms", "request_to_result_ms", "error"]
    write_csv(args.output_dir / "case_report.csv", fields, rows)
    # Exclude demo/simulated/failed timings; typed text still does not measure STT.
    timings = [float(row["server_pipeline_ms"]) for row in rows
               if row.get("mode") == "live" and row.get("status") == "complete"
               and row.get("measurement") == "server_pipeline"
               and isinstance(row.get("server_pipeline_ms"), (int, float))
               and math.isfinite(row["server_pipeline_ms"]) and row["server_pipeline_ms"] >= 0]
    summary = {
        "cases_attempted": len(rows), "cases_completed": sum(row["status"] == "complete" for row in rows),
        "cases_with_bilingual_ratings": sum(row["bilingual_ratings"] > 0 for row in rows),
        "live_server_timing_count": len(timings),
        "live_server_pipeline_p50_ms": statistics.median(timings) if timings else None,
        "live_server_pipeline_p95_ms": percentile(timings, 0.95),
        "timing_boundary": "typed text server pipeline, excludes microphone, STT, network playback and receiver audio",
        "semantic_accuracy": "requires external bilingual ratings; numeric checks do not certify translation",
        "dataset_status": "small synthetic author-drafted set; not a representative benchmark",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template", help="Write an empty bilingual review CSV")
    template.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    template.add_argument("--output", type=Path, default=ROOT / "review-template.csv")
    collect_parser = sub.add_parser("collect", help="Submit actual typed utterances to a running server (uses provider credits in live mode)")
    collect_parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    collect_parser.add_argument("--api-url", default="http://localhost:8000")
    collect_parser.add_argument("--expected-mode", choices=["live", "demo"], default="live")
    collect_parser.add_argument("--output", type=Path, default=ROOT / "results" / "run.jsonl")
    collect_parser.add_argument("--timeout", type=float, default=45)
    collect_parser.add_argument("--limit", type=int, default=0)
    report_parser = sub.add_parser("report", help="Report recorded outputs; no provider access")
    report_parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    report_parser.add_argument("--predictions", type=Path, required=True)
    report_parser.add_argument("--ratings", type=Path)
    report_parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    if args.command == "template":
        write_csv(args.output, RATING_COLUMNS, [{"case_id": case["id"]} for case in load_jsonl(args.dataset)])
    elif args.command == "collect":
        collect(args)
    else:
        report(args)


if __name__ == "__main__":
    main()
