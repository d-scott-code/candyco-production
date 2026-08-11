# CandyCo Ticket Lottery — Phase 0 Pilot

A low-maintenance system for fairly distributing the Delta Center box (4 seats,
~120 events/year: Jazz, Utah Mammoth, and concerts) to employees — without seats
going to waste, and spread across as many people as possible.

Phase 0 is the **office/salaried pilot**. It reuses the exact "zero-maintenance"
pattern this repo already runs for the daily production report: plain data files +
a small script + a static page served on GitHub Pages, plus Outlook emails.

**Live board:** `https://d-scott-code.github.io/candyco-production/ticket-lottery/`

---

## How it works (the model)

1. **Everyone eligible gets 1 base entry** in every draw — so it reads as a broad benefit.
2. **Extra entries are earned** for good behavior (see *Earning entries* below), which
   increase your odds (capped at 10× base so no one dominates).
3. A **weighted random draw** picks winners. **Recent winners get a cooldown** (45 days):
   excluded from *premium* events, reduced odds on *standard* events. This is what
   spreads tickets across many people.
4. **Premium events cap parties at 2** (`max_party`) so a marquee game serves two
   households; lower-demand events allow a full group of 4 so seats always fill.
5. Winners are emailed and have **48 hours to confirm**. Unclaimed seats cascade down an
   **ordered waitlist**, then appear as **last-minute open seats** anyone can grab.

## Earning entries (pilot criteria — start simple, expand later)

| Source | Entries |
|---|---|
| Base entry (every eligible employee) | +1 automatically |
| Peer / manager recognition (shout-out, core-value nom) | +1 each |
| Completed safety training / near-miss report | +1 each |
| Perfect attendance for the month *(bonus only — never penalizes protected leave)* | +1 |
| Work anniversary / milestone | +1 |

> **Before launch, HR/legal must sign off on the criteria.** Reward *leading* safety
> behaviors (training, reporting) — never "no injuries," which can suppress reporting and
> run afoul of OSHA anti-retaliation rules. Attendance rewards must not touch FMLA/ADA/sick
> leave. Also loop in Finance: employer tickets can be a taxable fringe benefit.

---

## Files

```
ticket-lottery/
├── index.html          Employee board (GitHub Pages). Reads events.json + results.json.
├── config.json         Phase 1 settings (Form URLs, seat location, 48h window, board URL).
├── import_events.py    Turn scraped deltacenter.com events into events.json.     [events]
├── draw.py             The draw engine (weighted lottery + cooldown + waitlist).
├── notify.py           Renders winner + reminder emails into outbox/.            [Phase 1]
├── reconcile.py        Confirmations + 48h timeouts + waitlist cascade + follow-ups. [Phase 1]
├── weekly.py           One entrypoint the scheduler calls: draw / reconcile / reminder. [Phase 1]
├── common.py           Shared helpers for the Phase 1 scripts.
├── data/
│   ├── events.json       Ticket inventory — one row per event. SAFE to publish.
│   ├── raw_events.json   Events scraped from deltacenter.com (input to import). SAFE.  [events]
│   ├── members.json      Pilot participants + earned points. PRIVATE (names/emails).
│   ├── entries.json      Who entered which event. PRIVATE.
│   ├── confirmations.json Winner confirm/decline responses. PRIVATE.              [Phase 1]
│   ├── results.json      Draw output for the board. SAFE (first name + last initial only).
│   └── draw_details.json Generated. PRIVATE (full names + emails). Git-ignored.
├── emails/             Outlook-safe HTML templates: winner, entered, reminder, lastminute.
├── outbox/             Generated, git-ignored. Rendered emails awaiting send.     [Phase 1]
└── SCHEDULING.md       How to run the loop on a schedule (cron/launchd/Routine).  [Phase 1]
```

**Privacy:** the public board only ever reads `events.json` and `results.json`, neither of
which contains emails or full names. `draw_details.json` is git-ignored so real PII never
reaches the public site. In production, `members.json` / `entries.json` live in **SharePoint**,
not git — the sample copies here are fictional data so you can run the pilot end-to-end today.

---

## Loading events from deltacenter.com

The event pool is pulled from the Delta Center's public listing rather than typed by
hand. `data/events.json` was built from `data/raw_events.json` (a scrape of
<https://www.deltacenter.com/events>) by:

```bash
python3 import_events.py --replace   # first real import (drops the samples)
python3 import_events.py             # later: merge refresh, keeps drawn/edited events
```

`import_events.py` classifies league, sets `tier` (concerts + marquee games → premium),
computes `entry_close` (date − `entry_close_days`) and a stable `id`, and — on a merge —
preserves the `status` and any manual `tier`/`max_party` you set. Tweak individual events
in `events.json` afterward; a merge refresh won't clobber those.

**To refresh:** re-scrape `deltacenter.com/events` into `data/raw_events.json`, then run
`python3 import_events.py`. The site shows a rolling window with a "Load More" button, so
re-run periodically to pick up newly announced events. (Ask Claude to "refresh the Delta
Center events" and it will re-scrape + import — a good candidate for a scheduled step.)

**Two caveats worth knowing:**
- **No Jazz games.** `deltacenter.com/events` lists Utah Mammoth, concerts, and other
  events but **not Utah Jazz** (published separately). Add Jazz to `raw_events.json` from
  `utahjazz.com` when you want them in the pool.
- **Tiers are a heuristic.** Marquee opponents and all concerts default to `premium`
  (`max_party: 2`); adjust any event by hand.

## Running a draw

```bash
cd ticket-lottery

python3 draw.py --all --seed 42     # reproducible dry run of all open events
python3 draw.py --event 2026-10-24-jazz-lakers   # just one event
python3 draw.py --all --commit      # persist wins: sets last_won, resets points,
                                    # marks events "drawn", writes results.json
```

A dry run writes `results.json` (board) and `draw_details.json` (emails) but does **not**
change member state. `--commit` records the wins so the cooldown applies going forward.
No dependencies — standard-library Python 3 only.

## The weekly loop — automated (Phase 1)

Phase 1 runs the cycle itself through one entrypoint. Full wiring (Forms→SharePoint
sync, the send step, cron/launchd/Routine) is in **`SCHEDULING.md`**.

```bash
python3 weekly.py draw        # Mon: draw closed events, mark them drawn, render winner emails
python3 weekly.py reconcile   # daily: confirmations + 48h timeouts + waitlist cascade + follow-ups
python3 weekly.py reconcile --commit   # ...same, and persist cooldown for confirmed winners
python3 weekly.py reminder    # Thu: broadcast for events closing soon
```

What each stage does:

1. **Draw** (`draw.py`) — weighted lottery over open events; winners start `pending`.
2. **Notify** (`notify.py`) — one "you won" email per pending winner with a confirm link
   and a **48-hour deadline**, plus the deadline **reminder** broadcast. Emails render to
   the git-ignored `outbox/`; a send step delivers them (see `SCHEDULING.md`).
3. **Reconcile** (`reconcile.py`) — the follow-through: **confirm** keeps the seats,
   **decline** or a **48h timeout** frees them, and freed seats **cascade down the ordered
   waitlist** (parties kept together, up to `max_party`). Promoted winners get their own
   email + deadline; any seats left after the waitlist is exhausted trigger a **last-minute
   broadcast** so nothing is wasted. `--commit` records cooldown for confirmed winners.
4. **Publish** — commit `results.json`; GitHub Pages refreshes the board.

Every step accepts `--as-of <ISO>` so you can simulate the 48-hour window in seconds.

**Cooldown timing:** in the automated loop, cooldown is applied at **confirmation**
(`reconcile --commit`), not at draw time — so it lands on people who actually get tickets,
including promoted winners. (`draw.py --commit` remains the manual one-shot path from Phase 0.)

## Phase roadmap

- **Phase 0 (done):** board + weighted draw + email templates, run on demand.
- **Phase 1 (this):** scheduled draw, auto-rendered emails, 48-hour confirm + waitlist
  cascade + last-minute broadcast — the loop runs itself.
- **Phase 2 (next):** extend to the plants (QR flyers, kiosk, SMS) and add the AI helpers
  (demand forecasting, targeted nudges, fairness auditing, HR digest).

---

## Configure before launch

- [ ] Create the **entry** Microsoft Form (→ `FORM_URL` in `index.html` and `config.json`)
      and the **confirm** Form (→ `confirm_url` in `config.json`).
- [ ] Fill the rest of `config.json` (seat location, board URL, broadcast address).
- [ ] Create the **SharePoint lists** for entries, confirmations, and members/points, and
      wire the Forms→SharePoint→JSON syncs (see `SCHEDULING.md`).
- [ ] Replace the sample `members.json` / `entries.json` / `confirmations.json` with real data.
- [ ] Load real upcoming events into `events.json` (set `tier` and `max_party`).
- [ ] Schedule the three `weekly.py` jobs (see `SCHEDULING.md`).
- [ ] Decide access: the board is on **public** GitHub Pages — keep it PII-free (it is), or
      move it behind M365 auth (SharePoint page) if you'd rather it be internal-only.
- [ ] HR/legal sign-off on earning criteria; Finance note on fringe-benefit tax.
