"""Assemble the two Pilao videos: scene recordings + Nicolas's voice + burned-in French subtitles.

usage: python assemble.py <video-dir> <voice-dir> <out-dir>
A scene whose voice file (<voice-dir>/<scene>.*) is missing gets silence: that gives a preview.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VID, VOICE, OUT = (Path(a) for a in sys.argv[1:4])
OUT.mkdir(parents=True, exist_ok=True)
WORK = OUT / "work"
WORK.mkdir(exist_ok=True)
DUR = json.loads((HERE / "durations.json").read_text())
LEAD = 0.5  # the voice starts 0.5 s into its scene
CARD = 2.6  # chapter cards
NO_SUBS = {"v1-1", "v1-7", "v2-9"}  # the card already shows the same words

VIDEO1 = [f"v1-{i}" for i in range(1, 8)]
VIDEO2 = ["v2-0"] + [x for n in range(1, 9) for x in (f"c{n}", f"v2-{n}")] + ["v2-9"]


def texts() -> dict[str, list[str]]:
    """Sentences per scene, read from the validated voice-over text."""
    md = (HERE.parent / "textes" / "voix-off.md").read_text()
    out: dict[str, list[str]] = {}
    video = None
    key = None
    for line in md.splitlines():
        if line.startswith("## Vidéo 1"):
            video = "v1"
        elif line.startswith("## Vidéo 2"):
            video = "v2"
        m = re.match(r"\*\*(\d+)\. ", line)
        if m and video:
            key = f"{video}-{m.group(1)}"
            out[key] = []
        elif key and line.strip() and not line.startswith(("#", "---", "Une ligne")):
            out[key].append(line.strip())
        elif not line.strip():
            key = None if key and out.get(key) else key
    out["v2-9"] = [out["v2-8"].pop()]  # « Bonnes réponses avec Pilao ! » is the closing card
    return out


def chunks(line: str, limit: int = 96) -> list[str]:
    """One subtitle per sentence; a long sentence is cut at the punctuation nearest its middle."""
    return [c for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý])", line) for c in split_long(s, limit)]


# Nicolas pauses after « Astuce : », so cut this sentence where he does not.
SPLITS = {"Astuce : si vous avez": "documentaire, "}


def split_long(sentence: str, limit: int) -> list[str]:
    for start, after in SPLITS.items():
        if sentence.startswith(start) and after in sentence:
            cut = sentence.index(after) + len(after)
            return [sentence[:cut].strip(), sentence[cut:].strip()]
    if len(sentence) <= limit:
        return [sentence]
    cuts = [m.end() for m in re.finditer(r"[,:;.…]\s", sentence)]
    if not cuts:
        return [sentence]
    mid = len(sentence) / 2
    cut = min(cuts, key=lambda c: abs(c - mid))
    return split_long(sentence[:cut].strip(), limit) + split_long(sentence[cut:].strip(), limit)


def probe(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def silences(path: Path) -> list[tuple[float, float]]:
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "silencedetect=n=-38dB:d=0.16", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(starts, ends))


def timing(parts: list[str], voice: Path | None, dur: float) -> list[tuple[float, float]]:
    """Start/end (in the voice's time) of each subtitle: proportional to length, snapped to pauses."""
    total = sum(len(p) for p in parts)
    if voice:
        sil = silences(voice)
        speech_start = sil[0][1] if sil and sil[0][0] < 0.05 else 0.0
        speech_end = sil[-1][0] if sil and sil[-1][1] >= dur - 0.05 else dur
    else:
        sil, speech_start, speech_end = [], 0.0, dur
    span = speech_end - speech_start
    expected = [span * len(p) / total for p in parts]
    # Candidate cut points: every pause inside the speech, plus the proportional guesses (penalised).
    cands: list[tuple[float, float]] = [((a + b) / 2, 0.0) for a, b in sil if speech_start < a and b < speech_end]
    acc = 0.0
    for e in expected[:-1]:
        acc += e
        cands.append((speech_start + acc, 0.35))
    cands.sort()

    def cost(i: int, start: float, end: float) -> float:
        d = end - start
        r = d / expected[i]
        return (r - 1) ** 2 + (3.0 if r < 0.65 or r > 1.7 else 0.0) + (5.0 if d < 0.8 else 0.0)

    n = len(parts)
    inf = float("inf")
    # best[i][j]: cheapest way to end subtitle i at candidate j (subtitles 0..i placed).
    best = [[inf] * len(cands) for _ in range(n - 1)]
    back = [[-1] * len(cands) for _ in range(n - 1)]
    for j, (t, pen) in enumerate(cands):
        if n > 1:
            best[0][j] = cost(0, speech_start, t) + pen
    for i in range(1, n - 1):
        for j, (t, pen) in enumerate(cands):
            for k in range(j):
                if best[i - 1][k] < inf:
                    c = best[i - 1][k] + cost(i, cands[k][0], t) + pen
                    if c < best[i][j]:
                        best[i][j], back[i][j] = c, k
    cuts: list[float] = []
    if n > 1:
        last = min(range(len(cands)), key=lambda j: best[n - 2][j] + cost(n - 1, cands[j][0], speech_end))
        for i in range(n - 2, -1, -1):
            cuts.append(cands[last][0])
            last = back[i][last]
        cuts.reverse()
    bounds = [speech_start, *cuts, speech_end + 0.35]
    return [(bounds[i], bounds[i + 1]) for i in range(n)]


def ts(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Geist SemiBold,46,&H00FFFFFF,&H00FFFFFF,&H33441801,&H33441801,0,0,0,0,100,100,0,0,3,14,0,2,230,230,64,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def segment(name: str, sentences: dict[str, list[str]], first: bool, last: bool) -> Path:
    dst = WORK / f"{name}.mp4"
    is_card = name.startswith("c")
    dur = CARD if is_card else DUR[name]
    voices = sorted(VOICE.glob(f"{name}.*"))
    voice = voices[0] if voices else None
    vf = ["tpad=stop_mode=clone:stop_duration=30", f"trim=duration={dur}", "setpts=PTS-STARTPTS", "fps=30"]
    if not is_card and name not in NO_SUBS:
        parts = [c for s in sentences[name] for c in chunks(s)]
        vdur = probe(voice) if voice else dur - LEAD - 0.9
        ass = WORK / f"{name}.ass"
        lines = [
            f"Dialogue: 0,{ts(LEAD + a)},{ts(min(LEAD + b, dur - 0.05))},Sub,,0,0,0,,{p}"
            for p, (a, b) in zip(parts, timing(parts, voice, vdur))
        ]
        ass.write_text(ASS_HEAD + "\n".join(lines) + "\n")
        vf.append(f"ass={ass}:fontsdir={HERE / 'fonts'}")
    if first:
        vf.append("fade=in:st=0:d=0.4")
    if last:
        vf.append(f"fade=out:st={dur - 0.7}:d=0.7")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(VID / f"{name}.mp4")]
    if voice:
        cmd += ["-i", str(voice)]
        af = f"[1:a]aresample=48000,aformat=channel_layouts=stereo,adelay={int(LEAD * 1000)}:all=1,apad,atrim=duration={dur}[a]"
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        af = f"[1:a]atrim=duration={dur}[a]"
    cmd += [
        "-filter_complex", f"[0:v]{','.join(vf)},format=yuv420p[v];{af}",
        "-map", "[v]", "-map", "[a]", "-t", str(dur),
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "aac", "-b:a", "160k", str(dst),
    ]
    subprocess.run(cmd, check=True)
    return dst


def build(title: str, names: list[str], sentences: dict[str, list[str]]) -> None:
    segs = [segment(n, sentences, i == 0, i == len(names) - 1) for i, n in enumerate(names)]
    lst = WORK / f"{title}.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in segs))
    joined = WORK / f"{title}-joined.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], check=True)
    dst = OUT / f"{title}.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(joined), "-c:v", "copy",
         "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
         "-movflags", "+faststart", str(dst)],
        check=True,
    )
    print(f"{dst.name}: {probe(dst):.1f} s, {dst.stat().st_size / 1e6:.1f} Mo")


if __name__ == "__main__":
    s = texts()
    build(sys.argv[4] if len(sys.argv) > 4 else "Pilao-1-presentation", VIDEO1, s)
    build(sys.argv[5] if len(sys.argv) > 5 else "Pilao-2-tutoriel", VIDEO2, s)
