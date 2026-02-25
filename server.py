#!/usr/bin/env python3
"""Watson Dashboard - HTTP server that reads watson time tracking data."""

import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

TARGET_HOURS_PER_WEEK = 40.0


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


def build_daily_breakdown(monday: date, today: date) -> list[dict]:
    """Return per-day hours for Mon–Fri of the current week."""
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    daily_target = TARGET_HOURS_PER_WEEK / 5
    days = []
    for i in range(5):
        day = monday + timedelta(days=i)
        if day > today:
            days.append({
                "date": day.isoformat(),
                "name": day_names[i],
                "hours": None,
                "target": round(daily_target, 2),
                "is_today": False,
                "is_future": True,
            })
        else:
            sessions = fetch_sessions(day, day)
            hours = seconds_for_sessions(sessions) / 3600
            days.append({
                "date": day.isoformat(),
                "name": day_names[i],
                "hours": round(hours, 2),
                "target": round(daily_target, 2),
                "is_today": day == today,
                "is_future": False,
            })
    return days


def build_weekly_data(num_weeks: int = 12) -> list[dict]:
    """Return per-week summary for the last `num_weeks` weeks."""
    weeks = []
    today = date.today()
    for offset in range(-(num_weeks - 1), 1):
        monday, sunday = get_week_bounds(offset)
        end = min(sunday, today)
        sessions = fetch_sessions(monday, end)
        seconds = seconds_for_sessions(sessions)
        hours = seconds / 3600
        is_current = offset == 0
        weekly_target = TARGET_HOURS_PER_WEEK
        delta = hours - weekly_target
        entry: dict = {
            "week_start": monday.isoformat(),
            "week_end": sunday.isoformat(),
            "hours": round(hours, 2),
            "target": weekly_target,
            "delta": round(delta, 2),
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
        elif path == "/" or path == "/index.html":
            with open("index.html", "r") as f:
                self.send_html(f.read())
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
