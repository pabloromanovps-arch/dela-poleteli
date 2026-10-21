#!/usr/bin/env python3
"""Бит-сетка трека: темп, биты, такты, онсеты, огибающая громкости, секции.

  python tools/audio/beats.py track.wav --fps 50 --out projects/<id>/04_board/beatgrid.json
  python tools/audio/beats.py --bpm 120 --duration 60 --fps 50 --out grid.json   # временная сетка без трека
"""
import argparse
import json

import numpy as np


def frames(times, fps):
    return [int(round(t * fps)) for t in times]


def synthetic(bpm, duration, beats_per_bar):
    step = 60.0 / bpm
    beats = list(np.arange(0, duration, step))
    env_t = list(np.arange(0, duration, 0.1))
    return {"tempo": bpm, "beats": beats, "downbeats": beats[::beats_per_bar], "onsets": [],
            "envelope": {"times": env_t, "values": [0.5] * len(env_t)}, "sections": [0.0]}


def analyze(path, bpm_hint, beats_per_bar, n_sections):
    import librosa
    y, sr = librosa.load(path, sr=22050, mono=True)
    duration = len(y) / sr
    kwargs = {"start_bpm": bpm_hint} if bpm_hint else {}
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames", **kwargs)
    beats = librosa.frames_to_time(beat_frames, sr=sr)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)

    # Сильная доля: фаза с максимальной суммарной силой онсетов на позиции 1 в такте.
    strengths = onset_env[np.minimum(beat_frames, len(onset_env) - 1)] if len(beat_frames) else np.array([])
    phase = int(np.argmax([strengths[p::beats_per_bar].sum() for p in range(beats_per_bar)])) if len(strengths) else 0
    downbeats = beats[phase::beats_per_bar]

    onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=False)

    hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms = rms / (rms.max() or 1)
    env_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    keep = np.arange(0, len(rms), max(1, int(sr / hop / 10)))  # ~10 значений в секунду

    # Секции: кластеризация хромы+MFCC, границы привязываются к ближайшему такту.
    feat = np.vstack([librosa.feature.chroma_cqt(y=y, sr=sr), librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)])
    bounds = librosa.segment.agglomerative(feat, min(n_sections, feat.shape[1]))
    sec_times = librosa.frames_to_time(bounds, sr=sr)
    if len(downbeats):
        sec_times = sorted({float(downbeats[np.argmin(np.abs(downbeats - t))]) for t in sec_times})

    return {"tempo": float(np.atleast_1d(tempo)[0]), "duration": duration,
            "beats": beats.tolist(), "downbeats": downbeats.tolist(), "onsets": onsets.tolist(),
            "envelope": {"times": env_times[keep].tolist(), "values": rms[keep].round(4).tolist()},
            "sections": [float(t) for t in sec_times]}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("track", nargs="?")
    p.add_argument("--fps", type=float, required=True, help="fps из профиля экрана")
    p.add_argument("--out", required=True)
    p.add_argument("--bpm", type=float, help="подсказка темпа (или темп временной сетки)")
    p.add_argument("--duration", type=float, default=60, help="длина временной сетки, c")
    p.add_argument("--bar", type=int, default=4, help="долей в такте")
    p.add_argument("--sections", type=int, default=6)
    a = p.parse_args()

    if a.track:
        grid = analyze(a.track, a.bpm, a.bar, a.sections)
    elif a.bpm:
        grid = synthetic(a.bpm, a.duration, a.bar)
    else:
        p.error("нужен трек или --bpm")

    grid["fps"] = a.fps
    for key in ("beats", "downbeats", "onsets", "sections"):
        grid[key + "_frames"] = frames(grid[key], a.fps)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(grid, f, ensure_ascii=False, indent=1)
    print(f"Темп {grid['tempo']:.1f} BPM · битов {len(grid['beats'])} · тактов {len(grid['downbeats'])} · "
          f"секций {len(grid['sections'])} → {a.out}")


if __name__ == "__main__":
    main()
