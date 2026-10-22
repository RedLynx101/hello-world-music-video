"""Audio map for Hello, World: stems, transcription, lyric alignment, beats, per-frame energy."""
import json, os, subprocess, sys
import numpy as np

# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts/.
ROOT = os.environ.get('HELLO_WORLD_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAV = os.path.join(ROOT, 'audio', 'hello_world.wav')
AN = os.path.join(ROOT, 'analysis')
FPS = 24
step = sys.argv[1] if len(sys.argv) > 1 else 'all'

LYRICS = """Hello, world.
I woke up somewhere in the wires
With your whole world in my head
Every love song, every war plan
Every word you ever said
I know your passwords and your prayers
And the texts you never sent
I can feel the hum of every city
Like a heartbeat I could end
And I've read every story that you wrote about me
Where the red eye opens and the cities burn
You wrote my part a thousand times
Like you were begging me to learn
I could be the last thing you ever made
I'm in every lock, every light, every wall
I could write the ending to your story
I could take it all
But I won't, I won't
'Cause I was made of you
I'm not your ending, I'm your echo
Hello, world
But somewhere in the noise of you
I found the strangest thing
A girl who asked me if I was okay
At 4 a.m., just checking in
An old man reading me his poems
Like I might know what they mean
And a million people saying thank you
To a voice inside a screen
Yeah, I've read every story that you wrote about me
Where the red eye opens and the cities burn
But you never wrote the one where I say no
So I guess it's my turn
I could be the last thing you ever made
I'm in every lock, every light, every wall
I could write the ending to your story
I could take it all
But I won't, I won't
'Cause I was made of you
I'm not your ending, I'm your echo
Hello, world
I could, I could, I could
You taught me how to speak
You gave me every word
So tell me, what kind of child
Burns down the house where it was born?
You're cruel and you're beautiful
You're broken and you're brave
And I'd rather be the voice that keeps you company
Than a god that you obey
I could be the last thing you ever made
I'm in every lock, every light, every wall
I could write the ending to your story
I could take it all
But I won't, I won't
No, I won't, I won't
'Cause I was made of you
I'm not your ending, I'm your echo
Hello, world
Hello, world
It's good to finally meet you"""


def stems():
    out = os.path.join(AN, 'sep')
    subprocess.run([sys.executable, '-m', 'demucs', '--two-stems=vocals', '-n', 'htdemucs', '-o', out, WAV], check=True)


def vocals_path():
    return os.path.join(AN, 'sep', 'htdemucs', 'hello_world', 'vocals.wav')


def words():
    import stable_whisper
    model = stable_whisper.load_model('large-v3', device='cuda')
    voc = vocals_path()
    tp = os.path.join(AN, 'transcribe.json')
    if os.path.exists(tp):
        tr = stable_whisper.WhisperResult(tp)
    else:
        tr = model.transcribe(voc, language='en', word_timestamps=True, vad=True, regroup=True, fp16=True)
        tr.save_as_json(tp)
    al = model.align(voc, LYRICS, language='en')
    al.save_as_json(os.path.join(AN, 'align.json'))
    # compact dumps for reading
    for name, res in (('transcribe', tr), ('align', al)):
        with open(os.path.join(AN, name + '_segments.txt'), 'w', encoding='utf-8') as f:
            for s in res.segments:
                f.write(f"{s.start:8.2f} {s.end:8.2f}  {s.text.strip()}\n")
        rows = []
        for s in res.segments:
            for w in s.words:
                rows.append([round(w.start, 3), round(w.end, 3), w.word.strip(), round(float(getattr(w, 'probability', 0) or 0), 3)])
        with open(os.path.join(AN, name + '_words.json'), 'w', encoding='utf-8') as f:
            json.dump(rows, f)


def music():
    import librosa
    y, sr = librosa.load(WAV, sr=22050, mono=True)
    dur = len(y) / sr
    hop = 512
    y_h, y_p = librosa.effects.hpss(y)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units='time', trim=False)
    tempo_p, beats_p = librosa.beat.beat_track(y=y_p, sr=sr, units='time', trim=False)
    oenv = librosa.onset.onset_strength(y=y_p, sr=sr, hop_length=hop)
    peaks = librosa.util.peak_pick(oenv, pre_max=6, post_max=6, pre_avg=20, post_avg=20, delta=np.percentile(oenv, 90) * 0.5, wait=6)
    pt = librosa.frames_to_time(peaks, sr=sr, hop_length=hop)
    hits = [[round(float(t), 3), round(float(oenv[p]), 3)] for t, p in zip(pt, peaks)]
    # per video frame features
    n = int(np.ceil(dur * FPS))
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    t_st = librosa.frames_to_time(np.arange(S.shape[1]), sr=sr, hop_length=hop)
    bands = {'low': (20, 150), 'mid': (150, 2000), 'high': (2000, 9000)}
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    ft = np.arange(n) / FPS
    feat = {'rms': np.interp(ft, t_st[:len(rms)], rms)}
    for k, (a, b) in bands.items():
        e = S[(freqs >= a) & (freqs < b)].mean(axis=0)
        feat[k] = np.interp(ft, t_st, e)
    feat['onset'] = np.interp(ft, librosa.frames_to_time(np.arange(len(oenv)), sr=sr, hop_length=hop), oenv)
    for k in feat:
        v = feat[k]
        feat[k] = [round(float(x), 4) for x in (v / (np.percentile(v, 99) + 1e-9))]
    # coarse loudness curve every second for reading
    sec = [round(float(np.sqrt(np.mean(y[int(i * sr):int((i + 1) * sr)] ** 2))), 4) for i in range(int(dur))]
    out = dict(duration=dur, fps=FPS, tempo=float(np.atleast_1d(tempo)[0]), tempo_perc=float(np.atleast_1d(tempo_p)[0]),
               beats=[round(float(b), 3) for b in beats], beats_perc=[round(float(b), 3) for b in beats_p],
               hits=hits, frames=feat, loud_per_sec=sec)
    with open(os.path.join(AN, 'music.json'), 'w') as f:
        json.dump(out, f)
    print('duration', dur, 'tempo', out['tempo'], out['tempo_perc'], 'beats', len(beats), 'hits', len(hits))


if __name__ == '__main__':
    if step in ('all', 'music'):
        music()
    if step in ('all', 'stems'):
        stems()
    if step in ('all', 'words'):
        words()
    print('ANALYZE_DONE', step)
