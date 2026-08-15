# Pickup Basketball Stat Tracker

A small Streamlit app for a seven-person pickup group. Everyone can open the shared page, enter the group password, choose the playing date, upload a headshot, save W/L plus box-score stats, and view leaderboards.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The local default password is `hoops`.

On Windows, you can also double-click `start.bat`. It starts the app on:

```text
http://localhost:8765
```

That avoids Streamlit's default `8501` port, which is commonly used by other local dashboards.

## Deploy free on Streamlit Community Cloud

Streamlit Community Cloud currently describes app hosting as free and deploys directly from GitHub. To publish this so everyone can use it from their phones:

1. Create a GitHub repo for this project.
2. Push these files to GitHub.
3. Go to `https://share.streamlit.io`.
4. Sign in with GitHub.
5. Click `Create app`.
6. Choose the GitHub repo, branch, and `app.py` as the app file.
7. In `Advanced settings`, add the password secret shown below.
8. Deploy the app and share the generated `*.streamlit.app` URL with the group.

Before sharing it with friends, set a secret named `APP_PASSWORD` in Streamlit Community Cloud:

```toml
APP_PASSWORD = "choose-a-real-group-password"
```

## Data storage note

Stats and profile photos are stored in a local SQLite database at `data/basketball_stats.sqlite3`. This is intentionally lightweight and fine for a small group, but hosted filesystem persistence can be less durable than a real database. If you want stronger long-term persistence later, the app can be moved to a free hosted backend such as Supabase or Google Sheets.
