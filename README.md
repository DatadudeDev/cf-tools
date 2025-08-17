Cloudflare Tools (cf-tools)

A collection of Cloudflare automation scripts for batch-processing jobs that you can’t do from the Cloudflare Dashboard UI.

This repo is designed to house a growing set of utilities that help developers and teams automate maintenance tasks, reduce clutter, and keep their Cloudflare accounts tidy.

🚀 Current Tools
1. Cloudflare Pages Deployment Cleanup

Problem:
Every git push creates a new deployment (production or preview) in Cloudflare Pages. Over time, these can pile up — often leaving hundreds of unused deployments that clutter your project.

Solution:
The cleanup_pages_deployments.py script deletes all deployments (production + preview) except the most recent production deployment, ensuring your Pages project stays lean.

It runs in safe batches of 24 deletions per loop with exponential backoff to avoid hitting API rate limits. The script repeats until only the latest production deployment remains.

🛠 Usage
1. Install requirements
pip install requests

2. Set environment variables

Configure the following (safe for public repos — just set them in CI/CD or shell):

export CF_API_TOKEN="your-cloudflare-api-token"
export CF_ACCOUNT_ID="your-cloudflare-account-id"
export CF_PAGES_PROJECT="your-pages-project-name"


CF_API_TOKEN → API token with Pages Read + Delete permissions

CF_ACCOUNT_ID → Found in your Cloudflare dashboard (not your email)

CF_PAGES_PROJECT → Your Pages project name

3. Run the script
python cleanup_pages_deployments.py

4. Exit codes

0 → Success

1 → Config or API fetch failure

2 → Some deletions failed

🔍 Example Output
[init] Validating configuration…
[init] Configuration OK.
[keep] Keeping newest PRODUCTION deployment id=abc123
[loop] Sweep #1 — scanning for deletions…
[loop] Deleting up to 24 of 153 candidates this sweep…
[delete] OK   id=def456
[delete] OK   id=ghi789
...
[loop] Nothing left to delete. Exiting cleanup loop.
[run] Cleanup complete. Deleted=152, Failed=0. Kept id=abc123
[done] Exiting Cloudflare Pages cleanup script.

📦 Roadmap

This repo will expand with more Cloudflare automation helpers, such as:

🔄 Batch DNS record operations

🗑 Bulk cache purge

📊 Analytics fetchers

🧹 Worker + KV cleanup scripts

Stay tuned — contributions and suggestions are welcome!

🤝 Contributing

PRs are welcome! If you have an idea for a Cloudflare script that solves a UI limitation, feel free to open an issue or submit a PR.

📜 License

MIT License © Datadude.dev
