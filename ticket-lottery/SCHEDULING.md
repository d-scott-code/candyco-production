# Phase 1 — running the loop on a schedule

Phase 1 makes the weekly cycle run itself. Three jobs, all driven through one
entrypoint (`weekly.py`), on the same local-scheduled-task pattern that already
runs this repo's 9:05 AM production report.

## The weekly cycle

| When (suggested) | Command | What happens |
|---|---|---|
| **Mon 9:00** | `python3 weekly.py draw` | Draw every open event whose entry has closed, mark those events `drawn`, and render "you won" emails (with a 48h confirm link) into `outbox/`. |
| **Daily 9:00** | `python3 weekly.py reconcile` | Apply confirmations + 48h timeouts, cascade freed seats down the waitlist, render promotion + last-minute emails, refresh `results.json`. Add `--commit` once you're happy to persist cooldown. |
| **Thu 9:00** | `python3 weekly.py reminder` | Render one broadcast for events closing within `reminder_days_before_close`. |

Each job renders emails to `outbox/<label>/` and updates the JSON. A **send step**
and a **publish step** finish the loop (below).

## Two data syncs (Microsoft Forms → SharePoint → JSON)

The scripts read `data/entries.json` and `data/confirmations.json`. In production
these come from two Microsoft Forms whose responses land in SharePoint lists:

1. **Entry form** → `entries.json` — synced before the Monday `draw`.
2. **Confirm form** (the link in the winner email) → `confirmations.json` — synced before each `reconcile`.

Sync = export/pull the SharePoint list rows into the JSON shape shown in each
file's `_comment`. A tiny Power Automate flow ("When a new response is submitted →
add row to a list", then a scheduled "get items → write JSON to the repo folder")
does this with no code. Until that's wired, the files can be updated by hand.

## The send step

`outbox/<label>/index.json` lists every rendered email (`to`, `subject`, `file`).
Deliver them via either:

- **Power Automate** — "When a file is created in `outbox/`" → send the HTML as an
  email → move the file to a `sent/` folder. Zero code, uses the existing M365 tenant.
- **Microsoft Graph** — a small `sendMail` loop over `index.json` (the same Graph
  path the plant-briefing skill already uses to send HTML mail).

The `outbox/` is **git-ignored** — rendered emails contain names + addresses and
must never reach the public Pages site.

## The publish step

After `reconcile`, commit `data/results.json` (+ `data/events.json` if statuses
changed) and push. GitHub Pages serves the refreshed board — exactly the
commit-and-push the production-report job already does. `results.json` is
PII-free by construction (first name + last initial only).

## Scheduling options

**launchd / cron on the same Mac as the production report** (mirrors what's there):

```cron
# Ticket lottery — draw Mondays, reconcile daily, remind Thursdays
0 9 * * 1  cd /path/to/candyco-production/ticket-lottery && /usr/bin/python3 weekly.py draw
0 9 * * *  cd /path/to/candyco-production/ticket-lottery && /usr/bin/python3 weekly.py reconcile
0 9 * * 4  cd /path/to/candyco-production/ticket-lottery && /usr/bin/python3 weekly.py reminder
```

Wrap each in the same "sync in → run → send → commit/push" script the scheduler
already uses, so entries/confirmations pull first and the board publishes after.

**Cloud Routine (Claude Code on the web):** the same three commands can run as
scheduled Routines instead of a local cron, if you'd rather not depend on the Mac
being awake. Ask and I'll set them up.

## Testing without waiting for real time

Every job takes `--as-of <ISO>` so you can simulate the 48-hour window:

```bash
python3 draw.py --all --seed 42                 # reproducible draw
python3 reconcile.py --as-of 2026-08-14T09:00   # 48h later: confirms + timeouts + cascade
python3 notify.py reminder --as-of 2026-10-16T09:00
```
