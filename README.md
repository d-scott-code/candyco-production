# CandyCo Production — Setup Guide

This is a one-time setup. Once complete, the web app updates itself every morning at 9:05 AM with no further effort from you.

---

## What you'll need
- A free GitHub account (github.com)
- Git installed on your Mac (it likely already is — open Terminal and type `git --version` to check)

---

## Step 1 — Create the GitHub repo

1. Go to [github.com/new](https://github.com/new)
2. **Repository name:** `candyco-production`
3. **Visibility:** Public *(required for free GitHub Pages — the URL is obscure enough for internal use; if you want it private, you'll need GitHub Pro)*
4. Leave everything else as default and click **Create repository**

---

## Step 2 — Upload the app files

1. On your new repo page, click **uploading an existing file**
2. Drag in the entire `candyco-production` folder contents:
   - `index.html`
   - `manifest.json`
   - `reports/.gitkeep`
3. Scroll down, add a commit message like `Initial setup`, and click **Commit changes**

---

## Step 3 — Enable GitHub Pages

1. In your repo, go to **Settings** → **Pages** (left sidebar)
2. Under **Source**, select **Deploy from a branch**
3. Branch: `main` · Folder: `/ (root)` → click **Save**
4. Wait about 60 seconds, then refresh. You'll see:
   > *Your site is live at* `https://YOUR-USERNAME.github.io/candyco-production`

Bookmark that URL on your phone and laptop. That's your production dashboard.

---

## Step 4 — Clone the repo to your Mac

Open **Terminal** and run:

```bash
cd ~
git clone https://github.com/YOUR-USERNAME/candyco-production.git
```

This creates `~/candyco-production` on your Mac. The scheduled task will push new reports to this folder every morning.

---

## Step 5 — Authenticate git with GitHub

The scheduled task needs to push to GitHub without prompting for a password. The easiest way is a **Personal Access Token (PAT)**:

1. Go to [github.com/settings/tokens/new](https://github.com/settings/tokens/new)
2. Note: `candyco-production push`
3. Expiration: **No expiration** (or 1 year — your call)
4. Scopes: check **repo**
5. Click **Generate token** and copy it

Then in Terminal, trigger a push to save your credentials:

```bash
cd ~/candyco-production
git push origin main
```

When prompted for username, enter your GitHub username. For password, paste your PAT (not your GitHub password). macOS will save it in Keychain — you won't be asked again.

---

## You're done

The scheduled task is already set up and will run every morning at 9:05 AM. It will:
1. Run the production-report skill (pulls SharePoint data, builds the report)
2. Save the HTML file to `~/candyco-production/reports/`
3. Update the date archive (`manifest.json`)
4. Push to GitHub — your live URL updates within seconds

---

## Troubleshooting

**The page shows "Almost there" instead of a report**
→ The repo isn't set up yet, or GitHub Pages isn't enabled. Follow Steps 2–3 above.

**The scheduled task ran but no new report appeared**
→ Open Terminal and run: `cd ~/candyco-production && git status`
Look for any error messages. Most likely cause is git credentials need to be re-entered (see Step 5).

**The report loads but looks broken**
→ Hard-refresh the page (Cmd+Shift+R on desktop). GitHub Pages can cache aggressively.

**Want to look further back than 90 days?**
→ All report files are stored in the `reports/` folder in your GitHub repo forever. The date picker only shows 90 days for cleanliness — every file is still there if you need it.
