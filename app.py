from __future__ import annotations

import base64
import ast
import hashlib
import html
import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import streamlit as st

try:
    import psycopg2
    from psycopg2.extras import DictCursor
except ImportError:  # Local SQLite mode does not require Postgres dependencies.
    psycopg2 = None
    DictCursor = None


APP_TITLE = "Pickup Stat Tracker"
DB_PATH = Path("data") / "basketball_stats.sqlite3"
DATABASE_URL_ENV = "DATABASE_URL"
GITHUB_TOKEN_ENV = "GITHUB_TOKEN"
GITHUB_REPO_ENV = "GITHUB_REPO"
GITHUB_DATA_BRANCH_ENV = "GITHUB_DATA_BRANCH"
GITHUB_DB_PATH_ENV = "GITHUB_DB_PATH"
DEFAULT_GITHUB_REPO = "llmarsii/bball-stats"
DEFAULT_GITHUB_DATA_BRANCH = "data"
DEFAULT_GITHUB_DB_PATH = "basketball_stats.sqlite3"
APP_TIME_ZONE_NAME = os.getenv("APP_TIME_ZONE", "America/Los_Angeles")
try:
    APP_TIME_ZONE = ZoneInfo(APP_TIME_ZONE_NAME)
except ZoneInfoNotFoundError:
    APP_TIME_ZONE = None
DEFAULT_PLAYERS = [
    "Player 1",
    "Player 2",
    "Player 3",
    "Player 4",
    "Player 5",
    "Player 6",
    "Player 7",
]
STAT_FIELDS = {
    "points": "PTS",
    "field_goals_made": "FGM",
    "field_goals_attempted": "FGA",
    "rebounds": "REB",
    "assists": "AST",
    "steals": "STL",
    "blocks": "BLK",
    "threes": "3PM",
    "three_attempts": "3PA",
    "turnovers": "TO",
}
BULK_STAT_COLUMNS = [
    ("PTS", "points"),
    ("FGM", "field_goals_made"),
    ("FGA", "field_goals_attempted"),
    ("3PM", "threes"),
    ("3PA", "three_attempts"),
    ("REB", "rebounds"),
    ("AST", "assists"),
    ("STL", "steals"),
    ("BLK", "blocks"),
    ("TO", "turnovers"),
]
SUMMARY_COLUMNS = {
    "name": "Player",
    "result": "W/L",
    "points": "PTS",
    "field_goals_made": "FGM",
    "field_goals_attempted": "FGA",
    "fg_pct": "FG%",
    "threes": "3PM",
    "three_attempts": "3PA",
    "three_pct": "3P%",
    "rebounds": "REB",
    "assists": "AST",
    "steals": "STL",
    "blocks": "BLK",
    "turnovers": "TO",
    "notes": "Notes",
}
GAME_LOG_COLUMNS = {
    "game_number": "Game",
    **SUMMARY_COLUMNS,
}
NIGHTLY_TOTAL_COLUMNS = {
    "name": "Player",
    "games": "Games",
    "wins": "W",
    "losses": "L",
    "record": "W-L",
    "win_pct": "WIN%",
    "points": "PTS",
    "field_goals_made": "FGM",
    "field_goals_attempted": "FGA",
    "threes": "3PM",
    "three_attempts": "3PA",
    "rebounds": "REB",
    "assists": "AST",
    "steals": "STL",
    "blocks": "BLK",
    "turnovers": "TO",
}
PLAYER_NIGHT_COLUMNS = {
    "game_date": "Date",
    **NIGHTLY_TOTAL_COLUMNS,
}
BACKGROUND_KEYS = {
    "neutral": "Neutral background",
    "winning": "Winning-night background",
    "losing": "Losing-night background",
}
MAX_BACKGROUND_IMAGE_BYTES = 5 * 1024 * 1024
PLAYER_COLORS = [
    "#ef4444",
    "#3b82f6",
    "#22c55e",
    "#f59e0b",
    "#a855f7",
    "#06b6d4",
    "#f97316",
]
PERCENT_COLUMNS = {"FG%", "3P%", "WIN%"}
AVERAGE_COLUMNS = {"PPG", "RPG", "APG", "SPG", "BPG", "TPG", "FGM/G", "FGA/G", "3PM/G", "3PA/G"}
WEEKDAY_ABBREVIATIONS = ["M", "Tu", "W", "Th", "F", "Sa", "Su"]
TOTAL_LEADERBOARD_COLUMNS = [
    "name",
    "GP",
    "Nights",
    "W",
    "L",
    "PTS",
    "FGM",
    "FGA",
    "REB",
    "AST",
    "STL",
    "BLK",
    "THREE_PM",
    "THREE_PA",
    "TO",
    "WIN%",
]
AVERAGE_LEADERBOARD_COLUMNS = [
    "name",
    "GP",
    "Nights",
    "W",
    "L",
    "WIN%",
    "PPG",
    "FG%",
    "3P%",
    "RPG",
    "APG",
    "SPG",
    "BPG",
    "TPG",
    "FGM/G",
    "FGA/G",
    "3PM/G",
    "3PA/G",
]
CUSTOM_STAT_FIELDS = [
    "GP",
    "Nights",
    "W",
    "L",
    "PTS",
    "FGM",
    "FGA",
    "REB",
    "AST",
    "STL",
    "BLK",
    "THREE_PM",
    "THREE_PA",
    "TO",
    "WIN_PCT",
    "FG_PCT",
    "THREE_PCT",
    "PPG",
    "RPG",
    "APG",
]
CUSTOM_STAT_OPERATORS = ["+", "-", "*", "/", "(", ")", "**"]


st.set_page_config(
    page_title=APP_TITLE,
    page_icon=":basketball:",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def configured_value(name: str, default: str = "") -> str:
    env_value = os.environ.get(name)
    if env_value:
        return env_value
    try:
        return str(st.secrets.get(name, default) or default)
    except Exception:
        return default


def configured_database_url() -> str:
    return configured_value(DATABASE_URL_ENV)


DATABASE_URL = configured_database_url()


def using_postgres() -> bool:
    return bool(DATABASE_URL)


def github_storage_config() -> dict:
    return {
        "token": configured_value(GITHUB_TOKEN_ENV),
        "repo": configured_value(GITHUB_REPO_ENV, DEFAULT_GITHUB_REPO),
        "branch": configured_value(GITHUB_DATA_BRANCH_ENV, DEFAULT_GITHUB_DATA_BRANCH),
        "path": configured_value(GITHUB_DB_PATH_ENV, DEFAULT_GITHUB_DB_PATH),
    }


def using_github_storage() -> bool:
    config = github_storage_config()
    return not using_postgres() and bool(config["token"] and config["repo"])


def to_postgres_sql(sql: str) -> str:
    return sql.replace("?", "%s")


class PostgresConnection:
    def __init__(self, database_url: str):
        if psycopg2 is None or DictCursor is None:
            raise RuntimeError(
                "DATABASE_URL is configured, but psycopg2-binary is not installed."
            )
        self.conn = psycopg2.connect(database_url)

    def __enter__(self) -> "PostgresConnection":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()

    def execute(self, sql: str, params: tuple = ()):
        cursor = self.conn.cursor(cursor_factory=DictCursor)
        cursor.execute(to_postgres_sql(sql), params)
        return cursor

    def executemany(self, sql: str, param_list: list[tuple]) -> None:
        cursor = self.conn.cursor(cursor_factory=DictCursor)
        cursor.executemany(to_postgres_sql(sql), param_list)


def db() -> sqlite3.Connection:
    if using_postgres():
        return PostgresConnection(DATABASE_URL)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_row(row) -> dict:
    data = dict(row)
    for key, value in data.items():
        if isinstance(value, memoryview):
            data[key] = value.tobytes()
    return data


def github_api_request(
    method: str,
    path: str,
    payload: dict | None = None,
    allow_missing: bool = False,
) -> dict | None:
    config = github_storage_config()
    url = f"https://api.github.com/repos/{config['repo']}{path}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {config['token']}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        if allow_missing and exc.code == 404:
            return None
        raise RuntimeError(f"GitHub API returned HTTP {exc.code} for {path}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach GitHub API: {exc.reason}") from exc
    return json.loads(body.decode("utf-8")) if body else {}


def github_content_sha() -> str | None:
    config = github_storage_config()
    encoded_path = "/".join(
        urllib.parse.quote(part)
        for part in config["path"].strip("/").split("/")
    )
    result = github_api_request(
        "GET",
        f"/contents/{encoded_path}?ref={urllib.parse.quote(config['branch'])}",
        allow_missing=True,
    )
    return result.get("sha") if result else None


def ensure_github_data_branch() -> None:
    config = github_storage_config()
    branch = urllib.parse.quote(config["branch"], safe="")
    if github_api_request("GET", f"/git/ref/heads/{branch}", allow_missing=True):
        return
    source_ref = github_api_request("GET", "/git/ref/heads/main")
    github_api_request(
        "POST",
        "/git/refs",
        {
            "ref": f"refs/heads/{config['branch']}",
            "sha": source_ref["object"]["sha"],
        },
    )


def download_db_from_github() -> bool:
    if not using_github_storage():
        return False
    config = github_storage_config()
    encoded_path = "/".join(
        urllib.parse.quote(part)
        for part in config["path"].strip("/").split("/")
    )
    result = github_api_request(
        "GET",
        f"/contents/{encoded_path}?ref={urllib.parse.quote(config['branch'])}",
        allow_missing=True,
    )
    if not result:
        return False
    content = result.get("content")
    if not content and result.get("sha"):
        blob = github_api_request("GET", f"/git/blobs/{result['sha']}")
        content = blob.get("content") if blob else None
    if not content:
        return False
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.write_bytes(base64.b64decode(content))
    return True


def upload_db_to_github() -> bool:
    if not using_github_storage() or not DB_PATH.exists():
        return False
    config = github_storage_config()
    ensure_github_data_branch()
    encoded_path = "/".join(
        urllib.parse.quote(part)
        for part in config["path"].strip("/").split("/")
    )
    payload = {
        "message": f"Update basketball stats backup {datetime.utcnow().isoformat()}",
        "content": base64.b64encode(DB_PATH.read_bytes()).decode("ascii"),
        "branch": config["branch"],
    }
    sha = github_content_sha()
    if sha:
        payload["sha"] = sha
    github_api_request("PUT", f"/contents/{encoded_path}", payload)
    return True


def local_db_has_user_data() -> bool:
    if not DB_PATH.exists():
        return False
    try:
        conn = sqlite3.connect(DB_PATH)
        game_count = conn.execute("SELECT COUNT(*) FROM game_stats").fetchone()[0]
        table_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        asset_count = (
            conn.execute("SELECT COUNT(*) FROM app_assets").fetchone()[0]
            if "app_assets" in table_names
            else 0
        )
        background_count = (
            conn.execute("SELECT COUNT(*) FROM background_images").fetchone()[0]
            if "background_images" in table_names
            else 0
        )
        photo_count = conn.execute(
            "SELECT COUNT(*) FROM players WHERE photo_blob IS NOT NULL"
        ).fetchone()[0]
        player_names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM players ORDER BY sort_order, id"
            ).fetchall()
        ]
        conn.close()
    except sqlite3.Error:
        return False
    return bool(
        game_count
        or asset_count
        or background_count
        or photo_count
        or player_names != DEFAULT_PLAYERS
    )


def restore_db_from_github_if_needed() -> None:
    if using_postgres() or local_db_has_user_data():
        return
    try:
        download_db_from_github()
    except RuntimeError as exc:
        st.session_state.github_storage_error = str(exc)


def backup_db_to_github_if_configured() -> None:
    if using_postgres():
        return
    try:
        if upload_db_to_github():
            st.session_state.github_storage_error = ""
    except RuntimeError as exc:
        st.session_state.github_storage_error = str(exc)


def table_columns(conn, table_name: str) -> dict:
    if using_postgres():
        rows = conn.execute(
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ?
            """,
            (table_name,),
        ).fetchall()
        return {row["name"]: row for row in rows}
    return {
        row["name"]: row
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def create_game_stats_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS game_stats (
            game_date TEXT NOT NULL,
            game_number INTEGER NOT NULL DEFAULT 1,
            player_id INTEGER NOT NULL REFERENCES players(id),
            result TEXT NOT NULL DEFAULT '',
            points INTEGER NOT NULL DEFAULT 0,
            field_goals_made INTEGER NOT NULL DEFAULT 0,
            field_goals_attempted INTEGER NOT NULL DEFAULT 0,
            rebounds INTEGER NOT NULL DEFAULT 0,
            assists INTEGER NOT NULL DEFAULT 0,
            steals INTEGER NOT NULL DEFAULT 0,
            blocks INTEGER NOT NULL DEFAULT 0,
            threes INTEGER NOT NULL DEFAULT 0,
            three_attempts INTEGER NOT NULL DEFAULT 0,
            turnovers INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (game_date, game_number, player_id)
        )
        """
    )


def create_app_assets_table(conn: sqlite3.Connection) -> None:
    blob_type = "BYTEA" if using_postgres() else "BLOB"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS app_assets (
            asset_key TEXT PRIMARY KEY,
            image_blob {blob_type} NOT NULL,
            image_mime TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def create_background_images_table(conn: sqlite3.Connection) -> None:
    id_type = "SERIAL PRIMARY KEY" if using_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"
    blob_type = "BYTEA" if using_postgres() else "BLOB"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS background_images (
            id {id_type},
            asset_key TEXT NOT NULL,
            image_blob {blob_type} NOT NULL,
            image_mime TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS background_picks (
            game_date TEXT NOT NULL,
            asset_key TEXT NOT NULL,
            background_image_id INTEGER NOT NULL,
            selected_at TEXT NOT NULL,
            PRIMARY KEY (game_date, asset_key)
        )
        """
    )


def create_game_nights_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS game_nights (
            game_date TEXT PRIMARY KEY,
            location_name TEXT NOT NULL DEFAULT '',
            maps_url TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )


def create_custom_stats_table(conn: sqlite3.Connection) -> None:
    id_type = "SERIAL PRIMARY KEY" if using_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS custom_stats (
            id {id_type},
            name TEXT NOT NULL,
            formula TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def migrate_legacy_background_assets(conn) -> None:
    for asset_key in BACKGROUND_KEYS:
        existing_count = conn.execute(
            "SELECT COUNT(*) FROM background_images WHERE asset_key = ?",
            (asset_key,),
        ).fetchone()[0]
        if existing_count:
            continue
        row = conn.execute(
            """
            SELECT image_blob, image_mime, updated_at
            FROM app_assets
            WHERE asset_key = ?
            """,
            (asset_key,),
        ).fetchone()
        if not row:
            continue
        conn.execute(
            """
            INSERT INTO background_images (asset_key, image_blob, image_mime, uploaded_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                asset_key,
                row["image_blob"],
                row["image_mime"],
                row["updated_at"],
            ),
        )


def dedupe_background_images(conn) -> int:
    rows = conn.execute(
        """
        SELECT id, asset_key, image_blob
        FROM background_images
        ORDER BY asset_key, uploaded_at, id
        """
    ).fetchall()
    seen: dict[tuple[str, str], int] = {}
    duplicate_ids = []
    for row in rows:
        data = normalize_row(row)
        fingerprint = image_fingerprint(data["image_blob"])
        key = (data["asset_key"], fingerprint)
        if key in seen:
            duplicate_ids.append(data["id"])
        else:
            seen[key] = data["id"]

    for image_id in duplicate_ids:
        conn.execute("DELETE FROM background_picks WHERE background_image_id = ?", (image_id,))
        conn.execute("DELETE FROM background_images WHERE id = ?", (image_id,))
    return len(duplicate_ids)


def ensure_game_stats_schema(conn: sqlite3.Connection) -> None:
    columns = table_columns(conn, "game_stats")
    migrations = {
        "field_goals_made": "INTEGER NOT NULL DEFAULT 0",
        "field_goals_attempted": "INTEGER NOT NULL DEFAULT 0",
        "three_attempts": "INTEGER NOT NULL DEFAULT 0",
    }
    for column, definition in migrations.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE game_stats ADD COLUMN {column} {definition}")

    columns = table_columns(conn, "game_stats")
    if "game_number" in columns:
        return

    now = datetime.utcnow().isoformat()
    conn.execute("ALTER TABLE game_stats RENAME TO game_stats_old")
    create_game_stats_table(conn)
    conn.execute(
        """
        INSERT INTO game_stats (
            game_date, game_number, player_id, result, points, field_goals_made,
            field_goals_attempted, rebounds, assists, steals, blocks, threes,
            three_attempts, turnovers, notes, updated_at
        )
        SELECT
            game_date,
            1 AS game_number,
            player_id,
            result,
            points,
            field_goals_made,
            field_goals_attempted,
            rebounds,
            assists,
            steals,
            blocks,
            threes,
            three_attempts,
            turnovers,
            notes,
            COALESCE(updated_at, ?)
        FROM game_stats_old
        """,
        (now,),
    )
    conn.execute("DROP TABLE game_stats_old")


def init_db() -> None:
    restore_db_from_github_if_needed()
    id_type = "SERIAL PRIMARY KEY" if using_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"
    blob_type = "BYTEA" if using_postgres() else "BLOB"
    duplicate_background_count = 0
    with db() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS players (
                id {id_type},
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                photo_blob {blob_type},
                photo_mime TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        create_game_stats_table(conn)
        create_app_assets_table(conn)
        create_background_images_table(conn)
        create_game_nights_table(conn)
        create_custom_stats_table(conn)
        migrate_legacy_background_assets(conn)
        duplicate_background_count = dedupe_background_images(conn)
        ensure_game_stats_schema(conn)
        player_count = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        if player_count == 0:
            now = datetime.utcnow().isoformat()
            conn.executemany(
                """
                INSERT INTO players (name, sort_order, updated_at)
                VALUES (?, ?, ?)
                """,
                [(name, index, now) for index, name in enumerate(DEFAULT_PLAYERS)],
            )
    if duplicate_background_count:
        backup_db_to_github_if_configured()


@st.cache_data(ttl=2)
def get_players() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, name, sort_order, photo_blob, photo_mime
            FROM players
            ORDER BY sort_order, id
            """
        ).fetchall()
    return [normalize_row(row) for row in rows]


def update_player_name(player_id: int, name: str) -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE players
            SET name = ?, updated_at = ?
            WHERE id = ?
            """,
            (name.strip() or "Unnamed Player", datetime.utcnow().isoformat(), player_id),
        )
    get_players.clear()
    all_stats.clear()
    backup_db_to_github_if_configured()


def update_player_photo(player_id: int, image_bytes: bytes, mime_type: str) -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE players
            SET photo_blob = ?, photo_mime = ?, updated_at = ?
            WHERE id = ?
            """,
            (image_bytes, mime_type, datetime.utcnow().isoformat(), player_id),
        )
    get_players.clear()
    backup_db_to_github_if_configured()


def remove_player_photo(player_id: int) -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE players
            SET photo_blob = NULL, photo_mime = NULL, updated_at = ?
            WHERE id = ?
            """,
            (datetime.utcnow().isoformat(), player_id),
        )
    get_players.clear()
    backup_db_to_github_if_configured()


def google_maps_search_url(location_name: str) -> str:
    query = urllib.parse.quote_plus(location_name.strip())
    return f"https://www.google.com/maps/search/?api=1&query={query}" if query else ""


def game_night_metadata(game_date: date) -> dict:
    with db() as conn:
        row = conn.execute(
            """
            SELECT game_date, location_name, maps_url, updated_at
            FROM game_nights
            WHERE game_date = ?
            """,
            (game_date.isoformat(),),
        ).fetchone()
    return normalize_row(row) if row else {"location_name": "", "maps_url": ""}


def saved_locations() -> list[str]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT location_name
            FROM game_nights
            WHERE location_name <> ''
            ORDER BY location_name
            """
        ).fetchall()
    return [row["location_name"] for row in rows]


def save_game_night_location(game_date: date, location_name: str) -> None:
    clean_location = location_name.strip()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO game_nights (game_date, location_name, maps_url, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(game_date) DO UPDATE SET
                location_name = excluded.location_name,
                maps_url = excluded.maps_url,
                updated_at = excluded.updated_at
            """,
            (
                game_date.isoformat(),
                clean_location,
                google_maps_search_url(clean_location),
                datetime.utcnow().isoformat(),
            ),
        )
    backup_db_to_github_if_configured()


def remove_game_night_location(game_date: date) -> None:
    save_game_night_location(game_date, "")


def get_custom_stats() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, name, formula, description, created_at, updated_at
            FROM custom_stats
            ORDER BY created_at, id
            """
        ).fetchall()
    return [normalize_row(row) for row in rows]


def add_custom_stat(name: str, formula: str, description: str) -> None:
    now = datetime.utcnow().isoformat()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO custom_stats (name, formula, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name.strip(), formula.strip(), description.strip(), now, now),
        )
    backup_db_to_github_if_configured()


def delete_custom_stat(custom_stat_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM custom_stats WHERE id = ?", (custom_stat_id,))
    backup_db_to_github_if_configured()


@st.cache_data(ttl=2)
def get_background_assets(asset_key: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, asset_key, image_blob, image_mime, uploaded_at
            FROM background_images
            WHERE asset_key = ?
            ORDER BY uploaded_at, id
            """,
            (asset_key,),
        ).fetchall()
    return [normalize_row(row) for row in rows]


def add_background_asset(asset_key: str, image_bytes: bytes, mime_type: str) -> bool:
    new_fingerprint = image_fingerprint(image_bytes)
    with db() as conn:
        existing_rows = conn.execute(
            """
            SELECT image_blob
            FROM background_images
            WHERE asset_key = ?
            """,
            (asset_key,),
        ).fetchall()
        for row in existing_rows:
            data = normalize_row(row)
            if image_fingerprint(data["image_blob"]) == new_fingerprint:
                return False
        conn.execute(
            """
            INSERT INTO background_images (asset_key, image_blob, image_mime, uploaded_at)
            VALUES (?, ?, ?, ?)
            """,
            (asset_key, image_bytes, mime_type, datetime.utcnow().isoformat()),
        )
    get_background_assets.clear()
    backup_db_to_github_if_configured()
    return True


def remove_background_asset(image_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM background_picks WHERE background_image_id = ?", (image_id,))
        conn.execute("DELETE FROM background_images WHERE id = ?", (image_id,))
    get_background_assets.clear()
    backup_db_to_github_if_configured()


def asset_to_data_url(asset: dict) -> str:
    encoded = base64.b64encode(asset["image_blob"]).decode("ascii")
    return f"data:{asset['image_mime']};base64,{encoded}"


def image_fingerprint(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def deterministic_background_choice(assets: list[dict], asset_key: str, game_date: date) -> dict:
    digest = hashlib.sha256(f"{game_date.isoformat()}:{asset_key}".encode("utf-8")).hexdigest()
    return assets[int(digest, 16) % len(assets)]


def selected_background_asset(asset_key: str, game_date: date) -> dict | None:
    assets = get_background_assets(asset_key)
    if not assets and asset_key != "neutral":
        assets = get_background_assets("neutral")
        asset_key = "neutral"
    if not assets:
        return None

    assets_by_id = {asset["id"]: asset for asset in assets}
    with db() as conn:
        row = conn.execute(
            """
            SELECT background_image_id
            FROM background_picks
            WHERE game_date = ?
              AND asset_key = ?
            """,
            (game_date.isoformat(), asset_key),
        ).fetchone()
        if row and row["background_image_id"] in assets_by_id:
            return assets_by_id[row["background_image_id"]]

        chosen = deterministic_background_choice(assets, asset_key, game_date)
        conn.execute(
            """
            INSERT INTO background_picks (game_date, asset_key, background_image_id, selected_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(game_date, asset_key) DO UPDATE SET
                background_image_id = excluded.background_image_id,
                selected_at = excluded.selected_at
            """,
            (
                game_date.isoformat(),
                asset_key,
                chosen["id"],
                datetime.utcnow().isoformat(),
            ),
        )
    backup_db_to_github_if_configured()
    return chosen


def background_data_url(asset_key: str, game_date: date) -> str:
    asset = selected_background_asset(asset_key, game_date)
    return asset_to_data_url(asset) if asset else ""


def stats_for_date(game_date: date) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM game_stats
            WHERE game_date = ?
            ORDER BY game_number, player_id
            """,
            (game_date.isoformat(),),
        ).fetchall()
    return [normalize_row(row) for row in rows]


def stats_by_game(game_date: date, player_id: int) -> dict[int, dict]:
    return {
        row["game_number"]: row
        for row in stats_for_date(game_date)
        if row["player_id"] == player_id
    }


def stats_for_game(game_date: date, game_number: int) -> dict[int, dict]:
    return {
        row["player_id"]: row
        for row in stats_for_date(game_date)
        if row["game_number"] == game_number
    }


def game_counts_for_date(game_date: date) -> dict[int, str]:
    counts: dict[int, int] = {}
    for row in stats_for_date(game_date):
        counts[row["player_id"]] = counts.get(row["player_id"], 0) + 1
    return {
        player_id: f"{count} game" if count == 1 else f"{count} games"
        for player_id, count in counts.items()
    }


def next_game_number(game_date: date, player_id: int) -> int:
    player_games = stats_by_game(game_date, player_id)
    return max(player_games.keys(), default=0) + 1


def next_group_game_number(game_date: date) -> int:
    game_numbers = [row["game_number"] for row in stats_for_date(game_date)]
    return max(game_numbers, default=0) + 1


def default_stat_values(stats: dict | None = None) -> dict:
    stats = stats or {}
    return {
        "result": stats.get("result", ""),
        "points": int(stats.get("points", 0) or 0),
        "field_goals_made": int(stats.get("field_goals_made", 0) or 0),
        "field_goals_attempted": int(stats.get("field_goals_attempted", 0) or 0),
        "rebounds": int(stats.get("rebounds", 0) or 0),
        "assists": int(stats.get("assists", 0) or 0),
        "steals": int(stats.get("steals", 0) or 0),
        "blocks": int(stats.get("blocks", 0) or 0),
        "threes": int(stats.get("threes", 0) or 0),
        "three_attempts": int(stats.get("three_attempts", 0) or 0),
        "turnovers": int(stats.get("turnovers", 0) or 0),
        "notes": stats.get("notes", "") or "",
    }


def save_stat_line(game_date: date, game_number: int, player_id: int, values: dict) -> None:
    now = datetime.utcnow().isoformat()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO game_stats (
                game_date, game_number, player_id, result, points, field_goals_made,
                field_goals_attempted, rebounds, assists, steals, blocks,
                threes, three_attempts, turnovers, notes, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_date, game_number, player_id) DO UPDATE SET
                result = excluded.result,
                points = excluded.points,
                field_goals_made = excluded.field_goals_made,
                field_goals_attempted = excluded.field_goals_attempted,
                rebounds = excluded.rebounds,
                assists = excluded.assists,
                steals = excluded.steals,
                blocks = excluded.blocks,
                threes = excluded.threes,
                three_attempts = excluded.three_attempts,
                turnovers = excluded.turnovers,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (
                game_date.isoformat(),
                game_number,
                player_id,
                values["result"],
                values["points"],
                values["field_goals_made"],
                values["field_goals_attempted"],
                values["rebounds"],
                values["assists"],
                values["steals"],
                values["blocks"],
                values["threes"],
                values["three_attempts"],
                values["turnovers"],
                values["notes"],
                now,
            ),
        )
    backup_db_to_github_if_configured()


def save_stat_lines_bulk(game_date: date, game_number: int, player_values: list[tuple[int, dict]]) -> None:
    now = datetime.utcnow().isoformat()
    params = [
        (
            game_date.isoformat(),
            game_number,
            player_id,
            values["result"],
            values["points"],
            values["field_goals_made"],
            values["field_goals_attempted"],
            values["rebounds"],
            values["assists"],
            values["steals"],
            values["blocks"],
            values["threes"],
            values["three_attempts"],
            values["turnovers"],
            values["notes"],
            now,
        )
        for player_id, values in player_values
    ]
    if not params:
        return
    with db() as conn:
        conn.executemany(
            """
            INSERT INTO game_stats (
                game_date, game_number, player_id, result, points, field_goals_made,
                field_goals_attempted, rebounds, assists, steals, blocks,
                threes, three_attempts, turnovers, notes, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_date, game_number, player_id) DO UPDATE SET
                result = excluded.result,
                points = excluded.points,
                field_goals_made = excluded.field_goals_made,
                field_goals_attempted = excluded.field_goals_attempted,
                rebounds = excluded.rebounds,
                assists = excluded.assists,
                steals = excluded.steals,
                blocks = excluded.blocks,
                threes = excluded.threes,
                three_attempts = excluded.three_attempts,
                turnovers = excluded.turnovers,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            params,
        )
    backup_db_to_github_if_configured()


def delete_stat_line(game_date: date, game_number: int, player_id: int) -> None:
    with db() as conn:
        conn.execute(
            """
            DELETE FROM game_stats
            WHERE game_date = ?
              AND game_number = ?
              AND player_id = ?
            """,
            (game_date.isoformat(), game_number, player_id),
        )
    all_stats.clear()
    backup_db_to_github_if_configured()


@st.cache_data(ttl=2)
def all_stats() -> pd.DataFrame:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT
                gs.game_date,
                gs.game_number,
                p.name,
                p.id AS player_id,
                gs.result,
                gs.points,
                gs.field_goals_made,
                gs.field_goals_attempted,
                gs.rebounds,
                gs.assists,
                gs.steals,
                gs.blocks,
                gs.threes,
                gs.three_attempts,
                gs.turnovers,
                gs.notes,
                gs.updated_at
            FROM game_stats gs
            JOIN players p ON p.id = gs.player_id
            ORDER BY gs.game_date DESC, gs.game_number DESC, p.sort_order, p.id
            """
        ).fetchall()
    return pd.DataFrame([normalize_row(row) for row in rows])


def stat_input(label: str, key: str, value: int, label_visibility: str = "visible") -> int:
    return int(
        st.number_input(
            label,
            min_value=0,
            max_value=200,
            value=int(value or 0),
            step=1,
            key=key,
            label_visibility=label_visibility,
        )
    )


def stat_line_validation_errors(values: dict, player_name: str = "") -> list[str]:
    prefix = f"{player_name}: " if player_name else ""
    errors = []
    if values["field_goals_made"] > values["field_goals_attempted"]:
        errors.append(f"{prefix}FGM cannot be greater than FGA.")
    if values["threes"] > values["three_attempts"]:
        errors.append(f"{prefix}3PM cannot be greater than 3PA.")
    if values["threes"] > values["field_goals_made"]:
        errors.append(f"{prefix}3PM cannot be greater than FGM.")
    return errors


def adjust_number_state(key: str, delta: int, minimum: int = 0, maximum: int = 200) -> None:
    current = int(st.session_state.get(key, 0) or 0)
    st.session_state[key] = max(minimum, min(maximum, current + delta))


def format_game_date(game_date: date) -> str:
    return f"{game_date:%b} {game_date.day}, {game_date:%Y}"


def safe_shooting_pct(made: int | float, attempted: int | float) -> float:
    attempts = int(attempted or 0)
    if attempts <= 0:
        return 0.0
    makes = max(0, min(int(made or 0), attempts))
    return round(makes / attempts, 3)


def format_date_with_weekday(game_date: date) -> str:
    return f"{game_date:%Y-%m-%d} {WEEKDAY_ABBREVIATIONS[game_date.weekday()]}"


def parse_game_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def saved_game_dates(df: pd.DataFrame | None = None) -> list[date]:
    stats_df = all_stats() if df is None else df
    if stats_df.empty or "game_date" not in stats_df:
        return []
    dates = {parsed for parsed in (parse_game_date(value) for value in stats_df["game_date"]) if parsed}
    return sorted(dates, reverse=True)


def formatted_metric_average(value: float) -> str:
    return f"{value:.1f}"


def format_stats_dataframe(
    display: pd.DataFrame,
    percent_columns: set[str] | None = None,
    average_columns: set[str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    formatted = display.copy()
    column_config = {}
    percent_labels = percent_columns or PERCENT_COLUMNS
    average_labels = average_columns or AVERAGE_COLUMNS

    for column in formatted.columns:
        if column in percent_labels:
            formatted[column] = pd.to_numeric(formatted[column], errors="coerce") * 100
            column_config[column] = st.column_config.NumberColumn(column, format="%.1f%%")
        elif column in average_labels:
            formatted[column] = pd.to_numeric(formatted[column], errors="coerce")
            column_config[column] = st.column_config.NumberColumn(column, format="%.1f")
    return formatted, column_config


def render_stats_dataframe(display: pd.DataFrame, **kwargs) -> None:
    formatted, column_config = format_stats_dataframe(display)
    table = formatted
    if not is_dark_mode():
        table = formatted.style.set_properties(
            **{
                "background-color": "#ffffff",
                "color": "#0f172a",
                "border-color": "#d7dee8",
            }
        ).set_table_styles(
            [
                {
                    "selector": "th",
                    "props": [
                        ("background-color", "#eef5fb"),
                        ("color", "#0f172a"),
                        ("border-color", "#d7dee8"),
                    ],
                },
                {
                    "selector": "td",
                    "props": [
                        ("background-color", "#ffffff"),
                        ("color", "#0f172a"),
                        ("border-color", "#d7dee8"),
                    ],
                },
            ]
        )
    st.dataframe(table, column_config=column_config, **kwargs)


def display_stat_lines(df: pd.DataFrame) -> pd.DataFrame:
    display_columns = ["game_date", *GAME_LOG_COLUMNS.keys()]
    return add_percentages(df)[display_columns].rename(
        columns={
            "game_date": "Date",
            **GAME_LOG_COLUMNS,
        }
    )


def formula_alias(column: str) -> str:
    return (
        column.upper()
        .replace("%", "_PCT")
        .replace("3P", "THREE")
        .replace("/", "_")
        .replace(" ", "_")
        .replace("-", "_")
    )


def safe_formula_value(node: ast.AST, variables: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return safe_formula_value(node.body, variables)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise ValueError(f"Unknown field: {node.id}")
        return float(variables[node.id])
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = safe_formula_value(node.operand, variables)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
        left = safe_formula_value(node.left, variables)
        right = safe_formula_value(node.right, variables)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right if right else 0.0
        if abs(right) > 8:
            raise ValueError("Exponent is too large")
        return left**right
    raise ValueError("Use only fields, numbers, parentheses, and + - * / **")


def evaluate_custom_formula(formula: str, variables: dict[str, float]) -> float:
    parsed = ast.parse(formula, mode="eval")
    if sum(1 for _ in ast.walk(parsed)) > 80:
        raise ValueError("Formula is too long")
    value = safe_formula_value(parsed, variables)
    if abs(value) > 1_000_000_000:
        raise ValueError("Formula result is too large")
    return round(value, 1)


def add_custom_stat_columns(df: pd.DataFrame, custom_stats: list[dict]) -> tuple[pd.DataFrame, list[str], list[str]]:
    result = df.copy()
    custom_columns = []
    errors = []
    for custom_stat in custom_stats:
        name = custom_stat["name"].strip()
        formula = custom_stat["formula"].strip()
        if not name or not formula:
            continue
        values = []
        try:
            for _, row in result.iterrows():
                variables = {}
                for column, value in row.items():
                    numeric_value = pd.to_numeric(value, errors="coerce")
                    if pd.isna(numeric_value):
                        numeric_value = 0
                    variables[formula_alias(str(column))] = float(numeric_value)
                values.append(evaluate_custom_formula(formula, variables))
            result[name] = values
            custom_columns.append(name)
        except (SyntaxError, ValueError, OverflowError, ZeroDivisionError) as exc:
            errors.append(f"{name}: {exc}")
    return result, custom_columns, errors


def app_today() -> date:
    if APP_TIME_ZONE is None:
        return date.today()
    return datetime.now(APP_TIME_ZONE).date()


def active_background_date() -> date:
    value = st.session_state.get("playing_date") or st.session_state.get("summary_date")
    return value if isinstance(value, date) else app_today()


def night_background_key(game_date: date) -> str:
    df = all_stats()
    if df.empty:
        return "neutral"
    rows = df[df["game_date"] == game_date.isoformat()]
    wins = int((rows["result"] == "W").sum())
    losses = int((rows["result"] == "L").sum())
    if wins > losses:
        return "winning"
    if losses > wins:
        return "losing"
    return "neutral"


def theme_mode() -> str:
    return st.session_state.get("theme_mode", "Dark")


def is_dark_mode() -> bool:
    return bool(st.session_state.get("night_mode_toggle", theme_mode() == "Dark"))


def render_theme_toggle() -> None:
    if "night_mode_toggle" not in st.session_state:
        st.session_state.night_mode_toggle = is_dark_mode()
    dark_mode = st.toggle("Night mode", key="night_mode_toggle")
    st.session_state.theme_mode = "Dark" if dark_mode else "Light"


def selected_player_id(players: list[dict]) -> int:
    player_ids = {player["id"] for player in players}
    active_player_id = st.session_state.get("active_player_id")
    if active_player_id in player_ids:
        return active_player_id

    selected_id = players[0]["id"]
    st.session_state.active_player_id = selected_id
    return selected_id


def select_player(player_id: int) -> None:
    st.session_state.active_player_id = player_id


def render_player_avatar(player: dict, size: int = 92) -> None:
    if player.get("photo_blob"):
        mime_type = player.get("photo_mime") or "image/png"
        encoded = base64.b64encode(player["photo_blob"]).decode("ascii")
        st.markdown(
            f'<img class="carousel-avatar" src="data:{mime_type};base64,{encoded}" '
            f'style="width:{size}px;height:{size}px;" alt="">',
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        (
            f'<div class="carousel-avatar-placeholder" style="width:{size}px;height:{size}px;">'
            f'{html.escape(player_initials(player["name"]))}</div>'
        ),
        unsafe_allow_html=True,
    )


def player_initials(name: str) -> str:
    parts = [part for part in name.strip().split() if part]
    if not parts:
        return "+"
    return "".join(part[0].upper() for part in parts[:2])


def player_photo_data_url(player: dict) -> str:
    if not player.get("photo_blob"):
        return ""
    mime_type = player.get("photo_mime") or "image/png"
    encoded = base64.b64encode(player["photo_blob"]).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def render_bus_wheels() -> None:
    st.markdown(
        '<div class="bus-wheels" aria-hidden="true"><span></span><span></span></div>',
        unsafe_allow_html=True,
    )


def render_clickable_photo_control(player: dict, scope: str, size: int = 112) -> None:
    photo_url = player_photo_data_url(player)
    if photo_url:
        visual = (
            f'<img class="profile-photo-click-target" src="{photo_url}" '
            f'style="width:{size}px;height:{size}px;" alt="">'
        )
    else:
        visual = (
            f'<div class="profile-photo-click-target is-empty" style="width:{size}px;height:{size}px;">'
            f'{html.escape(player_initials(player["name"]))}</div>'
        )

    with st.container(key=f"{scope}_photo_click_{player['id']}"):
        st.markdown(visual, unsafe_allow_html=True)
        uploaded = st.file_uploader(
            f"Click to add / change photo for {player['name']}",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"{scope}_photo_upload_{player['id']}",
            label_visibility="collapsed",
        )
        st.caption("Click to add / change photo")
        if uploaded is not None:
            update_player_photo(player["id"], uploaded.getvalue(), uploaded.type)
            st.success("Profile photo saved.")
            st.rerun()
        if player.get("photo_blob"):
            if st.button(
                "Remove",
                key=f"{scope}_remove_photo_{player['id']}",
                use_container_width=True,
            ):
                remove_player_photo(player["id"])
                st.success("Profile photo removed.")
                st.rerun()


def render_player_picker(
    players: list[dict],
    current_player_id: int,
    player_badges: dict[int, str],
    scope: str,
) -> None:
    current_index = next(
        (index for index, player in enumerate(players) if player["id"] == current_player_id),
        0,
    )
    with st.container(key=f"{scope}_player_picker"):
        nav_cols = st.columns([0.55, 8, 0.55])
        with nav_cols[0]:
            if st.button("‹", key=f"{scope}_prev_player", use_container_width=True, help="Previous player"):
                select_player(players[(current_index - 1) % len(players)]["id"])
                st.rerun()

        with nav_cols[1]:
            with st.container(key=f"{scope}_player_bus"):
                columns = st.columns(len(players))
                for index, player in enumerate(players):
                    color = PLAYER_COLORS[index % len(PLAYER_COLORS)]
                    selected = player["id"] == current_player_id
                    badge = player_badges.get(player["id"], "")
                    with columns[index]:
                        with st.container(key=f"{scope}_player_tile_{player['id']}"):
                            render_player_avatar(player, size=78)
                            st.markdown(
                                (
                                    f'<div class="carousel-player-name" style="color:{color};">'
                                    f'{html.escape(player["name"])}</div>'
                                ),
                                unsafe_allow_html=True,
                            )
                            if badge:
                                st.markdown(
                                    f'<div class="carousel-player-badge">{html.escape(badge)}</div>',
                                    unsafe_allow_html=True,
                                )
                            if st.button(
                                "Current" if selected else "Select",
                                key=f"{scope}_player_{player['id']}",
                                use_container_width=True,
                                disabled=selected,
                            ):
                                select_player(player["id"])
                                st.rerun()
            render_bus_wheels()

        with nav_cols[2]:
            if st.button("›", key=f"{scope}_next_player", use_container_width=True, help="Next player"):
                select_player(players[(current_index + 1) % len(players)]["id"])
                st.rerun()


def render_game_player_bus(players: list[dict], selected_player_ids: list[int], selection_key: str) -> None:
    selected_ids = set(selected_player_ids)
    st.caption("Click a bus window to add or remove players for this game.")
    with st.container(key="game_night_player_picker"):
        with st.container(key="game_night_player_bus"):
            columns = st.columns(len(players))
            for index, player in enumerate(players):
                color = PLAYER_COLORS[index % len(PLAYER_COLORS)]
                selected = player["id"] in selected_ids
                badge = "In game" if selected else "Click to add"
                with columns[index]:
                    with st.container(key=f"game_night_player_tile_{player['id']}"):
                        render_player_avatar(player, size=78)
                        st.markdown(
                            (
                                f'<div class="carousel-player-name" style="color:{color};">'
                                f'{html.escape(player["name"])}</div>'
                            ),
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            (
                                f'<div class="carousel-player-badge {"is-selected" if selected else ""}">'
                                f'{badge}</div>'
                            ),
                            unsafe_allow_html=True,
                        )
                        if st.button(
                            "Remove from game" if selected else "Add to game",
                            key=f"game_night_player_{player['id']}",
                            use_container_width=True,
                        ):
                            updated_ids = set(st.session_state.get(selection_key, []))
                            if selected:
                                updated_ids.discard(player["id"])
                            else:
                                updated_ids.add(player["id"])
                            st.session_state[selection_key] = [
                                player_option["id"]
                                for player_option in players
                                if player_option["id"] in updated_ids
                            ]
                            st.rerun()
            render_bus_wheels()


def render_player_stats_detail(player: dict) -> None:
    player_view, filtered_all = render_stats_scope_controls("player_page", all_stats())
    scoped_df = filtered_all[filtered_all["player_id"] == player["id"]].copy() if not filtered_all.empty else filtered_all
    completed = scoped_df[scoped_df["result"].isin(["W", "L"])].copy() if not scoped_df.empty else scoped_df
    summary = aggregate_player_totals(completed, ["player_id", "name"]) if not completed.empty else pd.DataFrame()

    with st.container(border=True, key=f"player_profile_summary_{player['id']}"):
        st.markdown(f"### {player['name']}")
        top_cols = st.columns([1.25, 4])
        with top_cols[0]:
            render_clickable_photo_control(player, "player_page", size=132)
        with top_cols[1]:
            metric_cols = st.columns(4)
            if summary.empty:
                for col, label in zip(metric_cols, ["Games", "Wins", "PPG", "RPG"]):
                    col.metric(label, "0.0" if label.endswith("PG") else 0)
            else:
                row = summary.iloc[0]
                total_games = int(row["games"])
                metric_cols[0].metric("Games", total_games)
                metric_cols[1].metric("Wins", int(row["wins"]))
                metric_cols[2].metric("PPG", formatted_metric_average(row["points"] / total_games))
                metric_cols[3].metric("RPG", formatted_metric_average(row["rebounds"] / total_games))

    filtered = scoped_df
    completed = filtered[filtered["result"].isin(["W", "L"])].copy() if not filtered.empty else filtered
    history = aggregate_player_totals(completed, ["game_date", "player_id", "name"]).sort_values("game_date", ascending=False) if not completed.empty else pd.DataFrame()

    if history.empty:
        st.info(f"No stat lines saved for {player['name']} in this view yet.")
        return

    if player_view == "Per game averages":
        display = player_average_display(history)
    else:
        display_columns = [
            "game_date",
            "games",
            "wins",
            "losses",
            "record",
            "points",
            "field_goals_made",
            "field_goals_attempted",
            "rebounds",
            "assists",
            "steals",
            "blocks",
            "threes",
            "three_attempts",
            "turnovers",
        ]
        display = history[display_columns].rename(
            columns={
                "game_date": "Date",
                "games": "Games",
                "wins": "W",
                "losses": "L",
                "record": "W-L",
                "points": "PTS",
                "field_goals_made": "FGM",
                "field_goals_attempted": "FGA",
                "rebounds": "REB",
                "assists": "AST",
                "steals": "STL",
                "blocks": "BLK",
                "threes": "3PM",
                "three_attempts": "3PA",
                "turnovers": "TO",
            }
        )

    st.caption("Filtered player results. Click any column header to sort.")
    render_stats_dataframe(display, use_container_width=True, hide_index=True)
    st.download_button(
        "Download Player CSV",
        data=display.to_csv(index=False),
        file_name=f"{csv_safe_name(player['name'])}_stats.csv",
        mime="text/csv",
    )

    with st.expander("Game-by-game log", expanded=False):
        games = add_percentages(filtered).sort_values(["game_date", "game_number"], ascending=[False, False])
        game_columns = ["game_date", *GAME_LOG_COLUMNS.keys()]
        game_columns.remove("name")
        game_display = games[game_columns].rename(
            columns={
                "game_date": "Date",
                **GAME_LOG_COLUMNS,
            }
        )
        render_stats_dataframe(game_display, use_container_width=True, hide_index=True)


def add_percentages(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if result.empty:
        return result
    result["fg_pct"] = result.apply(
        lambda row: safe_shooting_pct(row["field_goals_made"], row["field_goals_attempted"]),
        axis=1,
    )
    result["three_pct"] = result.apply(
        lambda row: safe_shooting_pct(row["threes"], row["three_attempts"]),
        axis=1,
    )
    return result


def aggregate_player_totals(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    grouped = df.groupby(group_cols, as_index=False).agg(
        games=("game_number", "count"),
        wins=("result", lambda values: int((values == "W").sum())),
        losses=("result", lambda values: int((values == "L").sum())),
        points=("points", "sum"),
        field_goals_made=("field_goals_made", "sum"),
        field_goals_attempted=("field_goals_attempted", "sum"),
        rebounds=("rebounds", "sum"),
        assists=("assists", "sum"),
        steals=("steals", "sum"),
        blocks=("blocks", "sum"),
        threes=("threes", "sum"),
        three_attempts=("three_attempts", "sum"),
        turnovers=("turnovers", "sum"),
    )
    grouped["record"] = grouped["wins"].astype(str) + "-" + grouped["losses"].astype(str)
    grouped["win_pct"] = (grouped["wins"] / grouped["games"]).round(3)
    return add_percentages(grouped)


def render_stats_scope_controls(scope: str, df: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    control_cols = st.columns([1.2, 2.8])
    with control_cols[0]:
        view = st.selectbox(
            "View",
            options=["Totals", "Per game averages"],
            key=f"{scope}_view",
        )
    date_labels = {format_date_with_weekday(game_date): game_date for game_date in saved_game_dates(df)}
    night_options = ["ALL GAMES", *date_labels.keys()]
    with control_cols[1]:
        selected_nights = st.multiselect(
            "Game nights",
            options=night_options,
            default=["ALL GAMES"],
            key=f"{scope}_nights",
        )

    filtered = df.copy()
    if selected_nights and "ALL GAMES" not in selected_nights:
        selected_dates = {date_labels[label].isoformat() for label in selected_nights if label in date_labels}
        filtered = filtered[filtered["game_date"].isin(selected_dates)]
    return view, filtered


def add_per_game_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if result.empty:
        return result
    result["WIN%"] = (result["wins"] / result["games"]).round(3)
    result["PPG"] = (result["points"] / result["games"]).round(1)
    result["RPG"] = (result["rebounds"] / result["games"]).round(1)
    result["APG"] = (result["assists"] / result["games"]).round(1)
    result["SPG"] = (result["steals"] / result["games"]).round(1)
    result["BPG"] = (result["blocks"] / result["games"]).round(1)
    result["TPG"] = (result["turnovers"] / result["games"]).round(1)
    result["FGM/G"] = (result["field_goals_made"] / result["games"]).round(1)
    result["FGA/G"] = (result["field_goals_attempted"] / result["games"]).round(1)
    result["3PM/G"] = (result["threes"] / result["games"]).round(1)
    result["3PA/G"] = (result["three_attempts"] / result["games"]).round(1)
    return result


def player_average_display(history: pd.DataFrame) -> pd.DataFrame:
    with_averages = add_per_game_columns(history)
    columns = [
        "game_date",
        "games",
        "wins",
        "losses",
        "WIN%",
        "PPG",
        "fg_pct",
        "three_pct",
        "RPG",
        "APG",
        "SPG",
        "BPG",
        "TPG",
        "FGM/G",
        "FGA/G",
        "3PM/G",
        "3PA/G",
    ]
    return with_averages[columns].rename(
        columns={
            "game_date": "Date",
            "games": "Games",
            "wins": "W",
            "losses": "L",
            "fg_pct": "FG%",
            "three_pct": "3P%",
        }
    )


def nightly_summary(game_date: date) -> pd.DataFrame:
    df = all_stats()
    if df.empty:
        return df
    df = df[df["game_date"] == game_date.isoformat()].copy()
    return aggregate_player_totals(df, ["player_id", "name"])


def nightly_game_log(game_date: date) -> pd.DataFrame:
    df = all_stats()
    if df.empty:
        return df
    df = df[df["game_date"] == game_date.isoformat()].copy()
    return add_percentages(df)


def render_photo(player: dict, size: int = 96) -> None:
    if player.get("photo_blob"):
        st.image(player["photo_blob"], width=size)
        return
    st.markdown(
        f'<div class="photo-placeholder" style="width:{size}px;height:{size}px;">+</div>',
        unsafe_allow_html=True,
    )


def render_player_photo_manager(player: dict, scope: str) -> None:
    with st.container(border=True, key=f"{scope}_photo_manager_{player['id']}"):
        cols = st.columns([1, 3, 2])
        with cols[0]:
            render_photo(player, size=92)
        with cols[1]:
            st.markdown("#### Profile photo")
            st.caption("Add, change, or remove this player's profile picture.")
            uploaded = st.file_uploader(
                "Add or change profile photo",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"{scope}_photo_upload_{player['id']}",
            )
            if uploaded is not None:
                update_player_photo(player["id"], uploaded.getvalue(), uploaded.type)
                st.success("Profile photo saved.")
                st.rerun()
        with cols[2]:
            st.write("")
            st.write("")
            if player.get("photo_blob"):
                if st.button(
                    "Remove Photo",
                    key=f"{scope}_remove_photo_{player['id']}",
                    use_container_width=True,
                ):
                    remove_player_photo(player["id"])
                    st.success("Profile photo removed.")
                    st.rerun()


def render_stat_form(player: dict, game_date: date, game_number: int, stats: dict) -> None:
    result_options = ["", "W", "L"]
    current_result = stats.get("result", "")
    result_index = result_options.index(current_result) if current_result in result_options else 0

    with st.form(f"stat_form_{game_date}_{game_number}_{player['id']}"):
        st.markdown(f"### {player['name']} - Game {game_number}")
        st.caption(format_game_date(game_date))
        result = st.radio(
            "Team result",
            options=result_options,
            index=result_index,
            horizontal=True,
            format_func=lambda option: "Unset" if option == "" else option,
            key=f"result_{game_date}_{game_number}_{player['id']}",
        )

        stat_values = {"result": result}
        with st.container(key=f"stat_entry_fields_{game_date}_{game_number}_{player['id']}"):
            first_row = st.columns(5)
            for index, field in enumerate(["points", "field_goals_made", "field_goals_attempted", "threes", "three_attempts"]):
                with first_row[index]:
                    stat_values[field] = stat_input(
                        STAT_FIELDS[field],
                        f"{field}_{game_date}_{game_number}_{player['id']}",
                        stats.get(field, 0),
                    )

            second_row = st.columns(5)
            for index, field in enumerate(["rebounds", "assists", "steals", "blocks", "turnovers"]):
                with second_row[index]:
                    stat_values[field] = stat_input(
                        STAT_FIELDS[field],
                        f"{field}_{game_date}_{game_number}_{player['id']}",
                        stats.get(field, 0),
                    )

        stat_values["notes"] = st.text_input(
            "Notes",
            value=stats.get("notes", ""),
            key=f"notes_{game_date}_{game_number}_{player['id']}",
            placeholder="Optional",
        )
        submitted = st.form_submit_button(
            "Save Game",
            type="primary",
            use_container_width=True,
    )

    if submitted:
        validation_errors = stat_line_validation_errors(stat_values)
        if validation_errors:
            for error in validation_errors:
                st.error(error)
            return
        save_stat_line(game_date, game_number, player["id"], stat_values)
        all_stats.clear()
        st.session_state[f"editing_{game_date}_{game_number}_{player['id']}"] = False
        st.session_state[f"pending_game_{game_date}_{player['id']}"] = next_game_number(game_date, player["id"])
        st.success(f"Saved {player['name']} Game {game_number}.")
        st.rerun()


def render_saved_stat_line(player: dict, game_date: date, game_number: int, stats: dict) -> None:
    st.markdown(f"### {player['name']} - Game {game_number}")
    metric_cols = st.columns(5)
    metric_cols[0].metric("PTS", stats.get("points", 0))
    metric_cols[1].metric(
        "FG",
        f"{stats.get('field_goals_made', 0)}/{stats.get('field_goals_attempted', 0)}",
    )
    metric_cols[2].metric("3PT", f"{stats.get('threes', 0)}/{stats.get('three_attempts', 0)}")
    metric_cols[3].metric("REB", stats.get("rebounds", 0))
    metric_cols[4].metric("AST", stats.get("assists", 0))

    detail_cols = st.columns(5)
    detail_cols[0].metric("STL", stats.get("steals", 0))
    detail_cols[1].metric("BLK", stats.get("blocks", 0))
    detail_cols[2].metric("TO", stats.get("turnovers", 0))
    detail_cols[3].metric("W/L", stats.get("result") or "Unset")
    detail_cols[4].metric("Date", format_game_date(game_date))

    if stats.get("notes"):
        st.caption(f"Notes: {stats['notes']}")

    action_cols = st.columns(2)
    with action_cols[0]:
        if st.button("Edit Game Stats", key=f"edit_{game_date}_{game_number}_{player['id']}", type="primary", use_container_width=True):
            st.session_state[f"editing_{game_date}_{game_number}_{player['id']}"] = True
            st.rerun()
    with action_cols[1]:
        confirm_key = f"confirm_delete_{game_date}_{game_number}_{player['id']}"
        confirmed = st.checkbox(
            f"Confirm delete Game {game_number}",
            key=confirm_key,
        )
        if st.button(
            "Delete Game Stats",
            key=f"delete_{game_date}_{game_number}_{player['id']}",
            disabled=not confirmed,
            use_container_width=True,
        ):
            delete_stat_line(game_date, game_number, player["id"])
            st.session_state.pop(confirm_key, None)
            st.session_state[f"pending_game_{game_date}_{player['id']}"] = next_game_number(game_date, player["id"])
            st.success(f"Deleted {player['name']} Game {game_number}.")
            st.rerun()


def render_game_location(game_date: date) -> None:
    metadata = game_night_metadata(game_date)
    locations = saved_locations()
    current_location = metadata.get("location_name", "")
    location_options = ["Add or type location", *locations]
    if current_location and current_location not in locations:
        location_options.append(current_location)
    selected_index = (
        location_options.index(current_location)
        if current_location in location_options
        else 0
    )

    with st.container(border=True, key=f"game_location_{game_date}"):
        cols = st.columns([2, 4, 1.4])
        with cols[0]:
            selected_location = st.selectbox(
                "Saved locations",
                options=location_options,
                index=selected_index,
                key=f"location_select_{game_date}",
            )
        location_value = current_location if selected_location == "Add or type location" else selected_location
        with cols[1]:
            typed_location = st.text_input(
                "Game location",
                value=location_value,
                key=f"location_input_{game_date}",
                placeholder="Great Park, Irvine CA",
            )
        with cols[2]:
            st.write("")
            if st.button("Save Location", key=f"save_location_{game_date}", use_container_width=True):
                save_game_night_location(game_date, typed_location)
                st.success("Location saved.")
                st.rerun()

        maps_url = google_maps_search_url(typed_location) or metadata.get("maps_url", "")
        if maps_url:
            st.markdown(f"[Open in Google Maps]({maps_url})")
        if current_location:
            if st.button("Clear Location", key=f"clear_location_{game_date}"):
                remove_game_night_location(game_date)
                st.rerun()


def render_bulk_game_form(players: list[dict], game_date: date) -> None:
    date_rows = stats_for_date(game_date)
    existing_games = sorted({row["game_number"] for row in date_rows})
    next_game = next_group_game_number(game_date)
    game_options = existing_games + ([] if next_game in existing_games else [next_game])
    game_key = f"bulk_game_{game_date}"
    pending_game_key = f"bulk_pending_game_{game_date}"
    if st.session_state.get(pending_game_key) in game_options:
        st.session_state[game_key] = st.session_state.pop(pending_game_key)
    if st.session_state.get(game_key) not in game_options:
        st.session_state[game_key] = next_game

    selected_game = st.selectbox(
        "Game",
        options=game_options,
        key=game_key,
        format_func=lambda value: f"Game {value}" + (" (next)" if value == next_game else ""),
    )

    existing_game_stats = stats_for_game(game_date, selected_game)
    player_names = {player["id"]: player["name"] for player in players}
    selection_key = f"bulk_players_{game_date}_{selected_game}"
    if selection_key not in st.session_state:
        existing_player_ids = [
            player["id"]
            for player in players
            if player["id"] in existing_game_stats
        ]
        st.session_state[selection_key] = existing_player_ids
    selected_player_ids = [
        player["id"]
        for player in players
        if player["id"] in set(st.session_state.get(selection_key, []))
    ]
    render_game_player_bus(players, selected_player_ids, selection_key)

    if not selected_player_ids:
        st.info("Click player windows on the bus to add players to this game.")
        return

    player_values = []
    with st.container(key=f"bulk_game_stepper_table_{game_date}_{selected_game}"):
        header_cols = st.columns([1.35, 0.9, *([1.35] * len(BULK_STAT_COLUMNS)), 1.45])
        header_cols[0].markdown("**Player**")
        header_cols[1].markdown("**W/L**")
        for col, (label, _) in zip(header_cols[2:-1], BULK_STAT_COLUMNS):
            col.markdown(f"**{label}**")
        header_cols[-1].markdown("**Notes**")

        for player_id in selected_player_ids:
            values = default_stat_values(existing_game_stats.get(player_id))
            row_cols = st.columns([1.35, 0.9, *([1.35] * len(BULK_STAT_COLUMNS)), 1.45])
            with row_cols[0]:
                st.markdown(f"**{player_names[player_id]}**")
            with row_cols[1]:
                result_options = ["", "W", "L"]
                current_result = values["result"] if values["result"] in result_options else ""
                result = st.selectbox(
                    "W/L",
                    options=result_options,
                    index=result_options.index(current_result),
                    format_func=lambda option: "-" if option == "" else option,
                    key=f"bulk_result_{game_date}_{selected_game}_{player_id}",
                    label_visibility="collapsed",
                )

            stat_values = {"result": result}
            for col, (label, field) in zip(row_cols[2:-1], BULK_STAT_COLUMNS):
                with col:
                    value_key = f"bulk_{field}_{game_date}_{selected_game}_{player_id}"
                    if value_key not in st.session_state:
                        st.session_state[value_key] = values[field]
                    with st.container(key=f"bulk_stepper_{field}_{game_date}_{selected_game}_{player_id}"):
                        step_cols = st.columns([0.95, 1.05, 0.95])
                        with step_cols[0]:
                            st.button(
                                r"\-",
                                key=f"{value_key}_minus",
                                on_click=adjust_number_state,
                                args=(value_key, -1),
                                use_container_width=True,
                            )
                        with step_cols[1]:
                            stat_values[field] = stat_input(
                                label,
                                value_key,
                                st.session_state[value_key],
                                label_visibility="collapsed",
                            )
                        with step_cols[2]:
                            st.button(
                                r"\+",
                                key=f"{value_key}_plus",
                                on_click=adjust_number_state,
                                args=(value_key, 1),
                                use_container_width=True,
                            )

            with row_cols[-1]:
                stat_values["notes"] = st.text_input(
                    "Notes",
                    value=values["notes"],
                    key=f"bulk_notes_{game_date}_{selected_game}_{player_id}",
                    label_visibility="collapsed",
                    placeholder="Optional",
                )
            player_values.append((player_id, stat_values))

    st.caption("Save Game updates selected players only. Deselecting a player does not delete any existing stat line.")
    submitted = st.button("Save Game Table", type="primary", use_container_width=True)

    if not submitted:
        return

    validation_errors = []
    for player_id, values in player_values:
        if values["result"] not in ["", "W", "L"]:
            validation_errors.append(f"{player_names[player_id]}: W/L must be W, L, or blank.")
        validation_errors.extend(stat_line_validation_errors(values, player_names[player_id]))

    if validation_errors:
        for error in validation_errors:
            st.error(error)
        return

    was_new_game = selected_game == next_game
    save_stat_lines_bulk(game_date, selected_game, player_values)
    all_stats.clear()
    if was_new_game:
        st.session_state[pending_game_key] = next_group_game_number(game_date)
    st.success(f"Saved Game {selected_game} for {len(player_values)} players.")
    st.rerun()


def render_game_night(players: list[dict]) -> None:
    st.subheader("Game Night")
    game_date = st.date_input("Playing date", value=app_today(), key="playing_date")
    st.info("To upload or change a player photo, go to the Roster tab or Player Page tab.")
    entry_mode = st.segmented_control(
        "Entry mode",
        options=["Full game table", "One player"],
        default="Full game table",
        key="game_night_entry_mode",
        width="stretch",
    )
    entry_mode = entry_mode or "Full game table"

    if entry_mode == "Full game table":
        st.caption("Select the players in the game, enter everyone on one table, then save the game.")
        render_bulk_game_form(players, game_date)
        return

    player_badges = game_counts_for_date(game_date)
    current_player_id = selected_player_id(players)
    st.caption("Select a player, then enter one game at a time. The next game opens automatically after saving.")
    render_player_picker(players, current_player_id, player_badges, scope="game_night")

    current_player = next(player for player in players if player["id"] == current_player_id)
    player_games = stats_by_game(game_date, current_player_id)
    next_game = max(player_games.keys(), default=0) + 1
    game_options = sorted(player_games.keys()) + [next_game]
    game_key = f"selected_game_{game_date}_{current_player_id}"
    pending_game_key = f"pending_game_{game_date}_{current_player_id}"
    if st.session_state.get(pending_game_key) in game_options:
        st.session_state[game_key] = st.session_state.pop(pending_game_key)
    if st.session_state.get(game_key) not in game_options:
        st.session_state[game_key] = next_game

    with st.container(border=True):
        st.markdown(f"### {current_player['name']}")
        selected_game = st.selectbox(
            "Game",
            options=game_options,
            key=game_key,
            format_func=lambda value: f"Game {value}" + (" (next)" if value == next_game else ""),
        )
        current_stats = player_games.get(selected_game, {})
        edit_key = f"editing_{game_date}_{selected_game}_{current_player_id}"

        if current_stats and not st.session_state.get(edit_key, False):
            render_saved_stat_line(current_player, game_date, selected_game, current_stats)
        else:
            render_stat_form(current_player, game_date, selected_game, current_stats)


def render_nightly_summary() -> None:
    st.subheader("Nightly Summary")
    dates = saved_game_dates()
    if dates:
        game_date = st.selectbox(
            "Summary date",
            options=dates,
            key="summary_date",
            format_func=format_date_with_weekday,
        )
    else:
        game_date = st.date_input("Summary date", value=app_today(), key="summary_date")
    summary = nightly_summary(game_date)
    game_log = nightly_game_log(game_date)

    if summary.empty:
        st.info(f"No stat lines saved for {format_game_date(game_date)} yet.")
        return

    display = summary[list(NIGHTLY_TOTAL_COLUMNS.keys())].rename(columns=NIGHTLY_TOTAL_COLUMNS)
    st.caption("Nightly totals across all games. Click any column header to sort.")
    render_stats_dataframe(display, use_container_width=True, hide_index=True)
    st.download_button(
        "Download Nightly Totals CSV",
        data=display.to_csv(index=False),
        file_name=f"pickup_totals_{game_date.isoformat()}.csv",
        mime="text/csv",
    )

    with st.expander("Game-by-game log"):
        game_display = game_log[list(GAME_LOG_COLUMNS.keys())].rename(columns=GAME_LOG_COLUMNS)
        render_stats_dataframe(game_display, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Game Log CSV",
            data=game_display.to_csv(index=False),
            file_name=f"pickup_games_{game_date.isoformat()}.csv",
            mime="text/csv",
        )


def player_history(player_id: int) -> pd.DataFrame:
    df = all_stats()
    if df.empty:
        return df
    df = df[df["player_id"] == player_id].copy()
    return aggregate_player_totals(df, ["game_date", "player_id", "name"]).sort_values("game_date", ascending=False)


def player_game_log(player_id: int) -> pd.DataFrame:
    df = all_stats()
    if df.empty:
        return df
    df = df[df["player_id"] == player_id].copy()
    df = add_percentages(df)
    return df.sort_values(["game_date", "game_number"], ascending=[False, False])


def csv_safe_name(name: str) -> str:
    safe_name = "".join(char.lower() if char.isalnum() else "_" for char in name)
    return "_".join(part for part in safe_name.split("_") if part) or "player"


def render_storage_warning() -> None:
    if using_postgres():
        return
    if using_github_storage():
        error = st.session_state.get("github_storage_error")
        if error:
            st.error(f"GitHub backup error: {error}")
        return
    st.warning(
        "Temporary local storage is active. Add GitHub backup secrets before using the hosted app for real games.",
    )
    if DB_PATH.exists():
        st.download_button(
            "Download SQLite Backup",
            data=DB_PATH.read_bytes(),
            file_name="basketball_stats.sqlite3",
            mime="application/octet-stream",
        )


def render_player_page(players: list[dict]) -> None:
    st.subheader("Player Page")
    current_player_id = selected_player_id(players)
    current_player = next(player for player in players if player["id"] == current_player_id)
    render_player_picker(players, current_player_id, {}, scope="player_page")
    render_player_stats_detail(current_player)


def render_backgrounds() -> None:
    st.subheader("Backgrounds")
    st.caption("Upload shared background images. The app picks one consistent image for the selected date and current night outcome.")
    st.caption(f"Image limit: {MAX_BACKGROUND_IMAGE_BYTES // (1024 * 1024)} MB per file. Large image libraries make the GitHub backup slower.")
    current_date = active_background_date()
    current_key = night_background_key(current_date)
    current_asset = selected_background_asset(current_key, current_date)
    st.info(f"Current outcome for {format_game_date(current_date)}: {BACKGROUND_KEYS[current_key]}")
    if current_asset:
        st.image(current_asset["image_blob"], caption="Current selected background", use_container_width=True)

    for asset_key, label in BACKGROUND_KEYS.items():
        with st.container(border=True):
            st.markdown(f"### {label}")
            assets = get_background_assets(asset_key)
            st.caption(f"{len(assets)} image" if len(assets) == 1 else f"{len(assets)} images")
            uploaded = st.file_uploader(
                f"Add {label.lower()}",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"background_{asset_key}",
            )
            if uploaded is not None:
                image_bytes = uploaded.getvalue()
                upload_fingerprint = image_fingerprint(image_bytes)
                upload_key = f"last_background_upload_{asset_key}"
                if len(image_bytes) > MAX_BACKGROUND_IMAGE_BYTES:
                    st.error(f"{uploaded.name} is too large. Keep each image under {MAX_BACKGROUND_IMAGE_BYTES // (1024 * 1024)} MB.")
                elif st.session_state.get(upload_key) != upload_fingerprint:
                    added = add_background_asset(asset_key, image_bytes, uploaded.type)
                    st.session_state[upload_key] = upload_fingerprint
                    if added:
                        st.success(f"Added {label}.")
                    else:
                        st.info("That image is already in this background library.")
                    st.rerun()

            if not assets:
                st.info(f"No {label.lower()} images uploaded yet.")
                continue

            for row_start in range(0, len(assets), 3):
                cols = st.columns(3)
                for offset, (col, asset) in enumerate(zip(cols, assets[row_start:row_start + 3])):
                    image_number = row_start + offset + 1
                    with col:
                        st.image(asset["image_blob"], use_container_width=True)
                        st.caption(f"Image {image_number}")
                        with st.popover("Zoom", use_container_width=True):
                            st.image(asset["image_blob"], use_container_width=True)
                            st.caption(f"Uploaded {asset['uploaded_at']}")
                        if st.button(
                            "Remove",
                            key=f"remove_background_{asset_key}_{asset['id']}",
                            use_container_width=True,
                        ):
                            remove_background_asset(asset["id"])
                            st.success(f"Removed {label} image {image_number}.")
                            st.rerun()


def append_custom_formula_piece(piece: str) -> None:
    key = "leaderboard_custom_formula"
    current = st.session_state.get(key, "").strip()
    spacer = " " if current and piece not in [")"] else ""
    st.session_state[key] = f"{current}{spacer}{piece}".strip()


def render_custom_stat_builder() -> list[dict]:
    custom_stats = get_custom_stats()
    with st.expander("Custom leaderboard stats"):
        if custom_stats:
            st.caption("Saved custom stats")
            for custom_stat in custom_stats:
                with st.container(border=True, key=f"custom_stat_saved_{custom_stat['id']}"):
                    cols = st.columns([2, 4, 1])
                    with cols[0]:
                        st.markdown(f"**{custom_stat['name']}**")
                        if custom_stat["description"]:
                            st.caption(custom_stat["description"])
                    with cols[1]:
                        st.code(custom_stat["formula"], language="text")
                    with cols[2]:
                        if st.button("Delete Stat", key=f"delete_custom_stat_{custom_stat['id']}", use_container_width=True):
                            delete_custom_stat(custom_stat["id"])
                            st.rerun()

        st.caption("Build a formula from leaderboard fields. Use `FG_PCT`, `THREE_PCT`, and `WIN_PCT` for percentage fields.")
        if "leaderboard_custom_formula" not in st.session_state:
            st.session_state.leaderboard_custom_formula = ""
        with st.container(key="custom_stat_builder_controls"):
            builder_cols = st.columns([1.55, 0.82, 0.9, 0.72])
            with builder_cols[0]:
                selected_field = st.selectbox("Field", CUSTOM_STAT_FIELDS, key="custom_stat_field")
            with builder_cols[1]:
                st.write("")
                if st.button("Add Field", key="append_custom_field", use_container_width=True):
                    append_custom_formula_piece(selected_field)
                    st.rerun()
            with builder_cols[2]:
                selected_operator = st.selectbox("Operation", CUSTOM_STAT_OPERATORS, key="custom_stat_operator")
            with builder_cols[3]:
                st.write("")
                if st.button("Add Op", key="append_custom_operator", use_container_width=True):
                    append_custom_formula_piece(selected_operator)
                    st.rerun()

        name = st.text_input("Custom stat name", key="leaderboard_custom_name", placeholder="Bus Rider Score")
        formula = st.text_input(
            "Formula",
            key="leaderboard_custom_formula",
            placeholder="",
        )
        description = st.text_input(
            "Description / comment",
            key="leaderboard_custom_description",
            placeholder="Rewards scoring, efficiency, rebounding, and ball security.",
        )
        if st.button("Add Custom Stat", type="primary", key="save_custom_stat"):
            if not name.strip() or not formula.strip():
                st.error("Add both a custom stat name and formula.")
            else:
                try:
                    sample_variables = {field: 1.0 for field in CUSTOM_STAT_FIELDS}
                    evaluate_custom_formula(formula, sample_variables)
                except (SyntaxError, ValueError, OverflowError, ZeroDivisionError) as exc:
                    st.error(f"Formula needs a fix: {exc}")
                else:
                    add_custom_stat(name, formula, description)
                    st.success("Custom stat added.")
                    st.rerun()
    return custom_stats


def render_leaderboard() -> None:
    st.subheader("Leaderboards")
    df = all_stats()
    if df.empty:
        st.info("No stat lines have been saved yet.")
        return

    metric_cols = st.columns(4)
    metric_cols[0].metric("Stat lines", len(df))
    metric_cols[1].metric("Game nights", df["game_date"].nunique())
    metric_cols[2].metric("Total points", int(df["points"].sum()))
    metric_cols[3].metric("Photos", sum(1 for player in get_players() if player.get("photo_blob")))

    leaderboard_view, filtered = render_stats_scope_controls("leaderboard", df)

    custom_stats = render_custom_stat_builder()

    completed = filtered[filtered["result"].isin(["W", "L"])].copy()
    if completed.empty:
        st.info("Saved rows need W/L results before standings can be calculated.")
        display_df = display_stat_lines(filtered)
        render_stats_dataframe(display_df, use_container_width=True, hide_index=True)
        return

    grouped = completed.groupby("name", as_index=False).agg(
        GP=("game_number", "count"),
        Nights=("game_date", "nunique"),
        W=("result", lambda values: int((values == "W").sum())),
        L=("result", lambda values: int((values == "L").sum())),
        PTS=("points", "sum"),
        FGM=("field_goals_made", "sum"),
        FGA=("field_goals_attempted", "sum"),
        REB=("rebounds", "sum"),
        AST=("assists", "sum"),
        STL=("steals", "sum"),
        BLK=("blocks", "sum"),
        THREE_PM=("threes", "sum"),
        THREE_PA=("three_attempts", "sum"),
        TO=("turnovers", "sum"),
    )
    grouped["WIN%"] = (grouped["W"] / grouped["GP"]).round(3)
    grouped["PPG"] = (grouped["PTS"] / grouped["GP"]).round(1)
    grouped["FG%"] = grouped.apply(lambda row: safe_shooting_pct(row["FGM"], row["FGA"]), axis=1)
    grouped["3P%"] = grouped.apply(lambda row: safe_shooting_pct(row["THREE_PM"], row["THREE_PA"]), axis=1)
    grouped["RPG"] = (grouped["REB"] / grouped["GP"]).round(1)
    grouped["APG"] = (grouped["AST"] / grouped["GP"]).round(1)
    grouped = grouped.sort_values(["W", "WIN%", "PPG"], ascending=False)

    if leaderboard_view == "Per game averages":
        grouped["FGM/G"] = (grouped["FGM"] / grouped["GP"]).round(1)
        grouped["FGA/G"] = (grouped["FGA"] / grouped["GP"]).round(1)
        grouped["3PM/G"] = (grouped["THREE_PM"] / grouped["GP"]).round(1)
        grouped["3PA/G"] = (grouped["THREE_PA"] / grouped["GP"]).round(1)
        grouped["SPG"] = (grouped["STL"] / grouped["GP"]).round(1)
        grouped["BPG"] = (grouped["BLK"] / grouped["GP"]).round(1)
        grouped["TPG"] = (grouped["TO"] / grouped["GP"]).round(1)
        display_columns = AVERAGE_LEADERBOARD_COLUMNS
    else:
        display_columns = TOTAL_LEADERBOARD_COLUMNS

    formula_base = grouped.rename(columns={"name": "Player"}).copy()
    formula_base, custom_columns, custom_errors = add_custom_stat_columns(formula_base, custom_stats)
    for error in custom_errors:
        st.warning(f"Custom stat skipped: {error}")
    display = formula_base[
        ["Player" if column == "name" else column for column in display_columns] + custom_columns
    ].copy()

    formatted, column_config = format_stats_dataframe(
        display,
        average_columns=AVERAGE_COLUMNS | set(custom_columns),
    )
    st.dataframe(formatted, column_config=column_config, use_container_width=True, hide_index=True)

    with st.expander("All saved stat lines"):
        display_df = display_stat_lines(filtered)
        render_stats_dataframe(display_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download CSV",
            data=display_df.to_csv(index=False),
            file_name="pickup_basketball_stats.csv",
            mime="text/csv",
        )


def render_roster(players: list[dict]) -> None:
    st.subheader("Roster")
    st.caption("Rename the seven player slots and manage profile photos.")

    for row_start in range(0, len(players), 3):
        cols = st.columns(3)
        for col, player in zip(cols, players[row_start:row_start + 3]):
            with col:
                with st.container(border=True, key=f"roster_card_{player['id']}"):
                    render_clickable_photo_control(player, "roster", size=104)
                    new_name = st.text_input(
                        "Player name",
                        value=player["name"],
                        key=f"name_{player['id']}",
                    )
                    if st.button("Save name", key=f"rename_{player['id']}", use_container_width=True):
                        update_player_name(player["id"], new_name)
                        st.success("Name saved.")
                        st.rerun()


def inject_css(background_url: str = "") -> None:
    dark = is_dark_mode()
    text = "#f9fafb" if dark else "#111827"
    muted = "#cbd5e1" if dark else "#475569"
    page_bg = "#05070c" if dark else "#f4f8fb"
    panel = "rgba(15, 23, 42, 0.78)" if dark else "rgba(255, 255, 255, 0.92)"
    panel_border = "rgba(125, 211, 252, 0.18)" if dark else "rgba(15, 23, 42, 0.12)"
    placeholder_bg = "#f3f4f6" if dark else "#e5e7eb"
    placeholder_text = "#737373" if dark else "#4b5563"
    widget_bg = "#121826" if dark else "#ffffff"
    widget_text = "#f9fafb" if dark else "#111827"
    widget_border = "rgba(148, 163, 184, 0.26)" if dark else "rgba(15, 23, 42, 0.18)"
    disabled_bg = "#0f141c" if dark else "#eef2f7"
    disabled_text = "#9ca3af" if dark else "#111827"
    table_bg = "#0b1019" if dark else "#ffffff"
    table_header = "#1b2230" if dark else "#e8f0f7"
    table_text = "#f8fafc" if dark else "#0f172a"
    overlay = (
        "linear-gradient(rgba(14, 17, 23, 0.82), rgba(14, 17, 23, 0.9))"
        if dark
        else "linear-gradient(rgba(248, 250, 252, 0.84), rgba(248, 250, 252, 0.92))"
    )
    background_css = f"""
        .stApp {{
            background: {page_bg};
            color: {text};
        }}
    """
    if background_url:
        background_css = f"""
        .stApp {{
            background-image:
                {overlay},
                url("{background_url}");
            background-attachment: fixed;
            background-position: center;
            background-size: cover;
            color: {text};
        }}
        """

    st.markdown(
        f"""
        <style>
        {background_css}
        .block-container {{
            padding-top: 1rem;
            padding-bottom: 2.5rem;
            max-width: 1180px;
        }}
        #MainMenu,
        footer,
        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        .stDeployButton {{
            display: none !important;
            height: 0 !important;
            visibility: hidden !important;
        }}
        .stApp, .stMarkdown, p, label, h1, h2, h3 {{
            color: {text} !important;
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", "Segoe UI", sans-serif;
            letter-spacing: 0;
        }}
        h1 {{
            font-weight: 950 !important;
        }}
        h2, h3 {{
            font-weight: 900 !important;
        }}
        div[data-testid="stTabs"] button p {{
            color: {text} !important;
        }}
        div[data-testid="stTabs"] button[aria-selected="true"] p {{
            color: {text} !important;
            font-weight: 900;
        }}
        div[data-testid="stTabs"] [data-baseweb="tab-list"] {{
            gap: 0.25rem;
        }}
        div[data-testid="stTabs"] button {{
            border-radius: 999px 999px 0 0;
            padding-left: 0.75rem;
            padding-right: 0.75rem;
        }}
        div[data-baseweb="input"] input,
        div[data-baseweb="base-input"],
        div[data-baseweb="select"] > div,
        div[data-baseweb="select"] div,
        div[data-baseweb="textarea"],
        textarea {{
            background: {widget_bg} !important;
            border-color: {widget_border} !important;
            color: {widget_text} !important;
        }}
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] svg,
        div[data-baseweb="input"] svg {{
            color: {widget_text} !important;
            fill: {widget_text} !important;
        }}
        div[data-baseweb="popover"],
        div[data-baseweb="popover"] ul,
        div[role="listbox"],
        div[role="option"] {{
            background: {widget_bg} !important;
            color: {widget_text} !important;
        }}
        div[role="option"] div,
        div[role="option"] span {{
            color: {widget_text} !important;
        }}
        div[role="radiogroup"] label,
        div[role="radiogroup"] p,
        div[role="radiogroup"] span {{
            color: {text} !important;
        }}
        div[data-testid="stButtonGroup"] {{
            margin-bottom: 0.75rem;
        }}
        div[data-testid="stButtonGroup"] button {{
            background: {widget_bg} !important;
            border: 1px solid {widget_border} !important;
            border-radius: 999px !important;
            color: {text} !important;
            font-size: 1rem;
            font-weight: 900;
            min-height: 3rem;
            padding: 0.55rem 1.15rem;
        }}
        div[data-testid="stButtonGroup"] button *,
        div[data-testid="stButtonGroup"] button p {{
            color: inherit !important;
        }}
        div[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] {{
            background: #ff465c !important;
            border-color: #ff465c !important;
            color: #ffffff !important;
        }}
        .player-strip-label {{
            color: #713f12;
            font-size: 0.72rem;
            font-weight: 950;
            padding-top: 0.15rem;
            text-align: center;
            text-transform: uppercase;
        }}
        .carousel-player-name {{
            font-size: 0.86rem;
            font-weight: 950;
            line-height: 1.1;
            margin: 0.34rem 0 0;
            overflow-wrap: anywhere;
            text-align: center;
            text-shadow: 0 1px 0 rgba(255, 255, 255, 0.72);
        }}
        .carousel-player-badge {{
            color: #334155;
            font-size: 0.75rem;
            font-weight: 800;
            line-height: 1.1;
            margin-bottom: 0.25rem;
            text-align: center;
        }}
        .carousel-player-badge.is-selected {{
            color: #166534;
        }}
        .carousel-avatar {{
            border-radius: 7px;
            display: block;
            margin: 0 auto;
            object-fit: cover;
            outline: 2px solid rgba(255, 255, 255, 0.78);
        }}
        .carousel-avatar-placeholder,
        .photo-placeholder {{
            align-items: center;
            background: {placeholder_bg};
            border: 2px dashed #a3a3a3;
            border-radius: 999px;
            color: {placeholder_text};
            display: flex;
            font-size: 1.1rem;
            font-weight: 950;
            justify-content: center;
        }}
        .carousel-avatar-placeholder {{
            border-radius: 7px;
            margin: 0 auto;
        }}
        .photo-placeholder {{
            border-radius: 8px;
        }}
        .st-key-game_night_player_picker,
        .st-key-player_page_player_picker {{
            margin: 0.75rem 0 1.25rem;
            overflow: visible;
            padding-bottom: 0.35rem;
        }}
        .st-key-game_night_player_picker > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"],
        .st-key-player_page_player_picker > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] {{
            align-items: center;
            flex-wrap: nowrap !important;
            gap: 0.75rem;
        }}
        .st-key-game_night_player_bus,
        .st-key-player_page_player_bus {{
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.42), rgba(255, 255, 255, 0) 32%),
                linear-gradient(90deg, #f59e0b, #facc15 22%, #fbbf24 78%, #f59e0b);
            border: 3px solid #111827;
            border-bottom-width: 6px;
            border-radius: 8px 8px 14px 14px;
            box-shadow: 0 16px 38px rgba(0, 0, 0, 0.34);
            margin-bottom: 0;
            overflow-x: auto;
            overflow-y: visible;
            padding: 0.9rem 0.7rem 1.35rem;
            position: relative;
            scrollbar-width: thin;
            touch-action: pan-x;
            -webkit-overflow-scrolling: touch;
        }}
        .st-key-game_night_player_bus::before,
        .st-key-game_night_player_bus::after,
        .st-key-player_page_player_bus::before,
        .st-key-player_page_player_bus::after {{
            display: none;
        }}
        .bus-wheels {{
            display: flex;
            height: 3.2rem;
            justify-content: space-between;
            margin: -1.55rem 1.55rem 1.15rem;
            pointer-events: none;
            position: relative;
            z-index: 4;
        }}
        .bus-wheels span {{
            animation: busWheelSpin 1.1s linear infinite;
            background:
                radial-gradient(circle at center, #94a3b8 0 12%, #0f172a 13% 42%, #020617 43% 57%, #64748b 58% 67%, #111827 68%);
            border: 5px solid #111827;
            border-radius: 999px;
            box-shadow: 0 10px 18px rgba(0, 0, 0, 0.28);
            height: 3.1rem;
            width: 3.1rem;
        }}
        @keyframes busWheelSpin {{
            to {{
                transform: rotate(360deg);
            }}
        }}
        @media (prefers-reduced-motion: reduce) {{
            .bus-wheels span {{
                animation: none;
            }}
        }}
        .st-key-game_night_player_bus div[data-testid="stHorizontalBlock"],
        .st-key-player_page_player_bus div[data-testid="stHorizontalBlock"] {{
            align-items: stretch;
            flex-wrap: nowrap !important;
            gap: 0.55rem;
            min-width: max-content;
            padding-bottom: 0.15rem;
        }}
        .st-key-game_night_player_bus div[data-testid="stColumn"],
        .st-key-player_page_player_bus div[data-testid="stColumn"] {{
            flex: 0 0 7.25rem !important;
            min-width: 7.25rem !important;
            width: 7.25rem !important;
        }}
        [class*="st-key-game_night_player_tile_"],
        [class*="st-key-player_page_player_tile_"] {{
            background: linear-gradient(180deg, #dff6ff, #bde7f7);
            border: 2px solid #111827;
            border-radius: 7px;
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.7);
            cursor: pointer;
            min-height: 7.55rem;
            padding: 0.38rem 0.35rem 0.35rem;
            position: relative;
        }}
        [class*="st-key-game_night_player_tile_"] .carousel-avatar,
        [class*="st-key-game_night_player_tile_"] .carousel-avatar-placeholder,
        [class*="st-key-player_page_player_tile_"] .carousel-avatar,
        [class*="st-key-player_page_player_tile_"] .carousel-avatar-placeholder {{
            cursor: pointer;
        }}
        [class*="st-key-game_night_player_"][data-testid="stElementContainer"],
        [class*="st-key-player_page_player_"][data-testid="stElementContainer"] {{
            height: 0;
            left: 50%;
            overflow: visible;
            position: absolute;
            top: 0.32rem;
            transform: translateX(-50%);
            width: 78px;
            z-index: 5;
        }}
        [class*="st-key-game_night_player_tile_"] div[data-testid="stButton"] button,
        [class*="st-key-player_page_player_tile_"] div[data-testid="stButton"] button {{
            background: transparent !important;
            border: 0 !important;
            border-radius: 7px;
            box-shadow: none !important;
            color: transparent !important;
            cursor: pointer;
            height: 78px;
            min-height: 78px;
            opacity: 0;
            padding: 0;
            width: 78px;
        }}
        [class*="st-key-game_night_player_tile_"] div[data-testid="stButton"] button *,
        [class*="st-key-player_page_player_tile_"] div[data-testid="stButton"] button * {{
            color: transparent !important;
        }}
        div[data-testid="stButton"] button {{
            background: {widget_bg} !important;
            border: 1px solid {widget_border} !important;
            border-radius: 8px;
            color: {widget_text} !important;
            font-weight: 800;
            white-space: normal;
        }}
        div[data-testid="stButton"] button p {{
            color: {widget_text} !important;
        }}
        div[data-testid="stButton"] button *,
        div[data-testid="stDownloadButton"] button *,
        div[data-testid="stFormSubmitButton"] button * {{
            color: inherit !important;
        }}
        div[data-testid="stButton"] button:disabled {{
            background: {disabled_bg} !important;
            border-color: {widget_border} !important;
            color: {disabled_text} !important;
            opacity: 1 !important;
        }}
        div[data-testid="stButton"] button:disabled p {{
            color: {disabled_text} !important;
        }}
        [class*="st-key-game_night_player_tile_"] div[data-testid="stButton"] button:disabled,
        [class*="st-key-player_page_player_tile_"] div[data-testid="stButton"] button:disabled {{
            background: transparent !important;
            border: 0 !important;
            color: transparent !important;
            cursor: default;
            opacity: 0 !important;
        }}
        [class*="st-key-game_night_player_tile_"] div[data-testid="stButton"] button:disabled *,
        [class*="st-key-player_page_player_tile_"] div[data-testid="stButton"] button:disabled * {{
            color: transparent !important;
        }}
        div[data-testid="stFormSubmitButton"] button[kind="primary"],
        div[data-testid="stButton"] button[kind="primary"] {{
            font-size: 1.05rem;
            font-weight: 800;
            min-height: 3rem;
        }}
        div[data-testid="stDownloadButton"] button,
        div[data-testid="stNumberInput"] button,
        div[data-testid="stFormSubmitButton"] button {{
            background: {widget_bg} !important;
            border-color: {widget_border} !important;
            color: {widget_text} !important;
        }}
        div[data-testid="stNumberInput"] input {{
            background: {widget_bg} !important;
            color: {widget_text} !important;
        }}
        div[data-testid="stExpander"] details {{
            background: {panel} !important;
            border: 1px solid {panel_border} !important;
            border-radius: 8px !important;
            color: {text} !important;
        }}
        div[data-testid="stExpander"] summary,
        div[data-testid="stExpander"] summary * {{
            color: {text} !important;
        }}
        div[data-testid="stMetric"] {{
            background: {panel};
            border: 1px solid {panel_border};
            border-radius: 8px;
            padding: 0.75rem;
        }}
        [data-testid="stMetric"] label,
        [data-testid="stMetric"] [data-testid="stMetricLabel"],
        [data-testid="stMetric"] [data-testid="stMetricValue"],
        [data-testid="stMetric"] p {{
            color: {text} !important;
        }}
        [data-testid="stMetric"] label,
        [data-testid="stMetric"] [data-testid="stMetricLabel"] {{
            opacity: 0.78;
        }}
        div[data-testid="stFileUploader"] {{
            width: 112px;
        }}
        div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] {{
            align-items: center;
            background: {placeholder_bg};
            border: 2px dashed #a3a3a3;
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            height: 112px;
            justify-content: center;
            min-height: 112px;
            padding: 0;
            position: relative;
            width: 112px;
        }}
        div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"]::before {{
            color: {placeholder_text};
            content: "+";
            font-size: 2rem;
            font-weight: 800;
            line-height: 1;
        }}
        div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] > div {{
            display: none;
        }}
        div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] button {{
            cursor: pointer;
            height: 112px;
            inset: 0;
            opacity: 0;
            position: absolute;
            width: 112px;
        }}
        [class*="st-key-player_page_photo_click_"],
        [class*="st-key-roster_photo_click_"] {{
            margin: 0 auto;
            max-width: 9rem;
            position: relative;
            text-align: center;
        }}
        .profile-photo-click-target {{
            background:
                radial-gradient(circle at 25% 20%, rgba(125, 211, 252, 0.26), transparent 35%),
                linear-gradient(135deg, #111827, #0f172a);
            border: 1px solid rgba(125, 211, 252, 0.32);
            border-radius: 14px;
            box-shadow: 0 14px 34px rgba(0, 0, 0, 0.32);
            color: #e2e8f0;
            cursor: pointer;
            display: flex;
            font-size: 2rem;
            font-weight: 950;
            justify-content: center;
            object-fit: cover;
            position: relative;
            z-index: 1;
        }}
        .profile-photo-click-target.is-empty {{
            align-items: center;
            border-style: solid;
        }}
        [class*="st-key-player_page_photo_click_"] div[data-testid="stCaptionContainer"],
        [class*="st-key-roster_photo_click_"] div[data-testid="stCaptionContainer"] {{
            pointer-events: none;
        }}
        [class*="st-key-player_page_photo_click_"] div[data-testid="stFileUploader"],
        [class*="st-key-roster_photo_click_"] div[data-testid="stFileUploader"] {{
            display: block;
            left: 0 !important;
            margin: 0;
            opacity: 0;
            overflow: hidden;
            position: absolute;
            top: 0;
            z-index: 5;
        }}
        [class*="st-key-player_page_photo_click_"] div[data-testid="stFileUploader"] {{
            transform: translateY(-132px);
        }}
        [class*="st-key-roster_photo_click_"] div[data-testid="stFileUploader"] {{
            transform: translateY(-104px);
        }}
        [class*="st-key-player_page_photo_click_"] div[data-testid="stFileUploader"] label,
        [class*="st-key-roster_photo_click_"] div[data-testid="stFileUploader"] label {{
            display: none;
        }}
        [class*="st-key-player_page_photo_click_"] div[data-testid="stFileUploader"],
        [class*="st-key-player_page_photo_click_"] div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"],
        [class*="st-key-player_page_photo_click_"] div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] button {{
            height: 132px;
            min-height: 132px;
            width: 132px;
        }}
        [class*="st-key-roster_photo_click_"] div[data-testid="stFileUploader"],
        [class*="st-key-roster_photo_click_"] div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"],
        [class*="st-key-roster_photo_click_"] div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] button {{
            height: 104px;
            min-height: 104px;
            width: 104px;
        }}
        [class*="st-key-player_page_photo_click_"] div[data-testid="stCaptionContainer"] p,
        [class*="st-key-roster_photo_click_"] div[data-testid="stCaptionContainer"] p {{
            color: {muted} !important;
            font-size: 0.74rem;
            line-height: 1.15;
            margin-top: 0.35rem;
        }}
        [class*="st-key-player_page_photo_click_"] div[data-testid="stButton"] button,
        [class*="st-key-roster_photo_click_"] div[data-testid="stButton"] button {{
            border-radius: 999px;
            font-size: 0.72rem;
            min-height: 1.85rem;
            padding: 0.2rem 0.5rem;
        }}
        [class*="st-key-player_profile_summary_"] {{
            background:
                linear-gradient(135deg, rgba(34, 197, 94, 0.12), rgba(14, 165, 233, 0.08)),
                {panel};
        }}
        [class*="st-key-roster_card_"] {{
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.05), transparent),
                {panel};
            min-height: 22rem;
        }}
        [class*="st-key-stat_entry_fields_"] div[data-testid="stHorizontalBlock"] {{
            align-items: end;
            flex-wrap: nowrap !important;
            gap: 0.75rem;
        }}
        [class*="st-key-stat_entry_fields_"] div[data-testid="stNumberInput"] input {{
            min-width: 0;
            text-align: center;
        }}
        [class*="st-key-stat_entry_fields_"] div[data-testid="stNumberInput"] button {{
            width: 1.7rem;
            min-width: 1.7rem;
        }}
        [class*="st-key-bulk_game_stepper_table_"] {{
            background: {table_bg};
            border: 1px solid {panel_border};
            border-radius: 10px;
            overflow-x: auto;
            padding: 0.35rem;
            scrollbar-width: thin;
        }}
        [class*="st-key-bulk_game_stepper_table_"] div[data-testid="stHorizontalBlock"] {{
            align-items: center;
            flex-wrap: nowrap !important;
            gap: 0.35rem;
            min-width: 88rem;
        }}
        [class*="st-key-bulk_game_stepper_table_"] div[data-testid="stColumn"] {{
            flex: 0 0 7.2rem !important;
            min-width: 7.2rem !important;
            width: 7.2rem !important;
        }}
        [class*="st-key-bulk_game_stepper_table_"] div[data-testid="stColumn"]:first-child {{
            background: {table_bg};
            border-right: 1px solid {panel_border};
            flex-basis: 7.5rem !important;
            left: 0;
            min-height: 3rem;
            min-width: 7.5rem !important;
            padding: 0.35rem 0.45rem;
            position: sticky;
            width: 7.5rem !important;
            z-index: 6;
        }}
        [class*="st-key-bulk_game_stepper_table_"] div[data-testid="stColumn"]:nth-child(2) {{
            flex-basis: 4.8rem !important;
            min-width: 4.8rem !important;
            width: 4.8rem !important;
        }}
        [class*="st-key-bulk_game_stepper_table_"] div[data-testid="stMarkdownContainer"] p,
        [class*="st-key-bulk_game_stepper_table_"] div[data-testid="stMarkdownContainer"] strong {{
            color: {table_text} !important;
        }}
        [class*="st-key-bulk_game_stepper_table_"] div[data-testid="stNumberInput"] input {{
            min-width: 2.1rem;
            padding-left: 0.1rem;
            padding-right: 0.1rem;
            text-align: center;
        }}
        [class*="st-key-bulk_game_stepper_table_"] div[data-testid="stNumberInput"] button {{
            width: 1rem;
            min-width: 1rem;
            padding-left: 0;
            padding-right: 0;
        }}
        [class*="st-key-bulk_stepper_"] div[data-testid="stHorizontalBlock"] {{
            gap: 0.08rem;
            min-width: 0 !important;
        }}
        [class*="st-key-bulk_stepper_"] div[data-testid="stColumn"],
        [class*="st-key-bulk_stepper_"] div[data-testid="stColumn"]:first-child {{
            background: transparent;
            border-right: 0;
            flex: 1 1 0 !important;
            left: auto;
            min-height: 0;
            min-width: 0 !important;
            padding: 0;
            position: static;
            width: auto !important;
            z-index: auto;
        }}
        [class*="st-key-bulk_stepper_"] div[data-testid="stButton"] button {{
            background: {widget_bg} !important;
            color: {widget_text} !important;
            border-radius: 7px;
            font-size: 0.95rem;
            font-weight: 950;
            min-height: 2.45rem;
            padding: 0;
        }}
        [class*="st-key-bulk_stepper_"] div[data-testid="stButton"] button p {{
            color: {widget_text} !important;
        }}
        [class*="st-key-bulk_stepper_"] div[data-testid="stNumberInput"] input {{
            background: {widget_bg} !important;
            border-radius: 7px;
            color: {widget_text} !important;
            min-height: 2.45rem;
        }}
        [class*="st-key-custom_stat_builder_controls"] div[data-testid="stHorizontalBlock"] {{
            align-items: end;
            gap: 0.65rem;
        }}
        [class*="st-key-custom_stat_builder_controls"] div[data-testid="stButton"] button {{
            min-height: 2.45rem;
        }}
        div[data-testid="stDataFrame"] {{
            border: 1px solid {panel_border};
            border-radius: 8px;
            overflow: hidden;
        }}
        div[data-testid="stDataFrame"] [role="grid"],
        div[data-testid="stDataFrame"] [role="columnheader"],
        div[data-testid="stDataFrame"] [role="row"],
        div[data-testid="stDataFrame"] [role="gridcell"] {{
            background: {table_bg} !important;
            color: {table_text} !important;
        }}
        div[data-testid="stDataFrame"] [role="columnheader"] {{
            background: {table_header} !important;
            color: {table_text} !important;
        }}
        div[data-testid="stDataFrame"] canvas {{
            background: {table_bg} !important;
        }}
        @media (max-width: 760px) {{
            .block-container {{
                padding-left: 0.8rem;
                padding-right: 0.8rem;
                padding-top: 0.8rem;
            }}
            .player-strip-label {{
                font-size: 0.72rem;
                padding-top: 0.45rem;
            }}
            .carousel-player-name {{
                font-size: 0.78rem;
            }}
            .carousel-player-badge {{
                font-size: 0.68rem;
            }}
            .st-key-game_night_player_picker,
            .st-key-player_page_player_picker {{
                margin-left: -0.1rem;
                margin-right: -0.1rem;
            }}
            .st-key-game_night_player_picker > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"],
            .st-key-player_page_player_picker > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] {{
                gap: 0.5rem;
            }}
            .st-key-game_night_player_bus,
            .st-key-player_page_player_bus {{
                padding-left: 0.45rem;
                padding-right: 0.45rem;
            }}
            .bus-wheels {{
                margin-left: 1rem;
                margin-right: 1rem;
            }}
            .bus-wheels span {{
                height: 2.7rem;
                width: 2.7rem;
            }}
            .st-key-game_night_player_picker > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child,
            .st-key-game_night_player_picker > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:last-child,
            .st-key-player_page_player_picker > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child,
            .st-key-player_page_player_picker > div[data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:last-child {{
                flex-basis: 2.8rem !important;
                min-width: 2.8rem !important;
                width: 2.8rem !important;
            }}
            .st-key-game_night_player_bus div[data-testid="stColumn"],
            .st-key-player_page_player_bus div[data-testid="stColumn"] {{
                flex: 0 0 5rem !important;
                min-width: 5rem !important;
                width: 5rem !important;
            }}
            [class*="st-key-game_night_player_tile_"],
            [class*="st-key-player_page_player_tile_"] {{
                min-height: 6.55rem;
                padding: 0.25rem 0.22rem;
            }}
            [class*="st-key-game_night_player_tile_"] .carousel-avatar,
            [class*="st-key-game_night_player_tile_"] .carousel-avatar-placeholder,
            [class*="st-key-player_page_player_tile_"] .carousel-avatar,
            [class*="st-key-player_page_player_tile_"] .carousel-avatar-placeholder {{
                height: 62px !important;
                width: 62px !important;
            }}
            [class*="st-key-game_night_player_"][data-testid="stElementContainer"],
            [class*="st-key-player_page_player_"][data-testid="stElementContainer"] {{
                width: 62px;
            }}
            [class*="st-key-game_night_player_tile_"] div[data-testid="stButton"] button,
            [class*="st-key-player_page_player_tile_"] div[data-testid="stButton"] button {{
                height: 62px;
                min-height: 62px;
                width: 62px;
            }}
            div[data-testid="stButton"] button {{
                font-size: 0.72rem;
                min-height: 2.2rem;
                padding-left: 0.2rem;
                padding-right: 0.2rem;
            }}
            div[data-testid="stMetric"] {{
                padding: 0.5rem;
            }}
            div[data-testid="stMetric"] label,
            div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
                font-size: 0.85rem;
            }}
            div[data-testid="stFileUploader"],
            div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"],
            div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] button {{
                height: 92px;
                min-height: 92px;
                width: 92px;
            }}
            .photo-placeholder {{
                max-height: 92px;
                max-width: 92px;
            }}
            [class*="st-key-stat_entry_fields_"] {{
                overflow-x: auto;
                padding-bottom: 0.2rem;
            }}
            [class*="st-key-stat_entry_fields_"] div[data-testid="stHorizontalBlock"] {{
                gap: 0.2rem;
                min-width: 18.2rem;
            }}
            [class*="st-key-stat_entry_fields_"] div[data-testid="stColumn"] {{
                flex: 0 0 3.38rem !important;
                min-width: 3.38rem !important;
                width: 3.38rem !important;
            }}
            [class*="st-key-stat_entry_fields_"] label p {{
                font-size: 0.68rem;
            }}
            [class*="st-key-stat_entry_fields_"] div[data-testid="stNumberInput"] input {{
                font-size: 0.88rem;
                padding-left: 0.15rem;
                padding-right: 0.15rem;
            }}
            [class*="st-key-stat_entry_fields_"] div[data-testid="stNumberInput"] button {{
                width: 1rem;
                min-width: 1rem;
                padding-left: 0;
                padding-right: 0;
            }}
            [class*="st-key-bulk_game_stepper_table_"] div[data-testid="stHorizontalBlock"] {{
                min-width: 84rem;
            }}
            [class*="st-key-roster_card_"] {{
                min-height: 20rem;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    init_db()
    background_date = active_background_date()
    background_key = night_background_key(background_date)
    inject_css(background_data_url(background_key, background_date))

    players = get_players()
    header_cols = st.columns([5, 1])
    with header_cols[0]:
        st.title(APP_TITLE)
        st.caption("Shared box scores for pickup nights.")
    with header_cols[1]:
        render_theme_toggle()
    render_storage_warning()

    tab_game, tab_player, tab_summary, tab_leaderboard, tab_backgrounds, tab_roster = st.tabs(
        ["Game Night", "Player Page", "Nightly Summary", "Leaderboards", "Backgrounds", "Roster"]
    )
    with tab_game:
        render_game_night(players)
    with tab_player:
        render_player_page(players)
    with tab_summary:
        render_nightly_summary()
    with tab_leaderboard:
        render_leaderboard()
    with tab_backgrounds:
        render_backgrounds()
    with tab_roster:
        render_roster(players)


if __name__ == "__main__":
    main()
