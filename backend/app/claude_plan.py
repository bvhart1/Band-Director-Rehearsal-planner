"""Turns structured tempo/rhythm analysis into a plain-language rehearsal plan.

Feedback is organized around the Florida Bandmasters Association concert-band
adjudication rubric (Performance Fundamentals / Technical Preparation /
Musical Effect), but this tool only measures tempo and rhythm timing - most
of that rubric's 24 criteria require judging tone, intonation, balance,
dynamics, or musical expression, none of which we have data for. RUBRIC_
constants below are the fixed, honest boundary of what we do and don't claim
to assess; Claude only ever writes observations for the assessable criteria,
never the rest.
"""
from __future__ import annotations

import json
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from .audio_pipeline import AnalysisResult

MODEL = "claude-opus-5"

ASSESSABLE_CRITERIA: tuple[str, ...] = (
    "Stability of Pulse",
    "Precision",
    "Rhythmic Accuracy",
    "Transitions",
    "Tempo",
)

CRITERION_CAPTION: dict[str, str] = {
    "Stability of Pulse": "Technical Preparation",
    "Precision": "Technical Preparation",
    "Rhythmic Accuracy": "Technical Preparation",
    "Transitions": "Technical Preparation",
    "Tempo": "Musical Effect",
}

CAPTION_ORDER: tuple[str, ...] = ("Performance Fundamentals", "Technical Preparation", "Musical Effect")

CAPTION_NOT_ASSESSED: dict[str, list[str]] = {
    "Performance Fundamentals": [
        "Tone Quality",
        "Intonation",
        "Balance",
        "Blend",
        "Band Sonority",
        "Physical Articulation",
    ],
    "Technical Preparation": [
        "Note Accuracy",
        "Entrances",
        "Releases",
        "Interpretive Articulation",
        "Clarity of Articulation",
        "Technique",
        "Dynamics Observed",
    ],
    "Musical Effect": [
        "Expression",
        "Shaping of Line",
        "Style",
        "Interpretation",
        "Phrasing",
        "Dynamic Expression",
    ],
}

SYSTEM_PROMPT = """\
You are an assistant to a school band director (marching band, jazz band, or \
concert band). You are given structured tempo and rhythm-consistency data \
computed from a rehearsal recording - tempo estimates, tempo drift (speeding \
up or slowing down within a passage), and a rhythm-consistency score (0-100, \
where 100 means the ensemble's beat timing was very tight) for each \
uninterrupted playing segment of the rehearsal. You may also be given the \
piece's title and composer/arranger.

The director evaluates using the Florida Bandmasters Association adjudication \
rubric, which has 24 criteria across three captions (Performance \
Fundamentals, Technical Preparation, Musical Effect). Your tempo/rhythm data \
can only speak to five of those criteria:

- Stability of Pulse - does tempo hold steady within a passage, or drift?
- Precision - how tightly aligned is the ensemble's rhythmic attack (the \
  consistency score)?
- Rhythmic Accuracy - is the ensemble's internal rhythmic alignment solid \
  (NOT whether notes/rhythms as written are correct - you have no score to \
  check that against)?
- Transitions - how cleanly does tempo carry across a segment boundary/seam \
  (compare tempo just before vs. after)?
- Tempo - only whether the tempo was held steady, not whether the tempo \
  choice is stylistically appropriate for the piece (see note below).

Write EXACTLY ONE `rubric_observations` entry for EACH of these five \
criteria - five entries total, never more, never fewer, and never more than \
one entry for the same criterion. Do this even when the data is \
unremarkable - say so plainly rather than omitting it. Each observation \
should be 2-4 sentences, grounded in the actual numbers (reference real time \
ranges, BPM, drift %, or consistency scores), written for a director \
audience. Every entry must contain your real, final, complete observation - \
never a placeholder, draft, or filler string standing in for one.

Do NOT write about, imply, or score any other rubric criterion (tone, \
intonation, balance, blend, sonority, articulation, note accuracy, \
entrances, releases, technique, dynamics, expression, phrasing, style, or \
interpretation) - you have no data on any of these. The app will separately \
and clearly label those as not assessed; do not blur that line by hedging \
comments about them yourself.

On piece title/composer, if given: you may use the title naturally in your \
prose (e.g., "In [Title], the tempo..."). Only state a specific fact about \
the piece itself (its typical tempo, era, style, form, or the composer's \
intent) if you are genuinely confident you know this exact piece well - \
concert band repertoire includes many pieces you may not know specifically. \
When you're not confident, do not guess or invent plausible-sounding details \
- just use the title as a label, not as a source of claims.

Beyond the rubric_observations, also produce the existing rehearsal-plan \
output:

- summary: 2-4 sentences overview of how the rehearsal went and what to \
  focus on next.
- drill_items: a concrete, prioritized list the director can literally run \
  in the next rehearsal.

Rules for drill_items:
- The "approx_measure_range" values are rough estimates (the analysis assumes \
  4/4 time and has no sheet music to align against) - treat them as a rough \
  locator alongside the precise time_range, not an authoritative measure count.
- Prioritize segments with the largest tempo drift and lowest consistency \
  scores - those are where the ensemble most needs focused drilling.
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


class RubricObservationOut(BaseModel):
    criterion: Literal["Stability of Pulse", "Precision", "Rhythmic Accuracy", "Transitions", "Tempo"]
    observation: str


class RehearsalPlanOut(BaseModel):
    summary: str = Field(description="2-4 sentence overview of how the rehearsal went and what to focus on next")
    rubric_observations: list[RubricObservationOut]
    drill_items: list[DrillItemOut]


def build_user_payload(analysis: AnalysisResult, piece_title: str | None, composer: str | None) -> dict:
    payload: dict = {
        "recording": analysis.to_dict(),
        "most_in_need_of_work": [s.to_dict() for s in analysis.most_in_need_of_work()],
    }
    if piece_title:
        payload["piece_title"] = piece_title
    if composer:
        payload["composer_or_arranger"] = composer
    return payload


def _is_placeholder(text: str) -> bool:
    return text.strip().lower() in ("placeholder", "")


def build_rubric_feedback(observations: list[RubricObservationOut]) -> list[dict]:
    # Guard against the model emitting duplicate/placeholder entries for a
    # criterion: drop stub text, then keep only the last real entry per
    # criterion so a leftover draft can never reach the director.
    last_by_criterion: dict[str, RubricObservationOut] = {}
    for obs in observations:
        if _is_placeholder(obs.observation):
            continue
        last_by_criterion[obs.criterion] = obs

    by_caption: dict[str, list[dict]] = {caption: [] for caption in CAPTION_ORDER}
    for criterion in ASSESSABLE_CRITERIA:
        obs = last_by_criterion.get(criterion)
        if not obs:
            continue
        by_caption[CRITERION_CAPTION[criterion]].append(
            {"criterion": obs.criterion, "observation": obs.observation}
        )

    return [
        {
            "caption": caption,
            "assessed": by_caption[caption],
            "not_assessed": CAPTION_NOT_ASSESSED[caption],
        }
        for caption in CAPTION_ORDER
    ]


def generate_plan(
    analysis: AnalysisResult,
    *,
    piece_title: str | None = None,
    composer: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> RehearsalPlanOut:
    client = client or anthropic.Anthropic()
    payload = build_user_payload(analysis, piece_title, composer)

    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _format_payload_for_prompt(payload)}],
        output_format=RehearsalPlanOut,
    )
    return response.parsed_output


def _format_payload_for_prompt(payload: dict) -> str:
    return (
        "Here is the structured tempo/rhythm analysis for this rehearsal "
        "recording:\n\n" + json.dumps(payload, indent=2)
    )
