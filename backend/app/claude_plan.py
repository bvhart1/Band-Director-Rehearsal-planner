"""Turns structured tempo/rhythm analysis into a plain-language rehearsal plan."""
from __future__ import annotations

from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from .audio_pipeline import AnalysisResult

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """\
You are an assistant to a school band director (marching band, jazz band, or \
concert band). You are given structured tempo and rhythm-consistency data \
computed from a rehearsal recording - tempo estimates, tempo drift (speeding \
up or slowing down within a passage), and a rhythm-consistency score (0-100, \
where 100 means the ensemble's beat timing was very tight) for each \
uninterrupted playing segment of the rehearsal.

Turn this into a concrete, prioritized rehearsal plan for the director's next \
rehearsal. Rules:

- Only comment on tempo and rhythmic ensemble timing. You have no pitch, \
  intonation, or balance data - do not invent or imply any.
- The "approx_measure_range" values are rough estimates (the analysis assumes \
  4/4 time and has no sheet music to align against) - treat them as a rough \
  locator alongside the precise time_range, not an authoritative measure count.
- Prioritize segments with the largest tempo drift and lowest consistency \
  scores - those are where the ensemble most needs focused drilling.
- Write for a band director audience: practical, encouraging, specific. \
  Reference the actual time ranges/measure estimates from the data.
- Each drill item should be something a director can literally do in \
  rehearsal (e.g. "Isolate mm. 8-15 with a metronome at 90 BPM, then \
  incrementally increase to performance tempo").
- suggested_minutes should sum to a realistic rehearsal chunk (roughly 15-40 \
  minutes total across all drill items, scaled to how much needs work).
- If the data shows a genuinely clean, consistent rehearsal, say so - don't \
  manufacture problems.
"""


class DrillItemOut(BaseModel):
    title: str = Field(description="Short imperative title, e.g. 'Tighten the pickup into m. 40'")
    description: str = Field(description="1-3 sentences: what to do and why, referencing the data")
    priority: Literal["high", "medium", "low"]
    suggested_minutes: int = Field(ge=1, le=60)
    location_label: str = Field(
        description="Human-readable locator combining the time range and approx measure "
        "range, e.g. 'Measures ~8-15 (0:18-0:37)'"
    )


class RehearsalPlanOut(BaseModel):
    summary: str = Field(description="2-4 sentence overview of how the rehearsal went and what to focus on next")
    drill_items: list[DrillItemOut]


def build_user_payload(analysis: AnalysisResult) -> dict:
    return {
        "recording": analysis.to_dict(),
        "most_in_need_of_work": [s.to_dict() for s in analysis.most_in_need_of_work()],
    }


def generate_plan(analysis: AnalysisResult, *, client: anthropic.Anthropic | None = None) -> RehearsalPlanOut:
    client = client or anthropic.Anthropic()
    payload = build_user_payload(analysis)

    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _format_payload_for_prompt(payload)}],
        output_format=RehearsalPlanOut,
    )
    return response.parsed_output


def _format_payload_for_prompt(payload: dict) -> str:
    import json

    return (
        "Here is the structured tempo/rhythm analysis for this rehearsal "
        "recording:\n\n" + json.dumps(payload, indent=2)
    )
