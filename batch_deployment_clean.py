#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cloudflare Pages Deployment Cleanup

Deletes ALL deployments (production + preview) EXCEPT the latest production one.
Runs in batches of 24 and loops until nothing but the newest production deployment remains.

Environment variables (safe for public repos; set these in your CI/CD or shell):
  CF_API_TOKEN       - Cloudflare API Token with Pages read/delete permissions
  CF_ACCOUNT_ID      - Cloudflare Account ID
  CF_PAGES_PROJECT   - Cloudflare Pages project name

Usage:
  python cleanup_pages_deployments.py

Exit codes:
  0 - Success
  1 - Config or API fetch failure
  2 - Deletion failures occurred
"""

import os
import sys
import time
import json
import typing as t
import requests

# -------------------- Configuration (annotated) --------------------
# Batch size: Cloudflare API is fine with single deletes; we throttle ourselves and group logical work.
BATCH_SIZE     = 24         # delete up to 24 per loop iteration
SLEEP_BETWEEN  = 0.15       # polite pause between individual deletes (seconds)
MAX_RETRIES    = 5          # retry limit for transient HTTP errors (429/5xx)
BACKOFF_BASE   = 0.75       # base seconds for exponential backoff (will multiply by 2**attempt)
TIMEOUT_SEC    = 30         # HTTP request timeout

# Read environment variables with sane placeholders for public repo defaults
API_TOKEN    = os.getenv("CF_API_TOKEN", "YOUR-API-TOKEN")
ACCOUNT_ID   = os.getenv("CF_ACCOUNT_ID", "YOUR-PROJECT-ID")
PROJECT_NAME = os.getenv("CF_PAGES_PROJECT", "YOUR-PROJECT")

BASE = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/pages/projects/{PROJECT_NAME}"
HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# -------------------- Utilities (annotated) --------------------
def _log(msg: str) -> None:
    """Simple stdout logger with flush for CI visibility."""
    print(msg, flush=True)

def _check_config() -> None:
    """Validate configuration early with actionable messages."""
    problems = []
    if not API_TOKEN or API_TOKEN.startswith("YOUR-"):
        problems.append("CF_API_TOKEN is not set (or using placeholder).")
    if not ACCOUNT_ID or ACCOUNT_ID.startswith("YOUR-"):
        problems.append("CF_ACCOUNT_ID is not set (or using placeholder).")
    if not PROJECT_NAME or PROJECT_NAME.startswith("YOUR-"):
        problems.append("CF_PAGES_PROJECT is not set (or using placeholder).")
    if problems:
        for p in problems:
            _log(f"[config] {p}")
        raise SystemExit(1)

def _request_with_retries(method: str, url: str, **kwargs) -> requests.Response:
    """
    Wrapper for requests with exponential backoff on 429/5xx.
    Annotated with clear messages on each attempt.
    """
    attempt = 0
    while True:
        try:
            attempt += 1
            _log(f"[http] {method.upper()} {url} (attempt {attempt}/{MAX_RETRIES})")
            resp = requests.request(method, url, headers=HEADERS, timeout=TIMEOUT_SEC, **kwargs)
            if resp.status_code in (429, 500, 502, 503, 504):
                if attempt < MAX_RETRIES:
                    delay = BACKOFF_BASE * (2 ** (attempt - 1))
                    _log(f"[http] Transient error {resp.status_code}; backing off {delay:.2f}s…")
                    time.sleep(delay)
                    continue
            return resp
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                delay = BACKOFF_BASE * (2 ** (attempt - 1))
                _log(f"[http] Exception: {e!r}; retrying in {delay:.2f}s…")
                time.sleep(delay)
                continue
            _log(f"[http] Error after {attempt} attempts: {e!r}")
            raise

def _sort_newest_first(deployments: t.List[dict]) -> t.List[dict]:
    """Defensively sort deployments by created_on desc if present."""
    return sorted(deployments or [], key=lambda d: d.get("created_on", ""), reverse=True)

# -------------------- Cloudflare API helpers (annotated) --------------------
def cf_get_deployments(env: t.Optional[str] = None) -> t.List[dict]:
    """
    Fetch deployments for the given environment:
      env in { 'production', 'preview', None }  (None == all)
    Notes:
      - Do NOT pass page/per_page (causes 8000024 per Cloudflare error).
      - Returns newest-first.
    """
    params: dict = {}
    if env in ("production", "preview"):
        params["env"] = env

    url = f"{BASE}/deployments"
    try:
        resp = _request_with_retries("GET", url, params=params)
        if resp.status_code != 200:
            _log(f"[fetch] Error fetching deployments ({env or 'all'}): {resp.status_code} {resp.text}")
            raise RuntimeError("Fetch deployments failed")
        data = resp.json()
        if not data.get("success", False):
            _log(f"[fetch] Cloudflare response not success: {json.dumps(data)[:500]}")
            raise RuntimeError("Fetch deployments returned success=false")
        deployments = data.get("result") or []
        deployments = _sort_newest_first(deployments)
        _log(f"[fetch] Retrieved {len(deployments)} {env or 'all'} deployments.")
        return deployments
    except Exception as e:
        _log(f"[fetch] Exception while fetching deployments: {e}")
        raise

def cf_delete_deployment(deployment_id: str) -> bool:
    """
    Delete a single deployment by id.
    Returns True on success, False on failure (and logs the response).
    """
    url = f"{BASE}/deployments/{deployment_id}"
    try:
        resp = _request_with_retries("DELETE", url)
        ok = (resp.status_code == 200)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        if ok and body.get("success") is True:
            _log(f"[delete] OK   id={deployment_id}")
            return True
        _log(f"[delete] FAIL id={deployment_id} status={resp.status_code} body={str(body)[:500]}")
        return False
    except Exception as e:
        _log(f"[delete] Exception deleting id={deployment_id}: {e}")
        return False

# -------------------- Core cleanup logic (annotated) --------------------
def determine_keep_id() -> str:
    """
    Determine the single production deployment to keep (newest one).
    Safety check: abort if none found.
    """
    prod = cf_get_deployments("production")
    if not prod:
        _log("[keep] No production deployments found — aborting for safety.")
        raise SystemExit(1)
    keep_id = prod[0].get("id")
    if not keep_id:
        _log("[keep] Newest production deployment lacks an 'id' — aborting.")
        raise SystemExit(1)
    _log(f"[keep] Keeping newest PRODUCTION deployment id={keep_id}")
    return keep_id

def list_candidates_to_delete(keep_id: str) -> t.List[dict]:
    """
    Build the list of deployments to delete:
      - All PREVIEW deployments
      - All PRODUCTION deployments except the newest one (keep_id)
    Returns a combined list (newest-first within each env fetch).
    """
    prod = cf_get_deployments("production")
    previews = cf_get_deployments("preview")
    # Everything except the newest production
    older_prod = [d for d in prod[1:] if d.get("id") and d["id"] != keep_id]
    # All previews
    preview_all = [d for d in previews if d.get("id") and d["id"] != keep_id]
    candidates = older_prod + preview_all
    _log(f"[scan] Candidates to delete: {len(candidates)}")
    return candidates

def delete_in_batches_until_done(keep_id: str) -> t.Tuple[int, int]:
    """
    Repeatedly delete deployments in batches of BATCH_SIZE until none remain
    except the keep_id. Returns (deleted_count, failed_count).
    """
    total_deleted = 0
    total_failed = 0
    loop_idx = 0

    # Track candidate-id set across sweeps to detect "stuck" state with no progress
    prev_candidate_ids: t.Optional[t.Tuple[str, ...]] = None

    while True:
        loop_idx += 1
        _log(f"\n[loop] Sweep #{loop_idx} — scanning for deletions…")
        candidates = list_candidates_to_delete(keep_id)

        if not candidates:
            _log("[loop] Nothing left to delete. Exiting cleanup loop.")
            break

        # Snapshot candidate IDs for stagnation detection
        candidate_ids = tuple(d.get("id") for d in candidates if d.get("id"))

        batch = candidates[:BATCH_SIZE]
        _log(f"[loop] Deleting up to {len(batch)} of {len(candidates)} candidates this sweep…")

        sweep_deleted = 0
        for d in batch:
            dep_id = d.get("id")
            if not dep_id or dep_id == keep_id:
                continue
            ok = cf_delete_deployment(dep_id)
            if ok:
                total_deleted += 1
                sweep_deleted += 1
            else:
                total_failed += 1
            time.sleep(SLEEP_BETWEEN)

        # If we made no progress AND we've already seen this exact set of (few) candidates,
        # consider them not currently eligible (e.g., aliased/force-required) and stop looping.
        # Guard with <= BATCH_SIZE so we don't prematurely stop when there might be more
        # deletable items beyond the current batch.
        if sweep_deleted == 0 and len(candidates) <= BATCH_SIZE and prev_candidate_ids == candidate_ids:
            _log("[loop] No eligible deletions remain (same undeletable candidates persist). Exiting cleanup loop.")
            break

        prev_candidate_ids = candidate_ids

        # Small breather between sweeps to be polite to the API
        time.sleep(0.5)

    return total_deleted, total_failed

# -------------------- Entry point (annotated) --------------------
def main() -> int:
    """
    Orchestrates config validation, identifies the keep_id, and loops batch deletes
    until only the newest production deployment remains.
    """
    # Guard config
    try:
        _log("[init] Validating configuration…")
        _check_config()
        _log("[init] Configuration OK.")
    except SystemExit:
        # Already logged actionable config errors
        return 1
    except Exception as e:
        _log(f"[init] Unexpected config error: {e}")
        return 1

    # Resolve the deployment we must keep forever
    try:
        keep_id = determine_keep_id()
    except SystemExit:
        return 1
    except Exception as e:
        _log(f"[keep] Failed to determine keep_id: {e}")
        return 1

    # Perform batch deletes until done
    deleted = failed = 0
    try:
        _log("[run] Starting cleanup loop…")
        deleted, failed = delete_in_batches_until_done(keep_id)
        if failed == 0:
            _log(f"[run] Cleanup complete. Deleted={deleted}, Failed={failed}. Kept id={keep_id}")
            return 0
        else:
            _log(f"[run] Cleanup finished with some failures. Deleted={deleted}, Failed={failed}. Kept id={keep_id}")
            return 2
    except Exception as e:
        _log(f"[run] Fatal error during cleanup: {e}")
        return 2
    finally:
        _log("[done] Exiting Cloudflare Pages cleanup script.")

if __name__ == "__main__":
    sys.exit(main())
