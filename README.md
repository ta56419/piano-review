# Piano Review

A local FastAPI app that transcribes recorded piano audio, locates the excerpt in Bach's full BWV 846 MIDI, and links each difference to playback. The interface is in Russian. No account, API key, or hosted service is needed.

## Download and run

Download the repository ZIP and extract it, or clone it. Both input samples are included. On a new Windows machine, install Python 3.12 and follow **Fresh Windows setup** below before launching. The Python environment is not bundled.

## Run this copy

Double-click `Demo.cmd`, or run in PowerShell:

```powershell
Set-Location .\piano-review
.\Demo.cmd
```

Open <http://127.0.0.1:8765>. The launcher opens the browser when the server is ready. Keep its console open; Ctrl+C stops it. It reuses an already running Piano Review server. The bundled JSON reports load immediately; **Пересчитать** starts fresh audio extraction, model inference, alignment, and scoring.

## Fresh Windows setup

Tested on Windows x64 with Python **3.12.14**, Basic Pitch **0.4.0**, ONNX Runtime **1.20.1** (CPU), NumPy **1.26.4**, librosa **0.10.2.post1**, and imageio-ffmpeg **0.6.0** / FFmpeg **7.1**. Install Python 3.12 x64 with the Python launcher, then run from this folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-deps -r requirements.lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe .\scripts\launch.py
```

`requirements.lock.txt` contains the complete tested environment, including transitive packages. `--no-deps` is intentional: Basic Pitch's published dependency constraints predate this Python/NumPy combination and may otherwise select TensorFlow or incompatible versions. This is a tested ONNX configuration, not a claim of upstream Python 3.12 support. No package source was patched. Warnings about missing TensorFlow, CoreML and TFLite are expected; inference explicitly loads `nmp.onnx`. FFmpeg is supplied by imageio-ffmpeg, so it need not be on PATH. Setup requires internet; analysis is offline after installation.

The supplied performance video is included at `data/real.mp4`, together with the controlled WAV and reference score. Source SHA-256:

```text
6dbd34cc080b83d76f6e9eb2ba3a73d070fd0d0091f53010386f145652a63054
```

## Reproduce the analysis

```powershell
# Fresh inference on both inputs, then an independent controlled-fixture check:
.\.venv\Scripts\python.exe .\scripts\verify_pipeline.py

# Analyze one input (fresh model inference is the default):
.\.venv\Scripts\python.exe -m piano_review.pipeline --sample real
.\.venv\Scripts\python.exe -m piano_review.pipeline --sample controlled

# Rebuild the synthetic audio and its separate ground truth:
.\.venv\Scripts\python.exe .\scripts\render_controlled.py
.\.venv\Scripts\python.exe -m piano_review.pipeline --sample controlled

# Development only: rescore notes after checking the audio hash and decoder configuration:
.\.venv\Scripts\python.exe -m piano_review.pipeline --sample all --reuse-transcription

# Serve without opening a browser:
.\.venv\Scripts\python.exe -m uvicorn piano_review.api:app --host 127.0.0.1 --port 8765
```

The UI's recompute action never uses the transcription cache. Jobs are serialized; duplicate concurrent jobs are rejected. The API binds only to loopback. API documentation: <http://127.0.0.1:8765/api/docs>.

## Observed result

| Input | Aligned complete measures | Confirmed errors | Uncertain findings | Result |
|---|---|---:|---:|---|
| Actual TikTok audio | 1–11, 176 score notes | 0 | 68 | Performer accuracy unconfirmed; raw model/MIDI agreement 72.0% |
| Labeled controlled audio | 1–3, 48 score notes | 2 | 0 | 95.8% by the stated scoring rule |

The real video lasts about 37.63 seconds; FFmpeg decodes 37.64095 seconds of audio. The selected decoder emits 243 events; the retained baseline emits 354. All 176 reference pitches in measures 1–11 are matched in order. The remaining 67 events and one timing candidate are uncertain; sustained-note retriggers and overtones are a major observed transcription limitation. **72.0% is model/score agreement, not the pianist's accuracy.** Zero confirmed errors is also not proof of a flawless performance.

Real alignment uses `playback_seconds = 0.850785 × reference_seconds + 0.168639`. Median absolute onset residual is 14.9 ms. Measure 11 ends near 37.603 seconds; measure 12 is excluded. The MIDI's 4/4 grid and 60 BPM tempo were parsed, and the note sequence was checked against the supplied score's LilyPond source. In particular, the F-sharps in measures 6 and 10 are written in the score.

Controlled findings calculated from audio:

- **Measure 2, 6.5983 s:** expected F5 (77), observed F♯5 (78).
- **Measure 3, 11.6048 s:** F5 begins approximately **207 ms late** relative to the fitted expected onset of 11.398 s. The fixture deliberately delays it by 200 ms; the difference is transcription/alignment resolution.

The controlled WAV uses an original additive piano-like timbre at 50 BPM, with 600 ms leading silence and short 220 ms articulation. It preserves the excerpt's pitches and onsets except for the two deliberate edits. The first sustained rendering produced detector retriggers, so articulation was shortened before final verification. This makes a clean demonstration, not a representative benchmark of real piano recordings. Pedal and note-length accuracy are outside this fixture.

## Alignment and scoring

1. FFmpeg decodes mono 22,050 Hz PCM. Basic Pitch runs actual polyphonic ONNX inference; its raw arrays, MIDI and note events are saved.
2. Semi-global edit alignment searches the entire 35-measure reference. Pitch order, repeated notes, substitutions, omissions and extras participate in the match. Chord-order repair handles near-simultaneous notes.
3. A robust **single affine clock** estimates leading offset and overall tempo. Allowed time-scale range: 0.4–2.5. There is no local time warping, so an isolated late note remains late.
4. Location confidence requires at least 16 exact matches, 70% reference coverage, median onset residual no more than 180 ms, and a distinct-location cost margin of at least 0.005 per observed note. A measure is scored only when complete within a 45 ms boundary allowance and at least 55% of its pitches match. These are heuristic gates, not calibrated probabilities.
5. The timing tolerance is **±120 ms**. A substituted note counts once even if its timing also differs. A missing note seeks to its aligned expected onset.

```text
N = number of reference notes in scored measures
X = extra detected notes in those measures
E = affected note events (pitch substitutions + timing-only differences + missing + extra)
agreement = 100 × (1 − E / (N + X))
```

For model-only evidence, `accuracy` is always `null`, even if no differences are found. Any uncertain findings also prevent a verified score. Raw `model_agreement` lives under analysis details; the real-clip headline shows pitch matches and an explicit unverified-performance status. The displayed interval treats all uncertain events as errors versus none as errors with the same denominator. It is a scenario range, **not a statistical confidence interval**. Controlled score: `100 × (1 − 2/48) = 95.8%`.

Model-only differences in the real recording remain uncertain. For labeled controlled audio, a pitch/timing finding is confirmed only with model activation ≥0.65 and at least three stable nearby exact-pitch matches (also ≥60% of nearby matches). Missing/extra model events remain uncertain. Activation is not a calibrated probability. The analyzer never reads `controlled-truth.json`; `verify_pipeline.py` reads it only after reports have been produced and cannot rewrite findings.

## Small modules

| File | Responsibility |
|---|---|
| `piano_review/transcription.py` | Extraction, ONNX inference, model/audio hashes and raw outputs |
| `piano_review/reference.py` | MIDI notes, tempo/meter changes, original measure numbering |
| `piano_review/alignment.py` | Ordered excerpt search and constrained global clock |
| `piano_review/scoring.py` | Counts, uncertainty, timestamps, Russian explanations |
| `piano_review/controlled.py` | Audio fixture generation and separate read-only verification |
| `piano_review/comparison.py` | Per-measure expected/detected pairs; retains unmatched raw events |
| `piano_review/pipeline.py` | File orchestration and browser report adapter |
| `piano_review/api.py` | Thin FastAPI routes, serial background jobs, media range responses |
| `web/` | Buildless HTML/CSS/JavaScript player, timeline, findings and final report |

The structure follows the small functions, explicit validation, plain JSON reports and unittest checks used in [AI Docs Agent](https://github.com/ta56419/ai-docs-agent), [Customer Churn ML Platform](https://github.com/ta56419/customer-churn-ml-platform), and [LLM Eval Security Lab](https://github.com/ta56419/llm-eval-security-lab). The visual reference is [tynskyi.pl](https://tynskyi.pl/).

## Interface and Russian copy

The player, sample switch, measure strip, paired notes, findings, inline report and analysis details remain in the same layout. The visual pass follows the typography and charcoal/blue palette of tynskyi.pl: locally bundled Inter, consistent SVG controls, lighter note-grid borders and distinct reference/detection rows. The comparison uses four columns at widths up to 1100 px so notes remain legible; the mobile page keeps every section in normal document flow.

Finding labels come from the analysis report, rather than a second set of frontend sentences. The control reads **«Такт 2 · Фа-диез вместо фа»** and **«Такт 3 · Фа прозвучала на 207 мс позже»**. Octaves and exact timestamps remain in the paired notes and selected-note detail. Loading, playback errors, empty states and advice use shorter Russian text.

**«Ноты для проверки»** lists unmatched detections for the selected measure. Its displayed count equals the number of replay buttons. These notes do not enter the confirmed error count or its breakdown; a regression test checks this explicitly. They still affect raw model/MIDI agreement, which is labeled separately under analysis details. The real clip's final report explicitly says that performer accuracy is unconfirmed.

Inter is bundled under the SIL Open Font License (`web/fonts/OFL.txt`), from the Google Fonts Inter distribution. The interface makes no external font requests. SVG icons are local project assets.

## Note review and decoder choice

The first screen shows paired score/detected notes for measure 1. Selecting a measure preserves paused playback; playing follows the measure clock. Clicking a note or finding starts **450 ms before its timestamp**. Scrubbing the timeline while paused also updates the selected comparison; leading silence and the trailing audio keep the nearest measure label. At playback end, the report opens inline and can be reopened with **Итог разбора**. The controlled example opens on measure 2 with both findings visible.

The default decoder uses `onset_thresh=0.60`, `frame_thresh=0.30`, `infer_onsets=False`, and `melodia_trick=False`. Fresh inference compared it with the baseline (`0.50`, inferred onsets and Melodia enabled): real extras fell from 178 to 67 while retaining all 176 pitch matches. Both controlled findings remained, with 95.8%. The refitted controlled clock changes the rounded delay from 208 ms to 207 ms; the detected onset remains 11.6048 s. This is a measured clock difference, not a changed fixture.

An additional synthetic probe recovered 8/8 normal notes, 8/8 quiet notes (about −10.7 dB), and 12/12 rapid repeated notes at 180 ms spacing under both decoders, with no extras. This small articulated synthetic probe does not establish recall on real quiet, pedaled or fast piano. No score-based filtering suppresses detections. Both decoder event lists and the untouched ONNX output arrays are retained in `reports/*-notes.json` and `.npz`.

```powershell
.\.venv\Scripts\python.exe scripts\compare_decoders.py
.\.venv\Scripts\python.exe scripts\audit_assignment.py
```

## Website verification and review

**23 Python unit tests and 6 JavaScript playback regression checks pass.** Coverage includes substitutions counted once, missing notes including the first/last note of a complete measure, extras, isolated late notes, global tempo, mid-piece excerpts, chord order, partial bars, model-only uncertainty, comparison-data integrity and MIDI tempo/meter changes.

The assignment audit reruns both clips from audio with fixture-answer access blocked, compares the fresh semantic report fields with packaged results, independently checks the score's first 11 measures, checks controlled audio frequencies/onset energy, and recomputes the 48-note denominator. Browser verification covers first-load note pairs, paused measure selection, playback sync, 450 ms lead-ins, both findings, switching during recomputation, the inline end report and reopening, and desktop/390 px layouts.

Audit fixes: boundary omissions now count in complete measures; clean model-only output cannot become verified performer accuracy; loading a different sample clears old feedback and disables playback until the new report arrives; background recomputation messages name the sample that actually changed.

- `reports/assignment-audit.json`, `AUDIT.md`: assignment checks and limits.
- `reports/real.json`, `reports/controlled.json`: schema-2 UI reports.
- `reports/*-analysis.json`: alignment and scoring.
- `reports/*-notes.json`: both raw decoder outputs, settings, versions and hashes.
- `reports/decoder-comparison.json`: fresh baseline/candidate/probe results.
- `reports/controlled-verification.json`: independent fixture recovery checks.
- `reports/browser-verification.json`, `reports/screenshots/refined-*.png`: final browser evidence.

Current handoff is **website review only**. Recording, cursor changes, editing and export are deferred until the user explicitly requests them after reviewing the website. Recording artifacts from development are excluded from this repository. The source repository includes both input samples. No submission to VSA has been made.

Latest browser fix: dragging or keyboard-seeking the timeline while paused previously left the note comparison on the old measure. It now follows the seek; the final measure also remains labeled during the short trailing audio. The JavaScript asset version was bumped so a normal reload gets the fix.

```powershell
node tests/test_playback.cjs
```

Review click-through:

1. Launch `Demo.cmd`. The real clip opens with 16 score/detected pairs for measure 1 and the 176-pitch-match headline.
2. Play/pause, select measure 2, then scrub while paused. The comparison follows the selected position.
3. Click the measure-11 candidate: playback starts at 36.759899 s, 450 ms before 37.2099 s. Its status remains uncertain.
4. Choose **Тестовый пример**. Replay the measure-2 wrong note and measure-3 late onset using the two finding buttons.
5. Let playback end. The inline report shows 95.8%, two findings, measures 2/3 and practice advice. Collapse and reopen **Итог разбора**.
6. Click **Пересчитать**, wait for completion, then reopen the report. Repeat on the real clip. The details show a new calculation time and the same measured results.

Browser evidence is a record of observed UI checks, not an automated browser-test runner. The playback regression file tests the actual synchronizer with small media/DOM adapters; browser checks separately verify native range events and rendered notes.

## Attribution and limits

- Performance: user-provided local copy of [Alexander Motovilov's TikTok](https://www.tiktok.com/@alexander_motovilov/video/7456130710764752130). Included as the supplied trial input. The performance belongs to its creator; no ownership or reuse license is claimed.
- Composition: J. S. Bach, Prelude in C major, BWV 846. MIDI, PDF and LilyPond source: [Mutopia piece 5](https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=5), edition Mutopia-2011/09/12-5, public-domain score typesetting; maintainer Tobias Erbsland. Files are retained in `data/`.
- Transcription: [Spotify Basic Pitch](https://github.com/spotify/basic-pitch), Apache-2.0, ICASSP 2022 ONNX model bundled in version 0.4.0. Model SHA-256: `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`.
- The controlled timbre is generated in this project; no sampled soundfont is used. It validates two known cases, not general model accuracy.
- Real performer mistakes remain unverified. Reverberation, pedal, overtones, expressive timing and clipped boundaries can mislead transcription or the global clock. Repeated identical excerpts may remain ambiguous and be excluded. There is no live input, arbitrary upload, account system, cloud analysis, pedal/dynamics scoring or production hardening.
