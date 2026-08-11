#!/usr/bin/env python3
"""
Leadership premium-event draft.

Premium events don't go straight to the general lottery. They're offered to the
leadership team first, in a serial "on the clock" draft:

  * Priority order comes from config.leadership.order (Scott first).
  * Even round-robin: the leader on the clock either CLAIMS one available premium
    event or PASSES. Either way the turn advances to the next person; a CLAIM also
    sends that leader to the BOTTOM of the order.
  * Each leader gets up to `picks_per_leader` (4) claims.
  * Each turn has a `turn_window_hours` (48h) deadline; no response auto-passes.
  * When every leader is capped or a full round passes with no claim (or the pool
    empties), the draft is COMPLETE and any unclaimed premium events are released
    to the general lottery (status -> "open").

State is replayed deterministically from data/leadership_picks.json (the record of
claims/passes, e.g. from a leadership Microsoft Form) plus config.leadership.started.

    python3 leadership.py --as-of 2026-08-14T09:00            # dry run: status + turn email
    python3 leadership.py --as-of 2026-08-14T09:00 --commit    # persist claims / releases to events.json

Outputs:
  data/leadership_status.json   PUBLIC board view (names + claimed event titles).
  outbox/<label>/               the "you're on the clock" email for the current leader.
  events.json (with --commit)   claimed events -> status "claimed"; on completion,
                                unclaimed premium -> status "open" (general lottery).
"""

import argparse
from collections import defaultdict
from datetime import datetime, timedelta

import common


def latest_picks_by_turn(picks):
    """Return each leader's actions in timestamp order."""
    by_leader = defaultdict(list)
    for p in sorted(picks, key=lambda x: x["timestamp"]):
        by_leader[p["leader_id"]].append(p)
    return by_leader


def replay(events, config, picks, as_of):
    lead = config["leadership"]
    cap = lead.get("picks_per_leader", 4)
    window = lead.get("turn_window_hours", 48)
    start = common.parse_dt(lead["started"])
    order = [m["id"] for m in lead["order"]]
    by_id = {m["id"]: m for m in lead["order"]}

    # Draft pool = premium events not yet released to the general lottery,
    # in date order.
    pool = [e for e in events
            if e.get("tier") == "premium" and e.get("status") in ("leadership", "claimed")]
    pool.sort(key=lambda e: e["date"])
    available = [e["id"] for e in pool]
    ev_by_id = {e["id"]: e for e in pool}

    actions = latest_picks_by_turn(picks)
    idx = defaultdict(int)          # per-leader consumed-action pointer
    counts = defaultdict(int)
    assigned = {}                   # event_id -> leader_id
    order = list(order)
    pos = 0
    turn_start = start
    passes_in_row = 0
    on_clock = None
    turn_deadline = None
    phase = "in_progress"

    while True:
        eligible = [lid for lid in order if counts[lid] < cap]
        if not eligible or not available:
            phase = "complete"
            break
        # advance pointer to the next eligible leader
        guard = 0
        while counts[order[pos % len(order)]] >= cap:
            pos = (pos + 1) % len(order)
            guard += 1
            if guard > len(order):
                break
        lid = order[pos % len(order)]

        acts = actions.get(lid, [])
        act = acts[idx[lid]] if idx[lid] < len(acts) else None

        if act is not None:
            idx[lid] += 1
            if act["action"] == "claim" and act.get("event_id") in available:
                eid = act["event_id"]
                assigned[eid] = lid
                available.remove(eid)
                counts[lid] += 1
                order.remove(lid)          # claimer -> bottom
                order.append(lid)
                passes_in_row = 0
                turn_start = common.parse_dt(act["timestamp"])
                # pointer keeps index; it now lands on the next leader
                pos = pos % len(order)
            else:
                passes_in_row += 1
                turn_start = common.parse_dt(act["timestamp"])
                pos = (pos + 1) % len(order)
            if passes_in_row >= len([l for l in order if counts[l] < cap]):
                phase = "complete"
                break
            continue

        # no recorded action for this leader's turn
        deadline = turn_start + timedelta(hours=window)
        if as_of >= deadline:
            passes_in_row += 1
            turn_start = deadline
            pos = (pos + 1) % len(order)
            if passes_in_row >= len([l for l in order if counts[l] < cap]):
                phase = "complete"
                break
            continue
        else:
            on_clock = lid
            turn_deadline = deadline
            break

    return {
        "phase": phase,
        "on_clock": on_clock,
        "turn_deadline": turn_deadline.isoformat(timespec="seconds") if turn_deadline else None,
        "order": list(order),
        "counts": dict(counts),
        "assigned": assigned,
        "available": list(available),
        "ev_by_id": ev_by_id,
        "by_id": by_id,
        "cap": cap,
    }


def build_status(state, config):
    by_id, ev = state["by_id"], state["ev_by_id"]
    claims = [{"leader": by_id[lid]["name"], "event_id": eid,
               "title": ev[eid]["title"], "date": ev[eid]["date"]}
              for eid, lid in state["assigned"].items()]
    claims.sort(key=lambda c: c["date"])
    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "phase": state["phase"],
        "on_clock": by_id[state["on_clock"]]["name"] if state["on_clock"] else None,
        "turn_deadline": state["turn_deadline"],
        "picks_per_leader": state["cap"],
        "order": [by_id[lid]["name"] for lid in state["order"]],
        "counts": {by_id[lid]["name"]: n for lid, n in state["counts"].items()},
        "claims": claims,
        "available_count": len(state["available"]),
    }


def turn_email(state, config):
    """The 'you're on the clock' email for the current leader."""
    lid = state["on_clock"]
    if not lid:
        return None
    leader = state["by_id"][lid]
    ev = state["ev_by_id"]
    cfg = config
    board = cfg.get("board_url", "")
    claim_base = cfg.get("leadership_claim_url", cfg.get("confirm_url", ""))
    rows = ""
    for eid in state["available"]:
        e = ev[eid]
        link = f'{claim_base}?who={leader["id"]}&event={eid}'
        rows += (f'<tr><td style="padding:8px 0;border-bottom:1px solid #eee;font-size:14px;">'
                 f'<b>{e["title"]}</b><br><span style="color:#64748b;">'
                 f'{common.fmt_date(e["date"])}</span></td>'
                 f'<td style="text-align:right;border-bottom:1px solid #eee;">'
                 f'<a href="{link}" style="color:#23CE6B;font-weight:700;">Claim</a></td></tr>')
    deadline = common.fmt_datetime(common.parse_dt(state["turn_deadline"]))
    html = common.render("leadership_turn.html", {
        "name": leader["name"],
        "deadline": deadline,
        "remaining": len(state["available"]),
        "picks_left": state["cap"] - state["counts"].get(lid, 0),
        "event_rows": rows,
        "board_url": board,
        "pass_link": f'{claim_base}?who={leader["id"]}&action=pass',
    })
    return {"to": leader["email"],
            "subject": "\U0001f3df You're on the clock — CandyCo premium tickets",
            "filename": f"leadership_turn_{leader['id']}.html", "html": html}


def main():
    ap = argparse.ArgumentParser(description="Run the leadership premium-event draft.")
    ap.add_argument("--as-of", help="ISO datetime override (testing)")
    ap.add_argument("--label", help="outbox subfolder name override")
    ap.add_argument("--commit", action="store_true",
                    help="persist claims (and releases on completion) to events.json")
    args = ap.parse_args()

    config = common.load_config()
    events_doc = common.load("events.json")
    picks = common.load("leadership_picks.json").get("picks", [])
    as_of = common.now_or(args.as_of)

    state = replay(events_doc["events"], config, picks, as_of)
    status = build_status(state, config)
    common.save("leadership_status.json", status)

    # console summary
    print(f"Leadership draft — {state['phase']}")
    if state["on_clock"]:
        print(f"  On the clock: {state['by_id'][state['on_clock']]['name']}  "
              f"(deadline {state['turn_deadline']})")
    for c in status["claims"]:
        print(f"  claimed  {c['leader']:<16} {c['date']}  {c['title']}")
    print(f"  {status['available_count']} premium event(s) still available; "
          f"counts: {status['counts']}")

    email = turn_email(state, config)
    if email:
        label = args.label or f"leadership-{as_of:%Y%m%dT%H%M%S}"
        out, _ = common.write_outbox(label, [email])
        print(f"  Wrote turn email to {out} -> {email['to']}")

    if args.commit:
        ev_by_id = {e["id"]: e for e in events_doc["events"]}
        for eid, lid in state["assigned"].items():
            e = ev_by_id.get(eid)
            if e:
                e["status"] = "claimed"
                e["claimed_by"] = state["by_id"][lid]["name"]
        if state["phase"] == "complete":
            for eid in state["available"]:
                e = ev_by_id.get(eid)
                if e:
                    e["status"] = "open"      # release to the general lottery
        common.save("events.json", events_doc)
        released = len(state["available"]) if state["phase"] == "complete" else 0
        print(f"  Committed: {len(state['assigned'])} claimed"
              + (f", {released} released to the general lottery." if released else "."))
    else:
        print("  Dry run. Re-run with --commit to persist claims / releases.")


if __name__ == "__main__":
    main()
