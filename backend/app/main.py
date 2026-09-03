from __future__ import annotations

import logging
import os
import tempfile
import time

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import supabase_client
from .audio_pipeline import analyze_recording_with_timeout, convert_to_wav
from .claude_plan import build_rubric_feedback, generate_plan
from .link_fetch import LinkFetchError, fetch_audio_from_url
from .reference_compare import compare_to_reference

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rehearsal-coach")

app = FastAPI(title="Rehearsal Coach analysis service")

allowed_origins = [
    origin.strip()
    for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://bvhart1.github.io,http://localhost:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _require_user_id(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    user_id = supabase_client.get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


class AnalyzeRequest(BaseModel):
    source_url: str | None = None
    reference_source_url: str | None = None


@app.post("/analyze/{rehearsal_id}", status_code=202)
def analyze(
    rehearsal_id: str,
    background_tasks: BackgroundTasks,
    body: AnalyzeRequest | None = None,
    authorization: str | None = Header(None),
) -> dict:
    user_id = _require_user_id(authorization)

    rehearsal = supabase_client.fetch_rehearsal(rehearsal_id)
    if not rehearsal:
        raise HTTPException(status_code=404, detail="Rehearsal not found")
    if rehearsal["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Rehearsal not found")
    if rehearsal["status"] == "processing":
        raise HTTPException(status_code=409, detail="Already processing")

    supabase_client.update_rehearsal_status(rehearsal_id, "processing")
    source_url = body.source_url if body else None
    reference_source_url = body.reference_source_url if body else None
    background_tasks.add_task(
        _run_pipeline,
        rehearsal_id,
        user_id,
        rehearsal["audio_path"],
        source_url,
        rehearsal.get("piece_title"),
        rehearsal.get("composer"),
        rehearsal.get("reference_audio_path"),
        reference_source_url,
    )
    return {"status": "processing"}


def _fetch_and_convert(
    tmpdir: str,
    filename_prefix: str,
    storage_path: str | None,
    source_url: str | None,
    on_new_storage_path,
) -> str:
    """Downloads or fetches an audio input, converts it to WAV, returns the WAV path."""
    if source_url:
        data, ext = fetch_audio_from_url(source_url)
        input_path = os.path.join(tmpdir, f"{filename_prefix}_input{ext}")
        with open(input_path, "wb") as f:
            f.write(data)
        on_new_storage_path(data, ext)
    else:
        raw_bytes = supabase_client.download_audio(storage_path)
        suffix = os.path.splitext(storage_path)[1] or ".audio"
        input_path = os.path.join(tmpdir, f"{filename_prefix}_input{suffix}")
        with open(input_path, "wb") as f:
            f.write(raw_bytes)

    wav_path = os.path.join(tmpdir, f"{filename_prefix}_converted.wav")
    convert_to_wav(input_path, wav_path)
    return wav_path


def _run_pipeline(
    rehearsal_id: str,
    user_id: str,
    audio_path: str,
    source_url: str | None = None,
    piece_title: str | None = None,
    composer: str | None = None,
    reference_audio_path: str | None = None,
    reference_source_url: str | None = None,
) -> None:
    try:
        logger.info("Starting analysis for rehearsal %s", rehearsal_id)

        with tempfile.TemporaryDirectory() as tmpdir:
            def save_main_audio(data: bytes, ext: str) -> None:
                storage_path = f"{user_id}/{int(time.time() * 1000)}{ext}"
                supabase_client.upload_audio(storage_path, data)
                supabase_client.set_audio_path(rehearsal_id, storage_path)

            try:
                wav_path = _fetch_and_convert(tmpdir, "main", audio_path, source_url, save_main_audio)
            except LinkFetchError as exc:
                supabase_client.update_rehearsal_status(rehearsal_id, "failed", str(exc))
                return

            logger.info("Rehearsal %s: running tempo/rhythm analysis", rehearsal_id)
            analysis = analyze_recording_with_timeout(wav_path)
            logger.info(
                "Rehearsal %s: analysis found %d segment(s)",
                rehearsal_id,
                len(analysis.segments),
            )

            if not analysis.analyzable_segments:
                supabase_client.update_rehearsal_status(
                    rehearsal_id,
                    "failed",
                    "Couldn't detect a clear, steady beat anywhere in this recording. "
                    "Try a recording with less background noise, positioned closer to the ensemble.",
                )
                return

            reference_comparison = None
            if reference_audio_path or reference_source_url:
                try:
                    def save_reference_audio(data: bytes, ext: str) -> None:
                        ref_storage_path = f"{user_id}/reference-{int(time.time() * 1000)}{ext}"
                        supabase_client.upload_audio(ref_storage_path, data)
                        supabase_client.set_reference_audio_path(rehearsal_id, ref_storage_path)

                    logger.info("Rehearsal %s: fetching/converting reference recording", rehearsal_id)
                    ref_wav_path = _fetch_and_convert(
                        tmpdir, "reference", reference_audio_path, reference_source_url, save_reference_audio
                    )

                    logger.info("Rehearsal %s: comparing against reference recording", rehearsal_id)
                    reference_comparison = compare_to_reference(wav_path, ref_wav_path, analysis.segments)
                    logger.info(
                        "Rehearsal %s: reference alignment_quality=%s",
                        rehearsal_id,
                        reference_comparison.get("alignment_quality"),
                    )
                except Exception:  # noqa: BLE001 - a bad reference shouldn't sink the whole analysis
                    logger.exception(
                        "Rehearsal %s: reference comparison failed, continuing without it", rehearsal_id
                    )

        logger.info("Rehearsal %s: requesting plan from Claude", rehearsal_id)
        plan = generate_plan(
            analysis,
            piece_title=piece_title,
            composer=composer,
            reference_comparison=reference_comparison,
        )
        logger.info("Rehearsal %s: got plan with %d drill item(s)", rehearsal_id, len(plan.drill_items))

        supabase_client.clear_previous_plan(rehearsal_id)
        drill_items = [
            {
                "title": item.title,
                "description": item.description,
                "priority": item.priority,
                "suggested_minutes": item.suggested_minutes,
                "measures": item.location_label,
                "done": False,
            }
            for item in plan.drill_items
        ]
        rubric_feedback = build_rubric_feedback(plan.rubric_observations)
        supabase_client.write_plan(rehearsal_id, plan.summary, rubric_feedback, drill_items)
        supabase_client.update_rehearsal_status(rehearsal_id, "analyzed")
        logger.info("Finished analysis for rehearsal %s", rehearsal_id)
    except Exception as exc:  # noqa: BLE001 - report every failure back to the director
        logger.exception("Analysis failed for rehearsal %s", rehearsal_id)
        supabase_client.update_rehearsal_status(rehearsal_id, "failed", str(exc)[:500])
