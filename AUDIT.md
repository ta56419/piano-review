# Assignment audit

Review date: 2026-11-17. Scope: recorded piano performance, the supplied real clip and a labeled synthetic control. No live lessons, chat or account features.

| VSA requirement | Evidence checked | Result |
|---|---|---|
| Analyze actual video audio | FFmpeg extraction; fresh ONNX inference; audio/model hashes; original and working MP4 hashes compared | Pass. Source unchanged. No score enters the decoder. |
| Detect wrong notes | Controlled WAV spectrum around 6.62 s peaks at 739.87 Hz (F♯5), where score measure 2 expects F5; pipeline independently reports 6.5983 s | Pass on labeled control. Real performer pitch mistakes remain unverified. |
| Detect timing deviations | Independent F5 band-energy rise near 11.5957 s; fixture schedules 11.6 s versus nominal 11.4 s; model reports 11.6048 s against fitted 11.398 s | Pass on control: +207 ms, tolerance ±120 ms. |
| Correct measure and explanation | Full 35-measure MIDI searched; first 11 measures independently transcribed from retained LilyPond and compared; controlled findings at measures 2 and 3 | Pass. Exact pitch names, expected/detected onsets and clickable replay are exposed. |
| Accuracy, error count, measures and advice after playback | Independently counted 48 reference events, no extras; two unique findings; `100*(1-2/48)=95.8`; browser end/reopen checks | Pass. Inline report shows 95.8%, 2, measures 2/3, slower practice, pitch checking and metronome advice. |

## Material fixes

- Reproduced dropped first/last omissions in complete bars. Semi-global alignment legitimately ignores the surrounding score, but its free endpoints also hid missing boundary notes. Complete scored measures now include every unpaired reference note as missing. Partial bars remain excluded.
- Reproduced `accuracy=100` for clean model-only evidence. Model-only accuracy now stays null regardless of the number of differences; raw agreement remains available separately.
- Switching samples now clears old findings, measure controls and status while loading. Playback/report controls are disabled until the new data arrives. A recomputation finishing after a switch names the sample it updated instead of claiming that the visible report changed.
- Added regression checks for both scoring defects. All 23 Python unit tests pass. Six JavaScript playback regression checks and JavaScript syntax checks pass.

- During the resumed website audit, reproduced paused timeline scrubbing leaving the comparison on the old measure, and the end-of-clip label falling back to the old selection. Manual scrubbing now follows the audio position even while paused; leading/trailing audio retains the nearest measure label. Explicit paused measure inspection and finding lead-ins remain intact. Verified in the browser after bumping the JavaScript asset version.
- Strengthened the assignment audit to assert fixture recovery, unique finding counts, type breakdown, affected measures and advice alongside independent spectral/onset checks.

## Real clip: what is and is not established

Fresh selected-decoder inference emits 243 events, aligns to measures 1–11 and matches all 176 reference pitches. It leaves 67 extra model candidates and one timing candidate. Performer accuracy is null; model/score agreement is 72.0%. Neither 176 pitch matches nor zero confirmed errors establishes a perfect performance.

The clock is `0.850784886 * score_seconds + 0.168638845`; median absolute onset residual is 14.9 ms. Measure 11 ends at 37.60317 s, inside the 37.64095 s decoded audio. Measure 12 is excluded. The alignment location margin is 0.05309 per observed note; this is a heuristic, not a probability.

The last B4 is detected at 37.2099 s versus the global-clock expectation of 37.3905 s (−181 ms), with activation 0.586203. It is at the clip ending and nearly simultaneous with the preceding detected G4. Pedal, repeated attacks, the ending gesture and transcription errors cannot be separated confidently here. The UI says “Проверьте начало си” and explicitly requests listening; this is not a confirmed pianist timing error. All raw detections remain accessible.

## Independent checks

`scripts/audit_assignment.py` blocks reads of fixture-answer paths while freshly analyzing both samples. The pipeline succeeds without such reads; only the subsequent audit opens the truth file. It compares summary, findings, comparisons, scoring, decoder and measure data against the packaged reports. Both match exactly (generation time is intentionally excluded).

The candidate decoder disables Melodia and inferred onsets and raises onset threshold from .50 to .60. Fresh baseline/candidate runs preserve all 176 real pitch matches, reduce extras from 178 to 67, and keep both controlled errors. Controlled accuracy stays 95.8%. Timing changes from the baseline's rounded 208 ms to 207 ms because the fitted clock changes slightly, while the detected onset stays 11.6048 s.

Both decoders recover 28/28 synthetic probe notes: 8 normal, 8 quiet at about −10.7 dB and 12 rapidly repeated at 180 ms spacing; zero extra probe events. This is a narrow synthetic check, not a benchmark of real quiet/pedaled piano. There is no score-conditioned note suppression.

## Browser checks

Launched through Demo.cmd. Checked 32 note buttons (16 pairs) on initial real load, paused selection of measure 2, playback-following measures, the real finding seek 37.2099→36.759899, controlled pitch seek 6.5983→6.1483, and timing seek 11.6048→11.1548. End-of-playback report and reopening work. Recomputed controlled audio while viewing the real clip: real data remained visible and the completion message correctly named the controlled clip. Desktop, 900 px and 390 px width checks show readable paired rows and no horizontal overflow; details expand in document flow.

## Limits relevant to review

This is a reproducible local demo, not calibrated music grading. Basic Pitch activation is not probability. The controlled timbre is synthesized with short articulation, not a real sampled piano. Pedal, dynamics and note-length accuracy are not evaluated. A single global affine clock preserves isolated delays but can flag expressive rubato. Repeated or weakly aligned excerpts can be excluded. Confirmed control findings validate two known cases, not broad real-world precision/recall.

Current handoff is website-only, at the user's request. Recording and export are deferred until explicit instruction after website review. Existing media from the interrupted session is not a verified deliverable for this build. No submission to VSA has been made.


## Interface refinement — 2026-11-17

Kept the existing section order and controls. Refined typography, spacing, note-row contrast, finding rows and button icons after inspecting tynskyi.pl in the browser. Added local Inter font files and license. Rewrote visible Russian copy in the HTML, frontend and report generator; finding titles now have one backend source. Short titles omit octaves, which remain visible in the note comparison and exact-event detail.

Added a regression check that an uncertain extra note never increases confirmed errors or affected measures. Its effect on raw model agreement is retained and explained in analysis details. The real summary now leads with unconfirmed performer accuracy; the controlled report leads with 95.8%, followed by two errors, measures 2/3, advice and the 48-note denominator. No analysis thresholds, source audio or score data changed in this pass. Fresh inference and the independent assignment audit reproduce the same numerical results; packaged and recomputed report fields match including the revised copy.


Final browser pass: desktop 1366 px, intermediate 900 px, and narrow 390 px. No horizontal overflow or clipped note names. Real and controlled playback, paused measure selection, timeline scrubbing, all three 450 ms finding lead-ins, sample switching, end reports and reopening were checked. Both clips were recomputed through the UI after restarting with Demo.cmd. A controlled job completing while the real clip was selected kept the real data and named the completed sample correctly. At measure 11, the review section displayed nine notes and nine replay controls while confirmed errors remained zero. Browser console contained no errors in the final pass. Evidence and source hashes: reports/browser-verification.json. Recording remains deferred.
