"""Fresh, independent assignment checks; fixture answers are blocked during inference."""
from pathlib import Path
import json, sys
from unittest.mock import patch
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from piano_review.pipeline import run_analysis, write_json
from piano_review.reference import parse_midi
from piano_review.transcription import sha256
from piano_review.controlled import verify_controlled_report

cached = {s: json.loads((ROOT / f'reports/{s}.json').read_text(encoding='utf-8')) for s in ['real','controlled']}
original_open = Path.open
blocked = []
def guarded_open(path, *args, **kwargs):
    if 'truth' in path.name:
        blocked.append(str(path)); raise AssertionError('Inference attempted to read fixture answers')
    return original_open(path, *args, **kwargs)
with patch.object(Path, 'open', guarded_open):
    reports = {s: run_analysis(s) for s in ['real','controlled']}
fields = ['summary','findings','comparisons','scoring','decoder','measures']
checks = {'fresh_equals_packaged': {s: all(cached[s][k] == reports[s][k] for k in fields) for s in reports},
          'fixture_answer_reads_during_inference': blocked,
          'original_source_unchanged': sha256(ROOT/'data/real.mp4') == '6dbd34cc080b83d76f6e9eb2ba3a73d070fd0d0091f53010386f145652a63054'}
reference = parse_midi(ROOT/'data/reference.mid')
# Independently transcribed from the retained LilyPond score's two hands, bars 1–11.
patterns = [[60,64,67,72,76,67,72,76],[60,62,69,74,77,69,74,77],
[59,62,67,74,77,67,74,77],[60,64,67,72,76,67,72,76],
[60,64,69,76,81,69,76,81],[60,62,66,69,74,66,69,74],
[59,62,67,74,79,67,74,79],[59,60,64,67,72,64,67,72],
[57,60,64,67,72,64,67,72],[50,57,62,66,72,62,66,72],
[55,59,62,67,71,62,67,71]]
checks['score_bars_1_to_11'] = all([n['pitch'] for n in reference['notes'] if n['measure']==i] == p*2 for i,p in enumerate(patterns,1))
controlled = reports['controlled']
checks['controlled_denominator'] = sum(n['measure'] in [1,2,3] for n in reference['notes'])
checks['controlled_independent_accuracy'] = round(100*(1-2/checks['controlled_denominator']),1)
checks['controlled_result'] = {k:controlled['summary'][k] for k in ['accuracy','error_count','problem_measures','advice']}
truth = json.loads((ROOT/'data/controlled-truth.json').read_text(encoding='utf-8'))
checks['controlled_fixture_recovery'] = verify_controlled_report(controlled, truth)
checks['controlled_counts_and_advice'] = (
    controlled['summary']['error_count'] == 2
    and controlled['summary']['uncertain_count'] == 0
    and controlled['summary']['problem_measures'] == [2, 3]
    and controlled['summary']['breakdown'] == {'pitch': 1, 'timing': 1, 'missing': 0, 'extra': 0}
    and len(controlled['findings']) == len({f['id'] for f in controlled['findings']}) == 2
    and len(controlled['summary']['advice']) == 3
    and all(f['status'] == 'confirmed' for f in controlled['findings']))
y,sr=sf.read(ROOT/'data/controlled.wav')
peaks=[]
for t in [6.62,11.62]:
    clip=y[int(t*sr):int((t+.08)*sr)]; size=65536
    spectrum=np.abs(np.fft.rfft(clip*np.hanning(len(clip)),n=size))
    hz=np.fft.rfftfreq(size,1/sr)
    region=(hz>650)&(hz<800); freq=float(hz[region][np.argmax(spectrum[region])])
    peaks.append({'time':t,'dominant_treble_hz':round(freq,2),'nearest_midi':round(69+12*np.log2(freq/440))})
filtered=sosfiltfilt(butter(4,[675,720],btype='bandpass',fs=sr,output='sos'),y)
envelope=np.sqrt(np.convolve(filtered**2,np.ones(111)/111,mode='same'))
lo,hi=int(11.5*sr),int(11.7*sr)
onset=(lo+np.flatnonzero(envelope[lo:hi]>.2*envelope[lo:hi].max())[0])/sr
checks['independent_audio']={'spectral_peaks':peaks,'late_f5_band_energy_onset':round(onset,4),
'fixture_expected_onset':11.4,'fixture_deliberate_onset':11.6,'note':'Band energy onset is an approximate independent check, not model transcription.'}
real=reports['real']; analysis=json.loads((ROOT/'reports/real-analysis.json').read_text(encoding='utf-8'))
checks['real']={'matches':real['summary']['pitch_match_count'],'accuracy':real['summary']['accuracy'],
'model_agreement':real['summary']['model_agreement'],'scored_measures':real['scoring']['scored_measures'],
'affine_slope':analysis['alignment']['slope'],'affine_intercept':analysis['alignment']['intercept'],
'median_onset_residual_ms':analysis['alignment']['median_onset_residual_ms'],
'location_margin':analysis['alignment']['location_margin'],
'measure_11_candidate':[f for f in real['findings'] if f['type']=='timing'],
'boundary':real['comparisons'][-1]['end']}
checks['passed'] = all(checks['fresh_equals_packaged'].values()) and not blocked and checks['original_source_unchanged'] and checks['score_bars_1_to_11'] and checks['controlled_denominator']==48 and controlled['summary']['accuracy']==95.8 and [p['nearest_midi'] for p in peaks]==[78,77] and abs(onset-11.6)<.025
checks['passed'] = bool(checks['passed'])
checks['passed'] = checks['passed'] and checks['controlled_fixture_recovery']['passed'] and checks['controlled_counts_and_advice']
write_json(ROOT/'reports/assignment-audit.json',checks)
print(json.dumps(checks,ensure_ascii=True,indent=2))
raise SystemExit(0 if checks['passed'] else 1)

