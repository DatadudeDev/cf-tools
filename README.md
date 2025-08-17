# cf-tools — Cloudflare Batch Utilities

A growing collection of **small, sharp tools** for Cloudflare housekeeping tasks that are awkward or impossible to do quickly in the UI — especially **batch** or **looped** maintenance jobs.

> **Status:** v0 — first utility included. More coming soon.

---

## ✨ Included Tools

### 1) Pages Deployment Wiper (keep newest production)
Deletes **all** Cloudflare Pages deployments (both **production** and **preview**) **except** the newest production deployment for a project. Useful after a burst of commits that left hundreds of old deployments lying around.

- Loops in batches (default: 24 per sweep)
- Retries politely with backoff on 429/5xx
- Stops automatically when nothing eligible remains
- Streams clear logs for CI

**Script:** `cleanup_pages_deployments.py`

<details>
<summary>What it does, exactly</summary>

- Fetches deployments for the project (`production` and `preview`) via the Cloudflare API.
- Determines the **single newest production** deployment and marks it as the **keep**.
- Repeatedly deletes:
  - All **preview** deployments.
  - All **older production** deployments (i.e., every production deployment except the newest one).
- Works in sweeps of 24 by default until there’s nothing left to delete.
</details>

---

## ⚙️ Requirements

- **Python** ≥ 3.8
- **requests** library (`pip install -r requirements.txt` or `pip install requests`)
- A Cloudflare API token with **Pages read + delete** permissions for the account

> ⚠️ **Irreversible:** Deletions can’t be undone. Double-check your project and account IDs.

---

## 🔧 Configuration

Set the following **environment variables** (safe for public repos when stored as CI secrets):

- `CF_API_TOKEN` — Cloudflare API Token (Pages read/delete for the account)
- `CF_ACCOUNT_ID` — Your Cloudflare **Account ID** (not your email)
- `CF_PAGES_PROJECT` — Cloudflare **Pages project** name (slug)

You can find:
- **Account ID** in the Cloudflare dashboard URL bar (Account Home) or in **Workers & Pages → Overview**.
- **Project name** in **Workers & Pages → Pages → Your Project** (the slug used in API URLs).

---

## 🚀 Quick Start (local)

```bash
# 1) Clone
git clone https://github.com/datadudedev/cf-tools.git
cd cf-tools

# 2) Install deps
python -m venv .venv && source .venv/bin/activate   # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt

# 3) Export env vars
export CF_API_TOKEN=********
export CF_ACCOUNT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
export CF_PAGES_PROJECT=my-pages-project

# 4) Run the wiper
python cleanup_pages_deployments.py
