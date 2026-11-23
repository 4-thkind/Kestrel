"""Shared helpers for the two Kestrel videos: voice (edge-tts), music (synthesised), audio mix and frame muxing.

Used by `demo video/record_demo.py` and `project explanation/render_explainer.py`.
Needs: pip install edge-tts imageio-ffmpeg numpy  (ffmpeg comes with imageio-ffmpeg).
"""
from __future__ import annotations

import asyncio
import subprocess
import wave
from pathlib import Path

import edge_tts
import imageio_ffmpeg
import numpy as np

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
RATE = 48000


def ff(*args: str) -> None:
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args], check=True)


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


async def _speak(text: str, voice: str, rate: str, mp3: Path) -> list[tuple[float, float, str]]:
    sentences = []
    com = edge_tts.Communicate(text, voice, rate=rate, boundary="SentenceBoundary")
    with open(mp3, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                sentences.append((chunk["offset"] / 1e7, (chunk["offset"] + chunk["duration"]) / 1e7, chunk["text"]))
    return sentences


def speak(parts: list[tuple[str, str]], out: Path, rate: str = "+0%", gap: float = 0.35) -> dict:
    """parts = [(voice, text)]. Writes one 48 kHz mono WAV; returns duration, subtitle cues and part start times.
    Cached: an unchanged script is not re-synthesised."""
    meta_path = out.with_suffix(".json")
    key = repr((parts, rate, gap))
    if out.exists() and meta_path.exists():
        import json
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("key") == key:
            return meta
    cues, starts, wavs, t = [], [], [], 0.0
    for i, (voice, text) in enumerate(parts):
        mp3 = out.with_name(f"{out.stem}.p{i}.mp3")
        wav = mp3.with_suffix(".wav")
        for attempt in range(4):   # the free TTS endpoint occasionally returns nothing; retry
            try:
                sents = asyncio.run(_speak(text, voice, rate, mp3))
                break
            except edge_tts.exceptions.NoAudioReceived:
                if attempt == 3:
                    raise
                import time
                time.sleep(2 + attempt * 3)
        ff("-i", str(mp3), "-af", "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
           "-ar", str(RATE), "-ac", "1", str(wav))
        starts.append(t)
        cues += [(t + a, t + b, s) for a, b, s in sents]
        wavs.append(wav)
        t += wav_seconds(wav) + gap
    # concatenate with gaps
    inputs, filt = [], []
    for i, w in enumerate(wavs):
        inputs += ["-i", str(w)]
        filt.append(f"[{i}]apad=pad_dur={gap}[a{i}]")
    filt.append("".join(f"[a{i}]" for i in range(len(wavs))) + f"concat=n={len(wavs)}:v=0:a=1[o]")
    ff(*inputs, "-filter_complex", ";".join(filt), "-map", "[o]", "-ar", str(RATE), "-ac", "1", str(out))
    meta = {"key": key, "duration": wav_seconds(out), "cues": cues, "starts": starts}
    import json
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def make_music(seconds: float, out: Path, bpm: float = 96, seed: int = 7) -> None:
    """A soft, original ambient bed: warm pad chords, a plucked arpeggio and a sub bass. Synthesised, so no licence issue."""
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE) + RATE
    t = np.arange(n) / RATE
    mix = np.zeros(n)
    beat = 60 / bpm
    bar = beat * 4
    # Cmaj9 - Am9 - Fmaj7#11 - Gsus/D  (MIDI notes)
    chords = [[48, 55, 59, 62, 64], [45, 52, 55, 59, 60], [41, 48, 52, 57, 59], [43, 50, 55, 57, 62]]
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    i = 0
    while i * bar * 2 < seconds + bar * 2:
        notes = chords[i % 4]
        a, b = int(i * bar * 2 * RATE), min(n, int((i + 1) * bar * 2 * RATE + RATE))
        if a >= n:
            break
        seg = t[a:b] - t[a]
        env = np.minimum(1, seg / 1.6) * np.exp(-np.maximum(0, seg - bar * 2) * 3)
        for m in notes:
            f = hz(m + 12)
            for det in (-0.12, 0.12):
                mix[a:b] += 0.05 * env * np.sin(2 * np.pi * f * (1 + det / 100) * seg + rng.random() * 6.28) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.2 * seg))
        mix[a:b] += 0.11 * env * np.sin(2 * np.pi * hz(notes[0] - 12) * seg)          # sub bass
        # plucked arpeggio, eighth notes
        arp = [notes[1] + 24, notes[2] + 24, notes[3] + 24, notes[4] + 24, notes[3] + 24, notes[2] + 24, notes[4] + 24, notes[1] + 36]
        for k in range(16):
            s = a + int(k * beat / 2 * RATE)
            e = min(n, s + int(1.2 * RATE))
            if s >= n:
                break
            st = t[s:e] - t[s]
            f = hz(arp[k % 8])
            mix[s:e] += 0.045 * np.exp(-st * 5.5) * (np.sin(2 * np.pi * f * st) + 0.3 * np.sin(4 * np.pi * f * st))
        i += 1
    mix = mix[: int(seconds * RATE)]
    fade = int(2.5 * RATE)
    mix[:fade] *= np.linspace(0, 1, fade)
    mix[-fade:] *= np.linspace(1, 0, fade)
    mix = (mix / (np.abs(mix).max() + 1e-9) * 0.7 * 32767).astype(np.int16)
    raw = out.with_suffix(".raw.wav")
    with wave.open(str(raw), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(mix.tobytes())
    ff("-i", str(raw), "-af", "lowpass=f=5200,aecho=0.8:0.7:180|320:0.25|0.15", "-ar", str(RATE), str(out))
    raw.unlink()


def mix_audio(events: list[tuple[float, Path]], seconds: float, music: Path, out: Path, music_db: float = -21) -> None:
    """Narration clips at absolute times over a music bed that ducks under the voice."""
    inputs, filt = [], []
    for i, (at, wav) in enumerate(events):
        inputs += ["-i", str(wav)]
        ms = max(0, int(at * 1000))
        filt.append(f"[{i}]adelay={ms}|{ms},apad=whole_dur={seconds}[v{i}]")
    k = len(events)
    filt.append("".join(f"[v{i}]" for i in range(k)) + f"amix=inputs={k}:normalize=0,atrim=0:{seconds},asplit=2[voice][key]")
    filt.append(f"[{k}]volume={music_db}dB,atrim=0:{seconds}[bed]")
    filt.append("[bed][key]sidechaincompress=threshold=0.03:ratio=6:attack=40:release=600[ducked]")
    filt.append("[voice][ducked]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[o]")
    ff(*inputs, "-i", str(music), "-filter_complex", ";".join(filt), "-map", "[o]", "-ar", str(RATE), "-ac", "2", str(out))


def mux(video: Path, audio: Path, out: Path) -> None:
    ff("-i", str(video), "-i", str(audio), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out))
