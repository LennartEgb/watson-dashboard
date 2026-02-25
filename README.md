# Watson Dashboard

A local web dashboard for [watson](https://tailordev.github.io/Watson/) time tracking. Shows your weekly hours vs. your target, overtime/undertime balance, a 24-week history, and a per-day session timeline.

## Requirements

- Python 3.9+
- [watson](https://tailordev.github.io/Watson/) installed and on your `$PATH`

## Usage

```bash
./start.sh          # starts on http://localhost:8080
./start.sh 9000     # custom port
```

Or directly:

```bash
python3 server.py
python3 server.py 9000
```

Then open **http://localhost:8080** in your browser.

To stop a running server:

```bash
lsof -ti tcp:8080 | xargs kill -9
```

## Features

### Summary cards
- **This week** — hours tracked so far, shown as a percentage of the weekly target
- **Net balance** — cumulative overtime/undertime across all completed weeks in the selected filter window
- **Total overtime / undertime** — aggregate over and under hours for the filter window

### Time range filter
Switch between **This week**, **2 weeks**, **4 weeks**, and **3 months** using the buttons in the header. All filtering is client-side — no extra network requests on filter changes.

### Weekly hours chart
Bar chart of hours worked per week. Bars are colour-coded:

| Colour | Meaning |
|--------|---------|
| Green  | Over target |
| Red    | Under target |
| Blue   | Current week |

A dashed line marks the weekly target. Hovering a bar shows worked hours and delta.

### Daily breakdown (This week)
When **This week** is selected, the chart switches to a per-day view (Mon–Fri). Days with no tracked hours are treated as days off and excluded from the target calculation, so holidays and vacation days do not count against your balance.

### Today's sessions panel
A timeline panel shows all watson sessions for the selected day:

- **Visual timeline bar** — proportional coloured segments across the working day; each project gets a consistent colour
- **Hour axis** — from the first session start to the current time (or end of last session for past dates)
- **Session list** — each session with project name, tags, time range, and duration

Use the **date picker** in the panel header to browse any previous working day. A **↩ Today** button reappears when viewing a past date to jump back. The panel auto-refreshes every 60 seconds when showing today.

### Desktop notifications
When you reach your daily target (default 8h), a browser notification fires once. It resets after midnight so it can fire again the next day. Grant notification permission when prompted on first load.

### Configurable weekly target
Click the **⚙** button in the header to change the weekly target hours (e.g. `20` for a part-time 20h/week schedule). The change takes effect immediately across all charts, cards, and delta calculations — no restart required. The setting is stored in `config.json` next to `server.py`.

### Week table
A per-week breakdown table with hours worked, delta vs. target, a status badge, and a progress bar. Weeks with zero hours (vacation, non-tracking periods) are excluded from the balance calculation.

## Configuration

Settings are stored in `config.json` (auto-created on first run):

```json
{
  "target_hours_per_week": 40.0
}
```

You can edit this file directly or use the ⚙ settings panel in the dashboard.

## Architecture

- **`server.py`** — pure Python stdlib HTTP server; no pip dependencies
- **`index.html`** — single-file frontend using [Chart.js](https://www.chartjs.org/) from CDN; no build step
- **`config.json`** — persisted settings (auto-created)
- All time data is fetched by shelling out to `watson log --json`
- The API always returns 24 weeks; time range filtering is done client-side
