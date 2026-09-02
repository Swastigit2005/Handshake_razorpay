# Deploying Handshake

No Docker. The submission is a public GitHub repository plus a live URL that a
reviewer can open without installing anything.

The console runs with **no credentials at all**: `HS_PAYMENTS=sim` and
`HS_BUYERS=heuristic` are the defaults, and the canonical run is committed in
`runs/`, so a cold instance shows real, hash-verified figures on first paint.
Keys are optional and only switch the live backends on.

---

## 0 · Preconditions

```bash
cd ~/Desktop/handshake-project
python3 --version          # 3.9 or newer
git --version
```

You need a GitHub account and a Render account (sign in to Render *with GitHub*,
so it can see your repositories).

---

## 1 · Prove it works locally, before anyone else sees it

```bash
./verify.sh
```

One command, about four minutes. It must end with all of:

```
== tests ==                58 passed
== recovery batch ==       recovered GMV 350018.8 | lift over control 0.6728
== readiness scan ==       readiness 84.3%, +Rs 123,605
== kill switch (R-11) ==   46 refusals
== audit chain ==          chain verified over 627 entries
== reproducibility ==      reproduced to the rupee: 350018.8
== credentials ==          .env ignored by git: yes — clean
```

`verify.sh` forces the offline backends on purpose: it is a *reproducibility*
check, and no hosted model returns bit-identical output twice. For a live-model
run use `./run.sh 500`, and `python3 preflight.py` to check the keys themselves.

Then look at the console once:

```bash
./run_ui.sh          # landing: http://127.0.0.1:8000
                     # console: http://127.0.0.1:8000/console
```

---

## 2 · Push to GitHub

```bash
cd ~/Desktop/handshake-project

python3 pre_push_check.py            # must print: clean
git add -A
git status --short | grep "\.env$" || echo "no .env staged — good"

git commit -m "Handshake v1.0: recovery and readiness for agent-driven checkout"
git branch -M main
```

Create the repository at **https://github.com/new**

* name: `handshake`
* visibility: **Public** (a reviewer must be able to open it)
* do **not** add a README, .gitignore or licence — the repo already has them

Then, with your own GitHub username in place of `YOURNAME`:

```bash
sed -i '' 's|USERNAME|YOURNAME|' README.md      # macOS; on Linux drop the ''
git add README.md && git commit -m "Fix CI badge"

git remote add origin https://github.com/YOURNAME/handshake.git
git push -u origin main
```

If the push asks for a password, use a **personal access token**, not your
account password: github.com → Settings → Developer settings → Personal access
tokens → Tokens (classic) → Generate, scope `repo`.

The Actions tab starts a run immediately. It installs on Python 3.9, 3.11 and
3.12, runs the 58 tests, runs a real batch and a real scan, and fails the build
if a credential is found in the tree. Wait for the green tick before you submit
the link — the badge in the README is what a reviewer glances at first.

**What is committed and what is not.** `.gitignore` excludes `.env`, `data/` and
every artefact in `runs/` *except* `runs/batch_canonical_*` and
`runs/readiness_canonical.json`. Those two are the evidence: the ledger, the
per-session records, the summary and the scan report from the run the README
quotes. A reviewer can re-verify the hash chain in them without running anything.

---

## 3 · Deploy on Render (no Docker, free tier)

`render.yaml` is already in the repo, so this is a Blueprint deploy — Render
reads the file and does not ask you to configure anything.

1. https://dashboard.render.com → **New** → **Blueprint**
2. Connect the `handshake` repository → **Apply**

Render then runs:

```
build:  pip install ".[console]"
start:  python -m uvicorn handshake.server.app:app --host 0.0.0.0 --port $PORT
health: /healthz
```

First build takes three to five minutes. The URL is
`https://handshake-console.onrender.com` (Render appends a suffix if the name is
taken — use whatever the dashboard shows).

The environment variables in `render.yaml` are deliberate:

| variable | value | why |
|---|---|---|
| `HS_PAYMENTS` | `sim` | no Razorpay keys on a public URL |
| `HS_BUYERS` | `heuristic` | no LLM quota burned by strangers |
| `HS_DEMO_MODE` | `1` | caps batch size and rate-limits `/api/run` |
| `HS_DB` | `/tmp/handshake.db` | free instances have no persistent disk |
| `PYTHON_VERSION` | `3.12.6` | pinned, so the build cannot drift |

**Free-tier facts, so nothing surprises you on demo day.** The instance sleeps
after 15 minutes idle and takes about a minute to wake. The filesystem is wiped
on every deploy — which is why the app re-imports the committed canonical run at
startup and re-verifies its chain, so a cold URL is never an empty console.
750 instance-hours a month is more than one service can use.

If a reviewer will open the link unattended, point a free uptime pinger
(uptimerobot.com) at `https://YOUR-URL/healthz` every 10 minutes so it is warm.

To gate the write endpoints, add `HS_API_TOKEN` in the Render dashboard →
Environment. Reads stay public; `/api/run`, `/api/readiness` and
`/api/killswitch` then require the `X-Handshake-Token` header.

---

## 4 · Test the deployment

```bash
URL=https://handshake-console.onrender.com

curl -s $URL/healthz | python3 -m json.tool
```

Expect `"ok": true`, a version, `"payments": "sim"`, and a `seed` block listing
an imported batch and scan with `"chain_valid": true`.

```bash
curl -s $URL/api/overview | python3 -m json.tool | head -40
```

Expect a non-zero `recovered` and a `readiness` score — proof the cold-start
import worked.

Then in a browser:

1. **Landing page** — read the problem, mechanism, measured results and limitations;
   then choose **Open the live console**
2. **Recovery** → *Run batch* (200 sessions) → watch the three headline outcomes
   and live sessions; expand **Advanced evidence** for causes and refusals
3. Click any failed session → the drawer shows the merchant-observable API trace,
   the diagnosis, the policy verdict and the audit-chain entries for that session
4. **Prevention** → *Scan catalogue* → the before/after proof and revenue delta
5. Flip the **kill switch** mid-batch → R-11 refusals appear, the money stops
6. **History** → open the stored run → the chain re-verifies out of SQLite

If step 2 returns HTTP 409, a run is already in flight — that guard is intended.
If it returns 429, `HS_DEMO_MODE` is rate-limiting; wait the stated gap.

---

## 5 · Changing things after deployment

Yes. `autoDeployTrigger: commit` is set, so:

```bash
git add -A && git commit -m "..." && git push
```

Render rebuilds and redeploys on its own, in three to five minutes, with a
zero-downtime swap. Run `./verify.sh` before every push — CI will catch a
regression, but only after the push is public.

Roll back from the Render dashboard → Deploys → *Rollback to this deploy*.

---

## 6 · Freeze the submission

```bash
git tag -a v1.0-submission -m "Razorpay AI Buildathon submission"
git push origin v1.0-submission
```

Submit three links: the repository, the tag, and the live URL. Record the video
against the live URL, not localhost — see `DEMO.md` for the five-minute script.

---

## Troubleshooting

| symptom | cause | fix |
|---|---|---|
| build fails, `no module named handshake` | Render built from a subdirectory | root directory must be blank in the service settings |
| `ModuleNotFoundError: fastapi` | the `console` extra was skipped | build command must be `pip install ".[console]"` |
| console loads but is empty | canonical artefacts not committed | `git ls-files runs/` must list five `batch_canonical_*` files and `readiness_canonical.json` |
| first request takes 60 s | free instance was asleep | expected; ping `/healthz` to pre-warm |
| CI red on 3.9 only | a newer-syntax annotation crept in | the tree is 3.9-clean today; check the diff |
| `/api/run` returns 401 | `HS_API_TOKEN` is set | send `X-Handshake-Token`, or unset it |
| figures differ from the README | live backends are on | the README figures are `HS_PAYMENTS=sim`, `HS_BUYERS=heuristic`, seed 20260830 |
