"""Write docs/LOGIN_CREDENTIALS.md from the demonstration database (every account and how it signs in)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))

from backend.app.seed.seed_data import PASSWORDS, ROOT_PERSONA_EMAILS  # noqa: E402


def _db_path() -> Path:
    from backend.app.core.config import settings
    url = settings.DATABASE_URL.split(":///", 1)[1]
    return Path(url) if url.startswith("/") else (APP_DIR / url).resolve()


def _dob_password(dob: str) -> str:
    y, m, d = dob.split("-")
    return f"{d}{m}{y}"


def write_credentials(out: Path | None = None) -> Path:
    out = out or APP_DIR / "docs" / "LOGIN_CREDENTIALS.md"
    con = sqlite3.connect(f"file:{_db_path()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    schools = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM schools ORDER BY id")}
    users = list(con.execute("SELECT * FROM users ORDER BY role, name"))
    by_email = {u["email"]: u for u in users}
    lines = [
        "# LumenEIOS demonstration logins",
        "",
        "Sign in with the **email** or the **username** shown. Passwords:",
        "",
        f"| Role | Password |",
        f"|---|---|",
        f"| Management (admin) | `{PASSWORDS['admin']}` |",
        f"| Principal | `{PASSWORDS['principal']}` |",
        f"| Teacher | `{PASSWORDS['teacher']}` |",
        f"| Student | date of birth as `DDMMYYYY` (listed below) |",
        f"| Parent | `{PASSWORDS['parent']}` |",
        "",
        "**Developer mode:** on the sign-in page open *Developer mode* to sign in as any account without a password",
        "(only when `APP_ENV=development`). The team root login `LEOFELIX` / `KVR` also still works and can switch roles.",
        "",
        "## Featured accounts (one-click buttons on the sign-in page)",
        "",
        "| Role | Name | Email | Username | Password |",
        "|---|---|---|---|---|",
    ]
    for role, email in ROOT_PERSONA_EMAILS.items():
        u = by_email.get(email)
        if not u:
            continue
        pw = PASSWORDS.get(role)
        if role == "student":
            dob = con.execute("SELECT date_of_birth FROM students WHERE id = ?", (u["id"],)).fetchone()[0]
            pw = _dob_password(dob)
        lines.append(f"| {role} | {u['name']} | `{email}` | `{u['username']}` | `{pw}` |")

    lines += ["", "## Staff", "", "| School | Role | Name | Email | Username | Designation |", "|---|---|---|---|---|---|"]
    for u in users:
        if u["role"] in ("admin", "principal", "teacher"):
            school = "All schools" if u["role"] == "admin" else schools.get(u["school_id"], "")
            lines.append(f"| {school} | {u['role']} | {u['name']} | `{u['email']}` | `{u['username']}` | {u['designation'] or ''} |")

    for school_id, school_name in schools.items():
        lines += ["", f"## {school_name} - students and parents"]
        classes = list(con.execute("SELECT id, name, class_teacher_name FROM classes WHERE school_id = ? ORDER BY grade, section", (school_id,)))
        for c in classes:
            lines += ["", f"### {c['name']} (class teacher: {c['class_teacher_name'] or '-'})", "",
                      "| Roll | Student | Admission no. (username) | Student password | Parent | Parent username (mobile) |",
                      "|---|---|---|---|---|---|"]
            rows = con.execute(
                "SELECT s.roll_no, s.name, s.admission_no, s.date_of_birth, p.name AS parent, p.username AS mobile "
                "FROM students s JOIN users p ON p.id = s.parent_id WHERE s.class_id = ? ORDER BY s.roll_no", (c["id"],))
            for r in rows:
                lines.append(f"| {r['roll_no']} | {r['name']} | `{r['admission_no']}` | `{_dob_password(r['date_of_birth'])}` | "
                             f"{r['parent']} | `{r['mobile']}` |")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    print(write_credentials())
