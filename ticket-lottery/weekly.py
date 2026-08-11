#!/usr/bin/env python3
"""
Single entrypoint the scheduler calls — ties the Phase 1 steps together so the
weekly loop runs itself. Each job shells out to the underlying scripts.

    python3 weekly.py draw        # e.g. Monday 9:00 — draw open events whose
                                  #   entry has closed, mark them drawn, and
                                  #   render the "you won" emails.
    python3 weekly.py reconcile   # e.g. daily — process confirmations + 48h
                                  #   timeouts, cascade seats, render follow-ups.
                                  #   Add --commit to finalize cooldown.
    python3 weekly.py reminder    # e.g. Thursday 9:00 — render the deadline
                                  #   reminder for events closing soon.

Rendered emails land in the git-ignored outbox/; a send step (see SCHEDULING.md)
delivers them via Outlook/Graph. See SCHEDULING.md for the cron/launchd/Routine
wiring and how entries/confirmations sync in from Microsoft Forms + SharePoint.
"""

import argparse
import subprocess
import sys

import common

PY = sys.executable
HERE = common.HERE


def run(*script_args):
    subprocess.run([PY, *script_args], cwd=HERE, check=True)


def mark_drawn():
    """Move events that were just drawn out of the 'open' pool so the next
    weekly draw doesn't re-draw them. Cooldown stays with reconcile (confirms)."""
    details = common.load("draw_details.json")
    drawn_ids = {d["event_id"] for d in details["draws"]}
    events_doc = common.load("events.json")
    changed = 0
    for e in events_doc["events"]:
        if e["id"] in drawn_ids and e.get("status") == "open":
            e["status"] = "drawn"
            changed += 1
    if changed:
        common.save("events.json", events_doc)
    print(f"Marked {changed} event(s) drawn.")


def main():
    ap = argparse.ArgumentParser(description="Run a weekly-loop job.")
    ap.add_argument("job", choices=["leadership", "draw", "reconcile", "reminder"])
    ap.add_argument("--commit", action="store_true",
                    help="reconcile/leadership: persist state to events.json")
    args = ap.parse_args()

    if args.job == "leadership":
        # Advance the premium draft, render the current leader's turn email, and
        # (with --commit) persist claims / release leftovers to the lottery.
        run("leadership.py", *(["--commit"] if args.commit else []))
    elif args.job == "draw":
        run("draw.py", "--all")
        mark_drawn()
        run("notify.py", "winners")
    elif args.job == "reconcile":
        run("reconcile.py", *(["--commit"] if args.commit else []))
    else:
        run("notify.py", "reminder")


if __name__ == "__main__":
    main()
