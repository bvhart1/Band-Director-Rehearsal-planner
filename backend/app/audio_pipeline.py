"""Tempo & rhythm-consistency analysis for a rehearsal recording.

No pitch/intonation analysis here by design (see project README) - full
ensemble mixes can't be reliably split into instrument stems without
source separation, so this module only looks at *when* things happen
(beat timing), not *what* is played.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

import librosa
import numpy as np

SAMPLE_RATE = 22050
BEATS_PER_MEASURE = 4  # assumed 4/4; see Segment.measure_range docstring

TOP_DB = 30.0  # librosa.effects.split silence threshold
MIN_SILENCE_GAP_S = 2.0  # stops shorter than this don't split a segment
MIN_SEGMENT_DURATION_S = 8.0  # segments shorter than this get merged into a neighbor
MAX_SEGMENT_DURATION_S = 75.0  # longer segments get subdivided for locality
MIN_BEATS_FOR_ANALYSIS = 6  # below this, tempo/consistency numbers are unreliable

# Coefficient-of-variation-to-score scaling: a segment with 0% inter-beat
# variation scores 100; one with ~50% variation (very ragged) scores 0.
CONSISTENCY_SCALE = 200.0


def convert_to_wav(input_path: str, output_path: str) -> None:
    """Normalize any input audio format to mono 22.05kHz WAV via ffmpeg."""
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", input_path,
            "-ac", "1", "-ar", str(SAMPLE_RATE),
            "-vn", output_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr[-2000:]}")


def format_time(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(round(seconds % 60))
    if secs == 60:
        minutes += 1
        secs = 0
    return f"{minutes}:{secs:02d}"


@dataclass
class Segment:
    start_time: float
    end_time: float
    tempo_bpm: float | None = None
    tempo_drift_percent: float | None = None
    rhythm_consistency_score: int | None = None
    beat_count: int = 0
    measure_range: str | None = None

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def time_range_label(self) -> str:
        return f"{format_time(self.start_time)}-{format_time(self.end_time)}"

    def severity(self) -> float:
        """Higher = more in need of rehearsal attention."""
        if self.tempo_drift_percent is None or self.rhythm_consistency_score is None:
            return -1.0
        return abs(self.tempo_drift_percent) * 1.5 + (100 - self.rhythm_consistency_score)

    def to_dict(self) -> dict:
        return {
            "start_time": round(self.start_time, 1),
            "end_time": round(self.end_time, 1),
            "time_range": self.time_range_label,
            "approx_measure_range": self.measure_range,
            "tempo_bpm": self.tempo_bpm,
            "tempo_drift_percent": self.tempo_drift_percent,
            "rhythm_consistency_score": self.rhythm_consistency_score,
            "beat_count": self.beat_count,
        }


def _find_raw_intervals(y: np.ndarray, sr: int) -> list[tuple[int, int]]:
    intervals = librosa.effects.split(y, top_db=TOP_DB, frame_length=2048, hop_length=512)
    return [(int(s), int(e)) for s, e in intervals]


def _merge_close_intervals(intervals: list[tuple[int, int]], sr: int) -> list[tuple[int, int]]:
    if not intervals:
        return []
    min_gap_samples = int(MIN_SILENCE_GAP_S * sr)
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end <= min_gap_samples:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))
    return merged


def _drop_or_merge_short_intervals(intervals: list[tuple[int, int]], sr: int) -> list[tuple[int, int]]:
    min_samples = int(MIN_SEGMENT_DURATION_S * sr)
    result: list[tuple[int, int]] = []
    for start, end in intervals:
        if end - start >= min_samples or not result:
            result.append((start, end))
        else:
            # too short to stand alone - fold into the previous segment
            prev_start, _ = result[-1]
            result[-1] = (prev_start, end)
    return result


def _subdivide_long_intervals(intervals: list[tuple[int, int]], sr: int) -> list[tuple[int, int]]:
    max_samples = int(MAX_SEGMENT_DURATION_S * sr)
    result: list[tuple[int, int]] = []
    for start, end in intervals:
        span = end - start
        if span <= max_samples:
            result.append((start, end))
            continue
        n_chunks = int(np.ceil(span / max_samples))
        chunk_size = span // n_chunks
        for i in range(n_chunks):
            chunk_start = start + i * chunk_size
            chunk_end = end if i == n_chunks - 1 else start + (i + 1) * chunk_size
            result.append((chunk_start, chunk_end))
    return result


def segment_recording(y: np.ndarray, sr: int) -> list[tuple[int, int]]:
    """Split a recording into playing segments, using stops as natural breakpoints."""
    intervals = _find_raw_intervals(y, sr)
    intervals = _merge_close_intervals(intervals, sr)
    intervals = _drop_or_merge_short_intervals(intervals, sr)
    intervals = _subdivide_long_intervals(intervals, sr)
    return intervals


def analyze_segment(y_seg: np.ndarray, sr: int, start_time: float, end_time: float) -> Segment:
    segment = Segment(start_time=start_time, end_time=end_time)

    _, beat_frames = librosa.beat.beat_track(y=y_seg, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    segment.beat_count = len(beat_times)

    if len(beat_times) < MIN_BEATS_FOR_ANALYSIS:
        return segment

    ibis = np.diff(beat_times)  # inter-beat intervals, seconds
    ibis = ibis[ibis > 0]
    if len(ibis) < MIN_BEATS_FOR_ANALYSIS - 1:
        return segment

    mean_ibi = float(np.mean(ibis))
    segment.tempo_bpm = round(60.0 / mean_ibi, 1)

    cv = float(np.std(ibis) / mean_ibi) if mean_ibi > 0 else 1.0
    segment.rhythm_consistency_score = int(round(np.clip(100 - cv * CONSISTENCY_SCALE, 0, 100)))

    midpoint = len(ibis) // 2
    if midpoint >= 2:
        first_half_tempo = 60.0 / np.mean(ibis[:midpoint])
        second_half_tempo = 60.0 / np.mean(ibis[midpoint:])
        if first_half_tempo > 0:
            drift = (second_half_tempo - first_half_tempo) / first_half_tempo * 100
            segment.tempo_drift_percent = round(float(drift), 1)

    return segment


def _assign_measure_ranges(segments: list[Segment]) -> None:
    """Approximate measure numbers by accumulating beat counts, assuming 4/4 time.

    This is a rough estimate (no score alignment available), meant to give
    directors a rough locator alongside the precise time range - not an
    authoritative measure count.
    """
    cumulative_beats = 0
    for seg in segments:
        if seg.beat_count == 0:
            seg.measure_range = None
            continue
        measure_start = cumulative_beats // BEATS_PER_MEASURE + 1
        cumulative_beats += seg.beat_count
        measure_end = cumulative_beats // BEATS_PER_MEASURE + 1
        seg.measure_range = f"~m. {measure_start}-{measure_end}"


@dataclass
class AnalysisResult:
    duration_seconds: float
    segments: list[Segment] = field(default_factory=list)

    @property
    def analyzable_segments(self) -> list[Segment]:
        return [s for s in self.segments if s.tempo_bpm is not None]

    def overall_average_tempo(self) -> float | None:
        analyzable = self.analyzable_segments
        if not analyzable:
            return None
        total_weight = sum(s.duration for s in analyzable)
        if total_weight == 0:
            return None
        weighted = sum(s.tempo_bpm * s.duration for s in analyzable)
        return round(weighted / total_weight, 1)

    def most_in_need_of_work(self, limit: int = 6) -> list[Segment]:
        return sorted(self.analyzable_segments, key=lambda s: s.severity(), reverse=True)[:limit]

    def to_dict(self) -> dict:
        return {
            "duration_seconds": round(self.duration_seconds, 1),
            "duration_label": format_time(self.duration_seconds),
            "overall_average_tempo_bpm": self.overall_average_tempo(),
            "segment_count": len(self.segments),
            "analyzable_segment_count": len(self.analyzable_segments),
            "segments": [s.to_dict() for s in self.segments],
        }


def analyze_recording(wav_path: str) -> AnalysisResult:
    y, sr = librosa.load(wav_path, sr=SAMPLE_RATE, mono=True)
    duration = float(len(y) / sr)

    raw_segments = segment_recording(y, sr)

    segments: list[Segment] = []
    for start_sample, end_sample in raw_segments:
        start_time = start_sample / sr
        end_time = end_sample / sr
        y_seg = y[start_sample:end_sample]
        segments.append(analyze_segment(y_seg, sr, start_time, end_time))

    _assign_measure_ranges(segments)

    return AnalysisResult(duration_seconds=duration, segments=segments)
