# Hosting on Cloudflare Pages (public board + private leadership page)

The whole ticket board runs as one Cloudflare Pages project: the **public** employee
board, a **private leadership** page, and a tiny **Function + KV** store that powers the
include/exclude "move" buttons. GitHub stays the source repo; Cloudflare builds from it.

```
ticket-lottery/
├── index.html            Public board — reads GET /api/board (falls back to the static list)
├── leadership/index.html Private leadership page — behind Cloudflare Access
├── functions/api/
│   ├── board.js   GET  /api/board   PUBLIC  — public-list events only
│   ├── admin.js   GET  /api/admin   GATED   — both lists + picks + who you are
│   ├── move.js    POST /api/move    GATED   — move an event public <-> leadership
│   └── pick.js    POST /api/pick    GATED   — claim / release a leadership event
└── functions/_shared.js  helpers (OWNER_EMAIL, default-list rule, KV access)
```

**Default split:** basketball (NBA/Jazz) + hockey (NHL/Mammoth) → **public**; everything
else (concerts, UFC, family shows, …) → **leadership**. The move buttons override this per
event, and the override is saved in KV.

**Owner:** `OWNER_EMAIL` in `functions/_shared.js` (Scott) is unlimited and not in the
round-robin; everyone else is capped at 4 claims.

## One-time setup

**1 — Connect the repo (Pages project).**
Cloudflare dashboard → Workers & Pages → Create → Pages → Connect to Git → pick
`d-scott-code/candyco-production`. Build settings: **Framework preset = None**, **Build
command = empty**, **Build output directory = `/`**. Deploy. Your board is then at
`https://<project>.pages.dev/ticket-lottery/` (add a custom domain later if you like).

**2 — Create the KV store and bind it.**
Workers & Pages → KV → **Create namespace** (e.g. `ticket-lottery`). Then in the Pages
project → **Settings → Functions → KV namespace bindings** → add a binding with
**Variable name `LOTTERY`** → your namespace. Add it for **both Production and Preview**.
(No KV = the pages still render read-only; moves just won't save.)

**3 — Gate the private routes with Access.**
Cloudflare **Zero Trust** → Access → Applications → **Add a self-hosted application**.
Protect these paths on your Pages domain:
- `/ticket-lottery/leadership*`
- `/api/admin`, `/api/move`, `/api/pick`

Leave **`/api/board` public** (it only ever returns public events).
Add one **policy → Allow**, Include → **Emails**: the leadership team
(Scott, Dave, Aubrey, Chad, Ryan, Kathleen, Stephanie, Matt). Login method: One-time PIN
or Google. Access then injects each person's verified email, which the Functions read to
enforce the owner/round-robin rules.

**4 — Confirm the owner email.**
`functions/_shared.js` → `OWNER_EMAIL` = the address that should be unlimited /
first-pick (default `scott.maxfield@candyco.com`).

## Using it

- **Employees** open `/ticket-lottery/` → see only public-list events.
- **Leadership** open `/ticket-lottery/leadership/` (sign in via Access) → see both lists;
  each event has a **Send to public →** (or **← Pull to leadership**) button, and
  leadership-list events have a **Claim** button.
- Moves/claims save to KV instantly and the public board reflects them on next load.

## Notes

- Without Cloudflare Functions (e.g. plain GitHub Pages or local `python3 -m http.server`),
  the **public board still works** via a static fallback — it shows the default-public
  (basketball + hockey) events from `data/events.json`. The leadership page needs Cloudflare.
- The formal weighted draw / confirm-cascade (`draw.py`, `reconcile.py`) still runs the
  public lottery for public-list events; scoping those to the public list is a follow-up.
