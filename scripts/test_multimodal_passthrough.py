#!/usr/bin/env python3
"""E2E test for posthog-python's multimodal passthrough path.

Exercises `Posthog(_enable_multimodal_capture=True)`: AI wrapper events ride
the dedicated AI lane (POST `/i/v0/ai/batch/`) and skip media redaction, so
base64 media survives in `$ai_input` / `$ai_output_choices`.

Makes REAL provider calls (nothing stubbed):
  1. audio-in-out     OpenAI `gpt-audio`: real speech recording in, mp3 audio out.
  2. image-openai     OpenAI vision chat: real photo in, text out.
  3. image-anthropic  Anthropic: the same photo in, text out.
  4. video-gemini     Gemini: synthetic MP4 in, text out.
  5. bigaudio-wav-out OpenAI `gpt-audio` with WAV output: deliberately a >1MB
                      event to probe capture/ingestion size handling.
  6. imagegen-gemini  (--with-imagegen) Gemini image model: text in, generated
                      image out. Off by default: free-tier Gemini keys have
                      zero image-gen quota. Note generated-image capture has no
                      OpenAI path today (`images` API unwrapped; Responses
                      `image_generation_call` dropped by the converter).

Input media comes from the open internet (Wikimedia Commons: an Eiffel Tower
photo and Neil Armstrong's "one small step" recording); the color-sequence
video is synthesized with ffmpeg. The script then polls local ClickHouse's
ai_events table (where ingestion splits AI events, stripping heavy props from
the events table) until the events land, and asserts the media arrived
unredacted — either still inline as base64 or offloaded by ingestion to blob
storage as a `phaiblob://` URI of the exact original byte size.

Usage:
    op run --env-file=.env -- uv run scripts/test_multimodal_passthrough.py

Environment:
    POSTHOG_HOST        default http://localhost:8010
    POSTHOG_API_KEY     auto-fetched from localhost when unset
    OPENAI_API_KEY      required
    GEMINI_API_KEY      required
    ANTHROPIC_API_KEY   required
"""

import argparse
import base64
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import uuid

import requests
from dotenv import load_dotenv

from posthog import Posthog
from posthog.ai.anthropic import Anthropic as PostHogAnthropic
from posthog.ai.gemini import Client as GeminiClient
from posthog.ai.openai import OpenAI
from posthog.ai.sanitization import REDACTED_IMAGE_PLACEHOLDER

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from get_localhost_api_key import get_api_key as get_localhost_api_key

DEFAULT_HOST = "http://localhost:8010"
DEV_LOGIN = {"email": "test@posthog.com", "password": "12345678"}
COMMONS_UA = "posthog-llma-e2e/1.0 (carlos@posthog.com)"
EIFFEL_URL = "https://commons.wikimedia.org/wiki/Special:FilePath/Tour_Eiffel_Wikimedia_Commons.jpg?width=800"
ARMSTRONG_URL = "https://commons.wikimedia.org/wiki/Special:FilePath/Armstrong_Small_Step.ogg"


def download(url: str) -> bytes:
    resp = requests.get(url, headers={"User-Agent": COMMONS_UA}, timeout=30)
    resp.raise_for_status()
    return resp.content


def fetch_media(tmp_dir: str) -> dict:
    """Real internet media (Wikimedia Commons) plus a synthetic color video."""
    jpg_bytes = download(EIFFEL_URL)

    ogg = os.path.join(tmp_dir, "armstrong.ogg")
    mp3 = os.path.join(tmp_dir, "armstrong.mp3")
    with open(ogg, "wb") as f:
        f.write(download(ARMSTRONG_URL))
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", ogg, "-ac", "1", "-b:a", "64k", mp3],
        check=True,
    )
    with open(mp3, "rb") as f:
        mp3_bytes = f.read()

    mp4 = os.path.join(tmp_dir, "video.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1:r=12",
            "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1:r=12",
            "-f", "lavfi", "-i", "color=c=green:s=320x240:d=1:r=12",
            "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", mp4,
        ],
        check=True,
    )
    with open(mp4, "rb") as f:
        mp4_bytes = f.read()

    print(
        f"Media: eiffel.jpg {len(jpg_bytes):,}B (Commons), "
        f"armstrong.mp3 {len(mp3_bytes):,}B (Commons ogg -> mp3), "
        f"video.mp4 {len(mp4_bytes):,}B (synthetic)"
    )
    return {"jpg": jpg_bytes, "mp3": mp3_bytes, "mp4": mp4_bytes}


def run_audio_in_out(ph, media, ids, model, audio_format="mp3"):
    # mp3 output keeps the event well under local Kafka's ~1MB message cap;
    # the bigaudio case requests wav to deliberately produce a >1MB event and
    # probe how capture/ingestion handles it.
    client = OpenAI(posthog_client=ph)
    response = client.chat.completions.create(
        model=model,
        modalities=["text", "audio"],
        audio={"voice": "alloy", "format": audio_format},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "This is a famous historical recording. Quote what the speaker says, then say why it is famous.",
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {"data": media["mp3_b64"], "format": "mp3"},
                    },
                ],
            }
        ],
        **ids,
    )
    message = response.choices[0].message
    audio = getattr(message, "audio", None)
    answer = audio.transcript if audio else message.content
    print(f"  answer: {answer!r}")
    print(f"  generated audio: {len(audio.data) if audio else 0:,} base64 chars")


def run_image_openai(ph, media, ids, model):
    client = OpenAI(posthog_client=ph)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What landmark is shown in this photo? Answer in one short sentence."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{media['jpg_b64']}"},
                    },
                ],
            }
        ],
        **ids,
    )
    print(f"  answer: {response.choices[0].message.content!r}")


def run_image_anthropic(ph, media, ids, model):
    client = PostHogAnthropic(posthog_client=ph)
    response = client.messages.create(
        model=model,
        max_tokens=100,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": media["jpg_b64"]},
                    },
                    {"type": "text", "text": "What landmark is shown in this photo? Answer in one short sentence."},
                ],
            }
        ],
        **ids,
    )
    print(f"  answer: {response.content[0].text!r}")


def run_video_gemini(ph, media, ids, model):
    client = GeminiClient(api_key=os.environ["GEMINI_API_KEY"], posthog_client=ph)
    # Dict-form parts, not types.Part.from_bytes: the SDK's gemini converter
    # drops typed Part objects whose .text is None (media parts become
    # content: null), while dict inline_data parts survive into $ai_input.
    response = client.models.generate_content(
        model=model,
        contents=[
            {
                "role": "user",
                "parts": [
                    {"inline_data": {"mime_type": "video/mp4", "data": media["mp4_b64"]}},
                    {"text": "This video shows a sequence of solid colors. Name the colors in the order they appear."},
                ],
            }
        ],
        **ids,
    )
    print(f"  answer: {response.text!r}")


def run_imagegen_gemini(ph, media, ids, model):
    client = GeminiClient(api_key=os.environ["GEMINI_API_KEY"], posthog_client=ph)
    response = client.models.generate_content(
        model=model,
        contents=["Generate a simple flat illustration of a hedgehog working on a laptop."],
        **ids,
    )
    generated = 0
    for part in response.candidates[0].content.parts:
        inline = getattr(part, "inline_data", None)
        if inline and inline.data:
            generated = len(inline.data)
            print(f"  generated image: {generated:,}B ({inline.mime_type})")
    if not generated:
        print(f"  no image in response: {response.text!r}")


def dev_session(host: str) -> requests.Session:
    session = requests.Session()
    resp = session.post(f"{host}/api/login", json=DEV_LOGIN)
    resp.raise_for_status()
    return session


def fetch_ai_event(clickhouse_url: str, trace_id: str):
    """Read from ClickHouse's ai_events table: local ingestion splits AI events
    there and strips the heavy props from the plain events table."""
    query = (
        "SELECT input, output_choices FROM posthog.ai_events "
        f"WHERE trace_id = '{trace_id}' AND event = '$ai_generation' "
        "FORMAT JSONCompact"
    )
    resp = requests.post(clickhouse_url, data=query)
    resp.raise_for_status()
    rows = resp.json()["data"]
    return rows[0] if rows else None


def as_json_text(value) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def probe(b64: str) -> str:
    """A distinctive mid-payload slice: present iff the base64 survived unredacted."""
    return b64[len(b64) // 2 : len(b64) // 2 + 48]


def media_intact(payload: str, b64: str, raw_size: int) -> bool:
    """The media survived if it is inline (base64 intact) or was offloaded by
    ingestion to blob storage (phaiblob:// URI carrying the exact byte size)."""
    return probe(b64) in payload or ("phaiblob://" in payload and f"size={raw_size}" in payload)


def verify(host: str, clickhouse_url: str, media: dict, traces: dict, timeout: float) -> bool:
    project = dev_session(host).get(f"{host}/api/projects/@current").json()
    print(f"Verifying ingestion in project {project['id']} ({project.get('name')})...")

    pending = dict(traces)
    events = {}
    deadline = time.monotonic() + timeout
    while pending and time.monotonic() < deadline:
        for case, trace_id in list(pending.items()):
            row = fetch_ai_event(clickhouse_url, trace_id)
            if row:
                events[case] = tuple(as_json_text(v) for v in row)
                del pending[case]
        if pending:
            time.sleep(3)
    for case in pending:
        print(f"  FAIL  {case}: ai_events row never arrived (waited {timeout:.0f}s — dropped by capture/ingestion?)")

    ok = not pending

    def check(name: str, condition: bool):
        nonlocal ok
        print(f"  {'PASS' if condition else 'FAIL'}  {name}")
        ok = ok and condition

    checks = {
        "audio-in-out": [
            ("input MP3 intact (inline or blob)", lambda i, o: media_intact(i, media["mp3_b64"], len(media["mp3"]))),
            ("generated audio in output_choices", lambda i, o: '"type": "audio"' in o or '"type":"audio"' in o),
            ("generated audio payload present", lambda i, o: len(o) > 50_000 or "phaiblob://" in o),
        ],
        "image-openai": [
            ("input JPEG intact (inline or blob)", lambda i, o: media_intact(i, media["jpg_b64"], len(media["jpg"]))),
        ],
        "image-anthropic": [
            ("input JPEG intact (inline or blob)", lambda i, o: media_intact(i, media["jpg_b64"], len(media["jpg"]))),
        ],
        "video-gemini": [
            ("input MP4 intact (inline or blob)", lambda i, o: media_intact(i, media["mp4_b64"], len(media["mp4"]))),
            ("video mime type preserved", lambda i, o: "video/mp4" in i),
        ],
        "imagegen-gemini": [
            ("generated image in output_choices", lambda i, o: "image/" in o),
            ("generated image payload present", lambda i, o: len(o) > 100_000 or "phaiblob://" in o),
        ],
        "bigaudio-wav-out": [
            ("input MP3 intact (inline or blob)", lambda i, o: media_intact(i, media["mp3_b64"], len(media["mp3"]))),
            ("large generated WAV in output_choices", lambda i, o: len(o) > 500_000 or "phaiblob://" in o),
        ],
    }
    for case, case_checks in checks.items():
        if case not in events:
            continue
        input_text, output_text = events[case]
        for name, condition in case_checks:
            check(f"{case}: {name}", condition(input_text, output_text))
        check(f"{case}: no redaction placeholder", REDACTED_IMAGE_PLACEHOLDER not in input_text + output_text)

    for case, trace in traces.items():
        status = "ok" if case in events else "MISSING"
        print(f"  {case} [{status}]: {host}/project/{project['id']}/llm-analytics/traces/{trace}")
    return ok


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.getenv("POSTHOG_HOST", DEFAULT_HOST))
    parser.add_argument("--distinct-id", default=os.getenv("POSTHOG_DISTINCT_ID", "multimodal-e2e-user"))
    parser.add_argument("--openai-audio-model", default="gpt-audio")
    parser.add_argument("--openai-vision-model", default="gpt-4o-mini")
    parser.add_argument("--anthropic-model", default="claude-sonnet-4-5-20250929")
    parser.add_argument("--gemini-model", default="gemini-2.5-flash")
    parser.add_argument("--gemini-image-model", default="gemini-2.5-flash-image")
    parser.add_argument(
        "--with-imagegen",
        action="store_true",
        help="Include the Gemini image-generation case (needs a paid-tier Gemini key)",
    )
    parser.add_argument("--verify-timeout", type=float, default=120.0)
    parser.add_argument("--clickhouse-url", default="http://localhost:8123")
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip server-side checks (use when pointing at a non-dev instance without local ClickHouse)",
    )
    args = parser.parse_args()

    for key in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        if not os.getenv(key):
            print(f"{key} is not set — run via: op run --env-file=.env -- uv run scripts/test_multimodal_passthrough.py")
            return 1

    api_key = os.getenv("POSTHOG_API_KEY") or get_localhost_api_key(host=args.host)
    logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")

    label = f"multimodal-e2e-{uuid.uuid4().hex[:8]}"
    print(f"Batch label: {label}")
    print(f"Target: {args.host} (key {api_key[:9]}...)")

    with tempfile.TemporaryDirectory() as tmp_dir:
        media = fetch_media(tmp_dir)
    for kind in ("jpg", "mp3", "mp4"):
        media[f"{kind}_b64"] = base64.b64encode(media[kind]).decode()

    ph = Posthog(api_key, host=args.host, _enable_multimodal_capture=True)

    cases = [
        ("audio-in-out", run_audio_in_out, args.openai_audio_model),
        ("image-openai", run_image_openai, args.openai_vision_model),
        ("image-anthropic", run_image_anthropic, args.anthropic_model),
        ("video-gemini", run_video_gemini, args.gemini_model),
        (
            "bigaudio-wav-out",
            lambda ph, media, ids, model: run_audio_in_out(ph, media, ids, model, audio_format="wav"),
            args.openai_audio_model,
        ),
    ]
    if args.with_imagegen:
        cases.append(("imagegen-gemini", run_imagegen_gemini, args.gemini_image_model))
    else:
        print("Skipping imagegen-gemini (free-tier Gemini has no image-gen quota; pass --with-imagegen with a paid key)")
    traces = {}
    failures = []
    for case, runner, model in cases:
        traces[case] = str(uuid.uuid4())
        print(f"[{case}] {model}")
        ids = {
            "posthog_distinct_id": args.distinct_id,
            "posthog_trace_id": traces[case],
            "posthog_properties": {"e2e_label": label, "e2e_case": case},
        }
        try:
            runner(ph, media, ids, model)
        except Exception as e:
            print(f"  CALL FAILED: {e}")
            failures.append(case)
            del traces[case]

    ai_lane_used = ph._ai_lane._started
    print(f"AI lane engaged: {ai_lane_used} (analytics lane backlog: {ph._analytics_lane.queue.qsize()})")

    print("Flushing...")
    ph.flush(timeout_seconds=60)
    ph.shutdown()

    if failures:
        print(f"Provider calls failed for: {', '.join(failures)}")
    if not ai_lane_used:
        print("FAIL: events did not route through the dedicated AI lane")
        return 1

    if args.skip_verify:
        print("Skipping server-side verification (--skip-verify)")
        return 0 if not failures else 1

    passed = verify(args.host, args.clickhouse_url, media, traces, args.verify_timeout) and not failures
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
