#!/usr/bin/env python3
"""Watson Dashboard - HTTP server that reads watson time tracking data."""

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DEFAULT_TARGET = 40.0


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"target_hours_per_week": DEFAULT_TARGET}


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def get_target() -> float:
    return float(load_config().get("target_hours_per_week", DEFAULT_TARGET))


TARGET_HOURS_PER_WEEK = get_target()


def get_week_bounds(offset: int = 0):
    """Return (monday, sunday) for the week at `offset` weeks from current."""
    today = date.today()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def fetch_sessions(from_date: date, to_date: date) -> list[dict]:
    """Run watson log --json for the given date range."""
    result = subprocess.run(
        [
            "watson",
            "log",
            "--json",
            "--from",
            from_date.strftime("%Y-%m-%d"),
            "--to",
            to_date.strftime("%Y-%m-%d"),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def seconds_for_sessions(sessions: list[dict]) -> float:
    total = 0.0
    for s in sessions:
        start = datetime.fromisoformat(s["start"])
        stop = datetime.fromisoformat(s["stop"])
        total += (stop - start).total_seconds()
    return total


def daily_target() -> float:
    return get_target() / 5


def build_daily_breakdown(monday: date, today: date) -> list[dict]:
    """Return per-day data for Mon-Fri of the current week, skipping 0h past days."""
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    dt = daily_target()
    days = []
    for i in range(5):
        day = monday + timedelta(days=i)
        if day > today:
            days.append({
                "date": day.isoformat(),
                "name": day_names[i],
                "hours": None,
                "target": round(dt, 2),
                "is_today": False,
                "is_future": True,
                "is_off": False,
            })
        else:
            sessions = fetch_sessions(day, day)
            hours = seconds_for_sessions(sessions) / 3600
            is_off = hours == 0 and not (day == today)
            days.append({
                "date": day.isoformat(),
                "name": day_names[i],
                "hours": round(hours, 2),
                "target": round(dt, 2),
                "is_today": day == today,
                "is_future": False,
                "is_off": is_off,
            })
    return days


def effective_weekly_target(monday: date, end: date, sessions: list[dict]) -> float:
    """Target adjusted for days with no tracked time (holidays/vacation)."""
    worked_days = set()
    for s in sessions:
        day = datetime.fromisoformat(s["start"]).date()
        worked_days.add(day)
    count = sum(
        1 for d in worked_days
        if d >= monday and d <= end and d.weekday() < 5
    )
    return count * daily_target()


def build_weekly_data(num_weeks: int = 12) -> list[dict]:
    """Return per-week summary for the last `num_weeks` weeks."""
    weeks = []
    today = date.today()
    for offset in range(-(num_weeks - 1), 1):
        monday, sunday = get_week_bounds(offset)
        end = min(sunday, today)
        sessions = fetch_sessions(monday, end)
        hours = seconds_for_sessions(sessions) / 3600
        is_current = offset == 0
        target = effective_weekly_target(monday, end, sessions)
        delta = round(hours - target, 2) if target > 0 else 0.0
        entry: dict = {
            "week_start": monday.isoformat(),
            "week_end": sunday.isoformat(),
            "hours": round(hours, 2),
            "target": round(target, 2),
            "delta": delta,
            "is_current": is_current,
            "days_elapsed": today.weekday() + 1 if is_current else 5,
        }
        if is_current:
            entry["days"] = build_daily_breakdown(monday, today)
        weeks.append(entry)
    return weeks


def build_summary(weeks: list[dict]) -> dict:
    completed = [w for w in weeks if not w["is_current"]]
    tracked = [w for w in completed if w["hours"] > 0]
    total_overtime = sum(w["delta"] for w in tracked if w["delta"] > 0)
    total_undertime = sum(w["delta"] for w in tracked if w["delta"] < 0)
    net_balance = sum(w["delta"] for w in tracked)
    current = next((w for w in weeks if w["is_current"]), None)
    return {
        "total_overtime_hours": round(total_overtime, 2),
        "total_undertime_hours": round(total_undertime, 2),
        "net_balance_hours": round(net_balance, 2),
        "current_week": current,
        "weeks_analyzed": len(tracked),
    }


def build_active_session() -> dict:
    """Return the currently running watson session, or active=False."""
    result = subprocess.run(["watson", "status"], capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return {"active": False}
    m = re.match(r"Project (.+?) started .+ \((.+?)\)", result.stdout.strip())
    if not m:
        return {"active": False}
    project_part = m.group(1)
    # project may include tags in brackets e.g. "myproject [tag1, tag2]"
    pm = re.match(r"(.+?)\s*\[(.+)\]$", project_part)
    if pm:
        project = pm.group(1).strip()
        tags = [t.strip() for t in pm.group(2).split(",")]
    else:
        project = project_part.strip()
        tags = []
    start_dt = datetime.strptime(m.group(2), "%Y.%m.%d %H:%M:%S%z")
    elapsed = (datetime.now(start_dt.tzinfo) - start_dt).total_seconds()
    return {
        "active": True,
        "project": project,
        "tags": tags,
        "start": start_dt.isoformat(),
        "start_time": start_dt.strftime("%H:%M"),
        "elapsed_seconds": round(elapsed),
    }


def build_today(for_date: date | None = None) -> dict:
    """Return hours, sessions, and target for a given date (defaults to today)."""
    today = date.today()
    target_date = for_date if for_date is not None else today
    is_today = target_date == today
    sessions = fetch_sessions(target_date, target_date)
    hours = seconds_for_sessions(sessions) / 3600
    entries = []
    for s in sessions:
        start_dt = datetime.fromisoformat(s["start"])
        stop_dt = datetime.fromisoformat(s["stop"])
        duration = (stop_dt - start_dt).total_seconds() / 3600
        entries.append({
            "project": s.get("project", "unknown"),
            "tags": s.get("tags", []),
            "start": s["start"],
            "stop": s["stop"],
            "start_time": start_dt.strftime("%H:%M"),
            "stop_time": stop_dt.strftime("%H:%M"),
            "duration_hours": round(duration, 4),
        })
    return {
        "date": target_date.isoformat(),
        "is_today": is_today,
        "hours": round(hours, 4),
        "target": daily_target(),
        "target_reached": hours >= daily_target(),
        "sessions": entries,
    }


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # suppress default logging
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, content: str):
        body = content.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/data":
            weeks = build_weekly_data(24)
            summary = build_summary(weeks)
            self.send_json({"weeks": weeks, "summary": summary})
        elif path == "/api/today":
            parsed_qs = parse_qs(parsed.query)
            for_date = None
            if "date" in parsed_qs:
                try:
                    for_date = date.fromisoformat(parsed_qs["date"][0])
                except ValueError:
                    pass
            self.send_json(build_today(for_date))
        elif path == "/api/status":
            self.send_json(build_active_session())
        elif path == "/api/config":
            cfg = load_config()
            self.send_json({"target_hours_per_week": cfg.get("target_hours_per_week", DEFAULT_TARGET)})
        elif path == "/" or path == "/index.html":
            with open("index.html", "r") as f:
                self.send_html(f.read())
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                target = float(data["target_hours_per_week"])
                if target <= 0 or target > 168:
                    raise ValueError
                cfg = load_config()
                cfg["target_hours_per_week"] = target
                save_config(cfg)
                self.send_json({"ok": True, "target_hours_per_week": target})
            except (KeyError, ValueError, json.JSONDecodeError):
                self.send_json({"ok": False, "error": "invalid value"}, status=400)
        else:
            self.send_response(404)
            self.end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    print(f"Watson Dashboard → http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
