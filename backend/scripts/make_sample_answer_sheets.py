"""Render sample handwritten answer sheets (PNG) for the open worksheets, for live upload -> OCR -> evaluation demos.

    python -m backend.scripts.make_sample_answer_sheets          # writes demo/answer-sheets/*.png

Each sheet looks like a photographed notebook page: ruled lines, a margin, blue ink in a handwriting font,
the student's name/class/roll at the top and numbered answers (some right, some partly wrong), with slight
tilt and uneven baselines. Uses Windows "Ink Free" / "Segoe Print" / "Comic Sans" when available.
"""
from __future__ import annotations

import json
import random
import zlib
import sqlite3
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))

from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

OUT = APP_DIR / "demo" / "answer-sheets"
FONT_CANDIDATES = [
    "/mnt/c/Windows/Fonts/Inkfree.ttf", "/mnt/c/Windows/Fonts/segoepr.ttf", "/mnt/c/Windows/Fonts/comic.ttf",
    "C:/Windows/Fonts/Inkfree.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
# (student name, quality 0..1) - Gurleen is the featured student and has not uploaded yet in the seeded data.
STUDENTS = [("Gurleen Kaur", 0.55), ("Nandini Murthy", 0.75), ("Pranay Iyer", 0.9), ("Sneha Mehta", 0.35)]


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def plain(text: str) -> str:
    """Handwritten answers do not contain LaTeX delimiters."""
    return (text.replace(r"\(", "").replace(r"\)", "").replace(r"\frac{", "").replace("}{", "/").replace("}", "")
            .replace(r"\times", "x").replace(r"\,", " ").replace(r"\text{", "").replace("\\", ""))


def answer(q: dict, quality: float, rng: random.Random) -> str:
    key = plain(q.get("correct_answer") or "")
    if q.get("type") == "mcq":
        return key if rng.random() < quality else plain(rng.choice(q.get("options") or [key]))
    if rng.random() < quality:
        return key
    first = key.split(";")[0].split(":")[0]
    return first if rng.random() < 0.6 else "I am not sure. " + first[:40]


def wrap(text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = (line + " " + w).strip()
        if f.getlength(trial) > width and line:
            lines.append(line)
            line = w
        else:
            line = trial
    return lines + ([line] if line else [])


def render(student: str, cls: str, roll: int, title: str, questions: list[dict], quality: float, seed: int) -> Image.Image:
    rng = random.Random(seed)
    w, h, gap, margin = 1240, 1754, 54, 150
    page = Image.new("RGB", (w, h), (250, 249, 244))
    d = ImageDraw.Draw(page)
    for y in range(230, h - 60, gap):
        d.line((40, y, w - 40, y), fill=(178, 206, 232), width=2)
    d.line((margin - 20, 40, margin - 20, h - 40), fill=(226, 140, 140), width=3)
    ink = (28, 52, 140)
    big, normal = font(46), font(40)
    d.text((margin, 70), f"Name: {student}", font=big, fill=ink)
    d.text((margin, 135), f"Class: {cls}    Roll No: {roll}", font=normal, fill=ink)
    d.text((w - 430, 135), "Date: 18/11/2026", font=normal, fill=ink)
    y = 230 + gap - 46
    for line in wrap(plain(title.split(" - ")[0]), big, w - margin - 120):
        d.text((margin, y), line, font=big, fill=ink)
        y += gap
    y += gap
    for i, q in enumerate(questions, start=1):
        if rng.random() < 0.05:
            continue
        lines = wrap(f"Q{i}. {answer(q, quality, rng)}", normal, w - margin - 120)
        for line in lines:
            if y > h - 120:
                break
            d.text((margin + rng.randint(-6, 6), y + rng.randint(-5, 3)), line, font=normal, fill=ink)
            y += gap
        y += gap  # leave one ruled line between answers so writing always sits on a line
    page = page.rotate(rng.uniform(-1.4, 1.4), resample=Image.BICUBIC, expand=False, fillcolor=(236, 233, 225))
    return page.filter(ImageFilter.GaussianBlur(0.6))


def main() -> list[Path]:
    from backend.app.core.config import settings
    url = settings.DATABASE_URL.split(":///", 1)[1]
    db = Path(url) if url.startswith("/") else (APP_DIR / url).resolve()
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for name, quality in STUDENTS:
        s = con.execute("SELECT id, class_id, class_name, roll_no FROM students WHERE name = ? AND school_id = 'school-1'", (name,)).fetchone()
        if not s:
            continue
        sheets = con.execute("SELECT id, title, questions_json FROM assessments WHERE class_id = ? AND status = 'scheduled' "
                             "AND title LIKE 'Worksheet%' ORDER BY subject_id", (s["class_id"],)).fetchall()
        for a in sheets:
            img = render(name, s["class_name"].replace("Class ", ""), s["roll_no"], a["title"], json.loads(a["questions_json"]),
                         quality, seed=zlib.crc32(f"{name}|{a['id']}".encode()))
            subject = "science" if "-sci-" in a["id"] else "maths"
            path = OUT / f"{name.split()[0].lower()}_{s['class_name'].split()[-1].lower()}_{subject}_worksheet.png"
            img.save(path, optimize=True)
            written.append(path)
    (OUT / "README.txt").write_text(
        "Sample photographed answer sheets for the open worksheets (Sunrise Public School).\n"
        "Sign in as the student (see docs/LOGIN_CREDENTIALS.md), open Upload Beta, choose the worksheet and upload the\n"
        "matching PNG. Then sign in as the teacher, open the worksheet in Upload Beta and evaluate the submission.\n",
        encoding="utf-8")
    return written


if __name__ == "__main__":
    for p in main():
        print(p.relative_to(APP_DIR))
