from __future__ import annotations

import os
from functools import lru_cache

from supabase import Client, create_client

AUDIO_BUCKET = "rehearsal-audio"


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, service_role_key)


def get_user_id_from_token(access_token: str) -> str | None:
    """Validate a Supabase auth access token and return the owning user's id."""
    client = get_service_client()
    try:
        result = client.auth.get_user(access_token)
    except Exception:
        return None
    if result is None or result.user is None:
        return None
    return result.user.id


def fetch_rehearsal(rehearsal_id: str) -> dict | None:
    client = get_service_client()
    response = client.table("rehearsals").select("*").eq("id", rehearsal_id).maybe_single().execute()
    return response.data


def update_rehearsal_status(rehearsal_id: str, status: str, error_message: str | None = None) -> None:
    client = get_service_client()
    client.table("rehearsals").update(
        {"status": status, "error_message": error_message}
    ).eq("id", rehearsal_id).execute()


def download_audio(storage_path: str) -> bytes:
    client = get_service_client()
    return client.storage.from_(AUDIO_BUCKET).download(storage_path)


def upload_audio(storage_path: str, data: bytes) -> None:
    client = get_service_client()
    client.storage.from_(AUDIO_BUCKET).upload(storage_path, data)


def set_audio_path(rehearsal_id: str, storage_path: str) -> None:
    client = get_service_client()
    client.table("rehearsals").update({"audio_path": storage_path}).eq("id", rehearsal_id).execute()


def clear_previous_plan(rehearsal_id: str) -> None:
    client = get_service_client()
    client.table("drill_items").delete().eq("rehearsal_id", rehearsal_id).execute()
    client.table("rehearsal_plans").delete().eq("rehearsal_id", rehearsal_id).execute()


def write_plan(rehearsal_id: str, summary: str, rubric_feedback: list[dict], drill_items: list[dict]) -> None:
    client = get_service_client()
    client.table("rehearsal_plans").insert(
        {"rehearsal_id": rehearsal_id, "summary": summary, "rubric_feedback": rubric_feedback}
    ).execute()
    if drill_items:
        rows = [{**item, "rehearsal_id": rehearsal_id} for item in drill_items]
        client.table("drill_items").insert(rows).execute()
