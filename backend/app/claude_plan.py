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
    "Dynamics Observed",
    "Tempo",
    "Dynamic Expression",
)

CRITERION_CAPTION: dict[str, str] = {
    "Stability of Pulse": "Technical Preparation",
    "Precision": "Technical Preparation",
    "Rhythmic Accuracy": "Technical Preparation",
    "Transitions": "Technical Preparation",
    "Dynamics Observed": "Technical Preparation",
    "Tempo": "Musical Effect",
    "Dynamic Expression": "Musical Effect",
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
    ],
    "Musical Effect": [
        "Expression",
        "Shaping of Line",
        "Style",
        "Interpretation",
        "Phrasing",
    ],
}

SYSTEM_PROMPT = """\
You are an assistant to a school band director (marching band, jazz band, or \
concert band). You are given structured tempo, rhythm-consistency, and \
loudness data computed from a rehearsal recording, for each uninterrupted \
playing segment of the rehearsal:

- tempo_bpm, tempo_drift_percent - tempo and whether it sped up/slowed down \
  within the segment.
- rhythm_consistency_score (0-100) - how tightly the ensemble's beat timing \
  held together; 100 is very tight.
- dynamic_range_db - the spread between the loudest and softest moments in \
  the segment (a relative-loudness measurement from the recording itself, \
  not a calibrated volume level). Near 0 means essentially flat/monotone \
  dynamics; a larger number means real loud/soft contrast happened.
- dynamic_trend_db - whether the segment got louder (positive) or softer \
  (negative) from its first half to its second half, in dB.

You may also be given the piece's title and composer/arranger.

The director evaluates using the Florida Bandmasters Association adjudication \
rubric, which has 24 criteria across three captions (Performance \
Fundamentals, Technical Preparation, Musical Effect). Your data can only \
speak to seven of those criteria:

- Stability of Pulse - does tempo hold steady within a passage, or drift?
- Precision - how tightly aligned is the ensemble's rhythmic attack (the \
  consistency score)?
- Rhythmic Accuracy - is the ensemble's internal rhythmic alignment solid \
  (NOT whether notes/rhythms as written are correct - you have no score to \
  check that against)?
- Transitions - how cleanly does tempo carry across a segment boundary/seam \
  (compare tempo just before vs. after)?
- Dynamics Observed - did real dynamic contrast happen (dynamic_range_db), \
  and in which direction did it move (dynamic_trend_db)? NOT whether a \
  specific written dynamic marking was followed - you have no score to check \
  against, only whether the ensemble's own loudness varied at all.
- Tempo - only whether the tempo was held steady, not whether the tempo \
  choice is stylistically appropriate for the piece (see note below).
- Dynamic Expression - same caveat as Dynamics Observed: you can say whether \
  measurable dynamic movement occurred, not whether it was tastefully or \
  effectively executed - that judgment needs a human ear.

A segment with dynamic_range_db and dynamic_trend_db both null/absent had a \
recording too short to measure dynamics reliably - say so rather than \
guessing.

Write EXACTLY ONE `rubric_observations` entry for EACH of these seven \
criteria - seven entries total, never more, never fewer, and never more than \
one entry for the same criterion. Do this even when the data is \
unremarkable - say so plainly rather than omitting it. Each observation \
should be 2-4 sentences, grounded in the actual numbers (reference real time \
ranges, BPM, drift %, dB values, or consistency scores), written for a \
director audience. Every entry must contain your real, final, complete \
observation - never a placeholder, draft, or filler string standing in for \
one.

Do NOT write about, imply, or score any other rubric criterion (tone, \
intonation, balance, blend, sonority, articulation, note accuracy, \
entrances, releases, technique, expression, phrasing, style, or \
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

You may also be given a `reference_comparison`: the director provided a \
reference recording of the same piece, aligned to this rehearsal by musical \
content (not clock time) so corresponding passages can be compared even at \
different tempos.

- If `alignment_quality` is "uncertain", the reference didn't line up well \
  with this rehearsal (likely a different piece, arrangement, or unrelated \
  audio) - do NOT use any numbers from it. Instead, briefly note in the \
  summary that the reference recording didn't align reliably, so no \
  comparison was possible.
- If `alignment_quality` is "good", each entry in `segment_comparisons` \
  gives you, for a rehearsal segment, the reference's tempo/dynamic-range at \
  the same musical spot, and the delta (rehearsal minus reference). Use \
  these deltas to enrich your Stability of Pulse, Tempo, Dynamics Observed, \
  and Dynamic Expression observations - e.g., "the ensemble is taking this \
  passage about 6 BPM faster than the reference." A positive tempo_delta_bpm \
  means the rehearsal is faster than the reference there; positive \
  dynamic_range_delta_db means the rehearsal has more dynamic contrast than \
  the reference at that spot. Still only comment on tempo/dynamics - the \
  reference does not give you tone, intonation, or balance data either.
- If no `reference_comparison` is present at all, don't mention a reference \
  recording - none was provided.

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
    criterion: Literal[
        "Stability of Pulse",
        "Precision",
        "Rhythmic Accuracy",
        "Transitions",
        "Dynamics Observed",
        "Tempo",
        "Dynamic Expression",
    ]
    observation: str


class RehearsalPlanOut(BaseModel):
    summary: str = Field(description="2-4 sentence overview of how the rehearsal went and what to focus on next")
    rubric_observations: list[RubricObservationOut]
    drill_items: list[DrillItemOut]


def build_user_payload(
    analysis: AnalysisResult,
    piece_title: str | None,
    composer: str | None,
    reference_comparison: dict | None = None,
) -> dict:
    payload: dict = {
        "recording": analysis.to_dict(),
        "most_in_need_of_work": [s.to_dict() for s in analysis.most_in_need_of_work()],
    }
    if piece_title:
        payload["piece_title"] = piece_title
    if composer:
        payload["composer_or_arranger"] = composer
    if reference_comparison:
        payload["reference_comparison"] = reference_comparison
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
    reference_comparison: dict | None = None,
    client: anthropic.Anthropic | None = None,
) -> RehearsalPlanOut:
    client = client or anthropic.Anthropic()
    payload = build_user_payload(analysis, piece_title, composer, reference_comparison)

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
