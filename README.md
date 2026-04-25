# MailRocketAI

A small pipeline that scrapes LinkedIn job posts, scores them against your
resume with an LLM, drafts a tailored application email, and sends it via
the Gmail API.

The system is intentionally a single sequential Python pipeline. There is
no Celery, no Redis, and no Docker. The architecture is organised so any of
those can be added later without touching business logic.

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for environment and
dependency management. If you don't have it yet:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

1. Install dependencies (creates `.venv/` and pins from `uv.lock`):

   ```
   make sync          # or: uv sync
   ```

   uv will read `.python-version` and provision the matching interpreter
   automatically if needed.

2. Create your config files from the templates:

   ```
   cp config/config.example.yaml   config/config.yaml
   cp config/secrets.example.yaml  config/secrets.yaml
   ```

   Edit both. `config.yaml` holds plain text (URLs, phone, email defaults,
   filter thresholds, model list). `secrets.yaml` holds your LinkedIn
   credentials, LLM provider API keys, and Gmail OAuth file paths. Both
   files are gitignored.

   All API keys go in `config/secrets.yaml`. You only need keys for the
   LLM providers you actually want to use — the model rotation in
   `config.yaml -> llm.models` automatically skips providers whose key is
   empty. **Gemini + Groq is enough to get started**; the rest are
   optional fallbacks with their own free tiers.

   | Key in `config/secrets.yaml`     | Where to get it                                                                       | Notes                                  |
   | -------------------------------- | ------------------------------------------------------------------------------------- | -------------------------------------- |
   | `linkedin.username` / `password` | Your LinkedIn login                                                                   | required for `scrape`                  |
   | `gemini_api_key`                 | [Google AI Studio](https://aistudio.google.com/app/apikey)                            | recommended primary                    |
   | `groq_api_key`                   | [Groq Console](https://console.groq.com/keys)                                         | recommended fallback, very fast        |
   | `cerebras_api_key`               | [Cerebras Cloud](https://cloud.cerebras.ai)                                           | optional, ~14.4K req/day free          |
   | `mistral_api_key`                | [Mistral La Plateforme](https://console.mistral.ai/api-keys)                          | optional, ~1B tokens/month free        |
   | `openrouter_api_key`             | [OpenRouter](https://openrouter.ai/keys)                                              | optional, mixed free models            |
   | `github_token`                   | [GitHub PAT](https://github.com/settings/tokens) with `models:read` scope             | optional, unlocks gpt-4o / o3-mini     |
   | `gmail.client_secret_path`       | Google Cloud Console — see step 4 below for the full flow                             | required for `send`                    |

   Any of these can also be supplied via an env var named
   `MAILROCKET_SECRET_<UPPER_KEY>` (e.g.
   `MAILROCKET_SECRET_GEMINI_API_KEY=...`) instead of editing the file —
   see [Configuration overrides](#configuration-overrides) below.

3. Drop your resume in `data/`:

   ```
   cp data/resume.example.txt data/resume.txt   # then edit
   cp /path/to/your-cv.pdf    data/resume.pdf   # optional, attached to outgoing mail
   ```

4. For Gmail, create an OAuth client and download its JSON:

   1. Open the [Google Cloud Console](https://console.cloud.google.com/)
      and create a new project if you don't already have one.
   2. Go to `APIs & Services -> Credentials -> OAuth 2.0 Client IDs` and
      start creating a new client.
   3. Choose **Desktop app** as the application type, give it any name,
      and click Create.
   4. Click **Download JSON** and save it at `data/gmail/client_secret.json`
      (the expected shape is shown in `data/gmail/client_secret.example.json`).

   The first run that sends mail will open a browser for consent and
   produce `data/gmail/token.json`.

5. Initialise the database:

   ```
   make init-db
   ```

## How it works

```
scrape  ->  linkedin_posts (analysed=0)
analyze ->  post_analysis  (mail_sent=-1) + analysed=1
send    ->  Gmail; mail_sent set to 1 (sent) or 0 (rejected)
```

Each stage reads its inputs from SQLite and writes its outputs to SQLite.
That makes every stage independently runnable and resumable, which is also
the seam where Celery would attach later if needed.

The CLI exposes them separately so you can:
- Run `make pipeline` (scrape + analyze) during the day, accumulating drafts.
- Eyeball the DB whenever you want.
- Run `make send` at start of the day for visibility before any mail goes
  out.

## Project layout

```
MailRocketAI/
├── Makefile
├── README.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── config/
│   ├── config.example.yaml      # committed defaults & plain-text inputs
│   ├── secrets.example.yaml     # committed template for keys/passwords
│   └── search_queries.yaml      # the search definitions
├── prompts/                     # LLM prompts
│   ├── resume_analysis.txt
│   ├── email_tailoring.txt
│   └── output_schema.json
├── data/                        # gitignored runtime state
│   ├── linkedin_posts.db
│   ├── cookies.pkl
│   ├── resume.txt / resume.pdf  # you provide
│   └── gmail/{client_secret,token}.json
├── mailrocket/                  # the package
│   ├── cli.py
│   ├── pipeline.py
│   ├── settings.py
│   ├── logging_setup.py
│   ├── scraper/  analyzer/  mailer/  storage/
└── scripts/
    └── db_admin.py              # one-off DB ops
```

## Daily flow

During the day:

```
make pipeline      # scrape + analyze; nothing is mailed
```

In the morning, to review and send:

```
make dry-send      # see exactly what would go out
make send          # actually send pending mails
```

Or run everything in one shot:

```
make run
```

## Review UI

A small FastAPI app for inspecting captured posts and tweaking the
LLM-generated drafts before they go out:

```
make ui                              # http://127.0.0.1:8765
```

The layout is three panes: a filterable post list on the left, the
read-only post detail in the middle (with a one-click "Open on LinkedIn"
deep-link), and the editable analysis on the right (subject, body,
contacts, match %, mail status, ...). Cmd/Ctrl-S saves the current
analysis.

## CLI subcommands

The `mailrocket` console script is installed by `uv sync`, so prefix any
of these with `uv run`:

```
uv run mailrocket init-db            # create schema
uv run mailrocket scrape             # only scrape
uv run mailrocket analyze            # only analyze pending posts
uv run mailrocket send [--dry-run]
uv run mailrocket pipeline           # scrape + analyze
uv run mailrocket run-all            # scrape + analyze + send
uv run mailrocket ui                 # web review UI
```

`uv run python -m mailrocket <cmd>` still works if you prefer that form.

Common flag: `--log-level DEBUG`.

## Managing dependencies

```
uv add <pkg>                         # add a new runtime dependency
uv add --group dev <pkg>             # add a dev-only dependency
uv remove <pkg>                      # drop a dependency
uv lock                              # re-resolve uv.lock
uv sync                              # apply uv.lock to .venv
```

## Configuration overrides

Anything in `config/config.yaml` can be overridden by an env var named
`MAILROCKET_<KEY>` (e.g. `MAILROCKET_HEADLESS=0`, `MAILROCKET_MATCH_THRESHOLD=72`).
Secrets use `MAILROCKET_SECRET_<KEY>`.

## DB administration

One-off operations live in `scripts/db_admin.py`:

```
uv run python scripts/db_admin.py raw "SELECT count(*) FROM linkedin_posts;"
uv run python scripts/db_admin.py count-by-date
uv run python scripts/db_admin.py mark-sent --from urls.txt
uv run python scripts/db_admin.py remove --no-backup
uv run python scripts/db_admin.py migrate
```
