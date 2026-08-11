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
├── draw.py             The draw engine (weighted lottery + cooldown + waitlist).
├── data/
│   ├── events.json     Ticket inventory — one row per event. SAFE to publish.
│   ├── members.json    Pilot participants + earned points. PRIVATE (names/emails).
│   ├── entries.json    Who entered which event. PRIVATE.
│   ├── results.json    Draw output for the board. SAFE (first name + last initial only).
│   └── draw_details.json  Generated. PRIVATE (full names + emails). Git-ignored.
└── emails/             Outlook-safe HTML templates: winner, entered, reminder.
```

**Privacy:** the public board only ever reads `events.json` and `results.json`, neither of
which contains emails or full names. `draw_details.json` is git-ignored so real PII never
reaches the public site. In production, `members.json` / `entries.json` live in **SharePoint**,
not git — the sample copies here are fictional data so you can run the pilot end-to-end today.

---

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

## The weekly loop (near-zero-touch, HR-owned)

1. **Entries in** — employees tap *Enter* on the board → a **Microsoft Form** →
   rows land in a **SharePoint list**. Export/sync that list to `entries.json`.
   *(Set `FORM_URL` at the top of `index.html` to your Form's link.)*
2. **Draw** — run `python3 draw.py --all --commit` (later: a scheduled task/Routine,
   exactly like the 9:05 AM production-report job).
3. **Notify** — fill the `emails/` templates from `draw_details.json` and send via Outlook
   (winners + the "entered" confirmations); broadcast the `reminder` before deadlines.
4. **Publish** — commit `events.json` + `results.json`; GitHub Pages updates the board.

## What's manual in Phase 0 vs. automated in Phase 1

- **Phase 0 (now):** Form + SharePoint list by hand; run the draw on demand; send emails
  from the templates. Proves the fairness rules and gauges demand at low build cost.
- **Phase 1:** schedule the draw, auto-generate + send the emails, and auto-cascade the
  48-hour waitlist. Then **Phase 2** extends to the plants (QR flyers, kiosk, SMS) and adds
  the AI helpers (demand forecasting, last-minute broadcast, fairness auditing, HR digest).

---

## Configure before launch

- [ ] Create the **Microsoft Form** and set `FORM_URL` in `index.html`.
- [ ] Create the **SharePoint list** for entries (and one for members/points).
- [ ] Replace the sample `members.json` / `entries.json` with the real pilot roster.
- [ ] Load real upcoming events into `events.json` (set `tier` and `max_party`).
- [ ] Decide access: the board is on **public** GitHub Pages — keep it PII-free (it is), or
      move it behind M365 auth (SharePoint page) if you'd rather it be internal-only.
- [ ] HR/legal sign-off on earning criteria; Finance note on fringe-benefit tax.
