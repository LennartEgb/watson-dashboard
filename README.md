# Watson Dashboard

A local web dashboard for [watson](https://tailordev.github.io/Watson/) time tracking. Shows your weekly hours vs. the 40h/week target, overtime/undertime, and a 24-week history chart.

## Usage

```bash
./start.sh          # starts on http://localhost:8080
./start.sh 9000     # custom port
```

Or directly:

```bash
python3 server.py
```

Then open **http://localhost:8080** in your browser.

## Features

- **Current week progress** — how many hours you've tracked so far this week
- **Net balance** — cumulative overtime/undertime across all tracked weeks
- **24-week bar chart** — green = over target, red = under target, blue = current week
- **Week table** — per-week breakdown with progress bars
- Weeks with zero hours (vacations, non-tracking periods) are excluded from the balance calculation
