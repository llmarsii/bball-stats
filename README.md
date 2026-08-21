# Pickup Basketball Stat Tracker

A small Streamlit app for a seven-person pickup group. Everyone can open the shared page, enter the group password, choose the playing date, upload a headshot, save W/L plus box-score stats for each game, and view nightly totals plus leaderboards.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

On Windows, you can also double-click `start.bat`. It starts the app on:

```text
http://localhost:8765
```

That avoids Streamlit's default `8501` port, which is commonly used by other local dashboards.

## Background images

Use the `Backgrounds` tab in the app to upload three optional images:

- Neutral background
- Winning-night background
- Losing-night background

The app chooses the winning or losing background from the selected night's total W/L count. If the night is tied or no stats have been entered, it uses the neutral background.

## Deploy free on Streamlit Community Cloud

Streamlit Community Cloud currently describes app hosting as free and deploys directly from GitHub. To publish this so everyone can use it from their phones:

1. Create a GitHub repo for this project.
2. Push these files to GitHub.
3. Go to `https://share.streamlit.io`.
4. Sign in with GitHub.
5. Click `Create app`.
6. Choose the GitHub repo, branch, and `app.py` as the app file.
7. Add a persistent database before sharing the app for real stat entry.
8. Deploy the app and share the generated `*.streamlit.app` URL with the group.

## Simple hosted storage with GitHub

The simplest no-new-account option is to let the app back up its SQLite database to this GitHub repo. The app stores the backup on a separate `data` branch so stat saves do not trigger normal Streamlit redeploys from `main`.

In Streamlit app secrets, add:

```toml
GITHUB_TOKEN = "YOUR_GITHUB_FINE_GRAINED_TOKEN"
GITHUB_REPO = "llmarsii/bball-stats"
GITHUB_DATA_BRANCH = "data"
GITHUB_DB_PATH = "basketball_stats.sqlite3"
```

The token needs Contents read/write access for this repository. On startup, the app restores `basketball_stats.sqlite3` from the `data` branch if the local database is empty. After each stat, roster, photo, or background change, it uploads the updated SQLite file back to GitHub.

This is intentionally simple and free. It is good for a small group entering stats one at a time. It is not a high-concurrency database.

## Optional database storage

If you later want a real hosted database, create a small hosted Postgres database with a provider such as Supabase or Neon, then add this secret in the Streamlit app settings:

```toml
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:PORT/DATABASE?sslmode=require"
```

When `DATABASE_URL` is configured, the app uses Postgres directly and does not use GitHub SQLite backup.

## Data storage note

Stats, profile photos, and background images are stored in:

- Postgres, when `DATABASE_URL` is configured.
- Local SQLite at `data/basketball_stats.sqlite3`, backed up to GitHub when `GITHUB_TOKEN` is configured.
- Local SQLite only, when neither `DATABASE_URL` nor `GITHUB_TOKEN` is configured.

Do not rely on local SQLite alone for production hosted data.
