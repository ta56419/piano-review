"""Read the score's MIDI time grid without renumbering an excerpt."""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict, deque
from pathlib import Path


def parse_midi(path: str | Path) -> dict:
    """Parse notes, all tempo changes and meter changes from a type 0/1 MIDI."""
    import mido

    midi = mido.MidiFile(str(path))
    if midi.type not in (0, 1) or midi.ticks_per_beat <= 0:
        raise ValueError("Only synchronous MIDI with a positive PPQ is supported")
    tick = 0
    seconds = 0.0
    tempo = 500_000
    active = defaultdict(deque)
    notes = []
    tempos = [{"beat": 0.0, "seconds": 0.0, "bpm": 120.0,
               "microseconds_per_beat": tempo}]
    meters = [{"beat": 0.0, "numerator": 4, "denominator": 4}]
    for message in mido.merge_tracks(midi.tracks):
        seconds += mido.tick2second(message.time, midi.ticks_per_beat, tempo)
        tick += message.time
        beat = tick / midi.ticks_per_beat
        if message.type == "set_tempo":
            tempo = message.tempo
            entry = {"beat": beat, "seconds": seconds, "bpm": 60_000_000 / tempo,
                     "microseconds_per_beat": tempo}
            if tempos[-1]["beat"] == beat:
                tempos[-1] = entry
            else:
                tempos.append(entry)
        elif message.type == "time_signature":
            entry = {"beat": beat, "numerator": message.numerator,
                     "denominator": message.denominator}
            if meters[-1]["beat"] == beat:
                meters[-1] = entry
            else:
                meters.append(entry)
        elif message.type == "note_on" and message.velocity > 0:
            active[(message.channel, message.note)].append(
                (seconds, beat, message.velocity))
        elif message.type == "note_off" or (
            message.type == "note_on" and message.velocity == 0
        ):
            key = (message.channel, message.note)
            if active[key]:
                onset, start_beat, velocity = active[key].popleft()
                if seconds > onset:
                    notes.append({"pitch": message.note, "onset": onset,
                                  "offset": seconds, "duration": seconds - onset,
                                  "beat": start_beat, "duration_beats": beat - start_beat,
                                  "velocity": velocity})
    if any(active.values()):
        raise ValueError("Reference MIDI contains a note without a note-off")
    if not notes:
        raise ValueError("Reference MIDI contains no notes")

    def beat_seconds(value: float) -> float:
        change = tempos[bisect_right([t["beat"] for t in tempos], value) - 1]
        return change["seconds"] + (value - change["beat"]) * change[
            "microseconds_per_beat"] / 1_000_000

    end_beat = max(n["beat"] + n["duration_beats"] for n in notes)
    measures = []
    start = 0.0
    meter_index = 0
    while start < end_beat - 1e-7:
        while meter_index + 1 < len(meters) and meters[meter_index + 1]["beat"] <= start + 1e-7:
            meter_index += 1
        meter = meters[meter_index]
        end = start + meter["numerator"] * 4 / meter["denominator"]
        if meter_index + 1 < len(meters) and meters[meter_index + 1]["beat"] < end - 1e-7:
            raise ValueError("Meter change falls inside a measure; annotate pickup bars explicitly")
        measures.append({"number": len(measures) + 1, "start_beat": start,
                         "end_beat": end, "start": beat_seconds(start),
                         "end": beat_seconds(end), "numerator": meter["numerator"],
                         "denominator": meter["denominator"]})
        start = end
    starts = [measure["start_beat"] for measure in measures]
    notes.sort(key=lambda note: (note["onset"], note["pitch"]))
    for index, note in enumerate(notes):
        note["id"] = index
        note["measure"] = measures[bisect_right(starts, note["beat"] + 1e-8) - 1]["number"]
    return {"notes": notes, "measures": measures, "tempo_changes": tempos,
            "meter_changes": meters, "duration": max(n["offset"] for n in notes),
            "ticks_per_beat": midi.ticks_per_beat, "source_path": str(path)}
