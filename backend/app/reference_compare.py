"""Aligns a rehearsal recording against a reference recording and compares
tempo/dynamics at corresponding musical moments.

Alignment uses chroma-based Dynamic Time Warping (DTW) - a standard,
well-established music-information-retrieval technique (built into Librosa)
that matches moments by harmonic/pitch content, not clock time, so it still
works when the two recordings take the piece at different tempos throughout.

This only extends what we already measure (tempo, dynamics) with a "compared
to the reference" dimension - it does not add tone/intonation/balance
comparison, which would need timbral analysis this doesn't do.

Alignment quality varies by reference: a wrong piece, a very different
arrangement, or unrelated audio produces a poor alignment. ALIGNMENT_COST_
THRESHOLD gates that - low-confidence alignments are reported as such rather
than handed to Claude as if they were reliable.
"""
from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np

from .audio_pipeline import Segment, analyze_segment

CHROMA_HOP_LENGTH = 512

# Average per-frame cosine-distance cost along the DTW path. Calibrated
# against synthetic tests: a genuine match scored ~0.001, an unrelated pair
# scored ~0.35. This is a coarse heuristic, not a precise statistic.
ALIGNMENT_COST_THRESHOLD = 0.15


@dataclass
class SegmentComparison:
    rehearsal_time_range: str
    reference_time_range: str
    reference_tempo_bpm: float | None
    tempo_delta_bpm: float | None
    reference_dynamic_range_db: float | None
    dynamic_range_delta_db: float | None

    def to_dict(self) -> dict:
        return {
            "rehearsal_time_range": self.rehearsal_time_range,
            "reference_time_range": self.reference_time_range,
            "reference_tempo_bpm": self.reference_tempo_bpm,
            "tempo_delta_bpm": self.tempo_delta_bpm,
            "reference_dynamic_range_db": self.reference_dynamic_range_db,
            "dynamic_range_delta_db": self.dynamic_range_delta_db,
        }


def _align(reh_y: np.ndarray, ref_y: np.ndarray, sr: int) -> tuple[np.ndarray, float]:
    chroma_reh = librosa.feature.chroma_cqt(y=reh_y, sr=sr, hop_length=CHROMA_HOP_LENGTH)
    chroma_ref = librosa.feature.chroma_cqt(y=ref_y, sr=sr, hop_length=CHROMA_HOP_LENGTH)
    cost_matrix, warp_path = librosa.sequence.dtw(X=chroma_reh, Y=chroma_ref, metric="cosine")
    end_i, end_j = warp_path[0]  # warp_path is in reverse order before flipping
    avg_cost = float(cost_matrix[end_i, end_j] / len(warp_path))
    return warp_path[::-1], avg_cost


def _make_time_mapper(warp_path: np.ndarray, sr: int):
    def reh_time_to_ref_time(t: float) -> float:
        frame = librosa.time_to_frames(t, sr=sr, hop_length=CHROMA_HOP_LENGTH)
        idx = int(np.searchsorted(warp_path[:, 0], frame))
        idx = min(idx, len(warp_path) - 1)
        ref_frame = warp_path[idx, 1]
        return float(librosa.frames_to_time(ref_frame, sr=sr, hop_length=CHROMA_HOP_LENGTH))

    return reh_time_to_ref_time


def _compare_segment(segment: Segment, ref_y: np.ndarray, sr: int, mapper) -> SegmentComparison | None:
    ref_start = mapper(segment.start_time)
    ref_end = mapper(segment.end_time)
    if ref_end <= ref_start:
        return None

    ref_slice = ref_y[int(ref_start * sr):int(ref_end * sr)]
    ref_segment = analyze_segment(ref_slice, sr, ref_start, ref_end)

    tempo_delta = None
    if segment.tempo_bpm is not None and ref_segment.tempo_bpm is not None:
        tempo_delta = round(segment.tempo_bpm - ref_segment.tempo_bpm, 1)

    range_delta = None
    if segment.dynamic_range_db is not None and ref_segment.dynamic_range_db is not None:
        range_delta = round(segment.dynamic_range_db - ref_segment.dynamic_range_db, 1)

    return SegmentComparison(
        rehearsal_time_range=segment.time_range_label,
        reference_time_range=ref_segment.time_range_label,
        reference_tempo_bpm=ref_segment.tempo_bpm,
        tempo_delta_bpm=tempo_delta,
        reference_dynamic_range_db=ref_segment.dynamic_range_db,
        dynamic_range_delta_db=range_delta,
    )


def compare_to_reference(rehearsal_wav_path: str, reference_wav_path: str, segments: list[Segment]) -> dict:
    from .audio_pipeline import SAMPLE_RATE

    reh_y, sr = librosa.load(rehearsal_wav_path, sr=SAMPLE_RATE, mono=True)
    ref_y, _ = librosa.load(reference_wav_path, sr=SAMPLE_RATE, mono=True)

    warp_path, avg_cost = _align(reh_y, ref_y, sr)

    if avg_cost > ALIGNMENT_COST_THRESHOLD:
        return {
            "alignment_quality": "uncertain",
            "avg_alignment_cost": round(avg_cost, 3),
            "segment_comparisons": [],
        }

    mapper = _make_time_mapper(warp_path, sr)
    comparisons = []
    for segment in segments:
        if segment.tempo_bpm is None:
            continue
        comparison = _compare_segment(segment, ref_y, sr, mapper)
        if comparison:
            comparisons.append(comparison.to_dict())

    return {
        "alignment_quality": "good",
        "avg_alignment_cost": round(avg_cost, 3),
        "segment_comparisons": comparisons,
    }
