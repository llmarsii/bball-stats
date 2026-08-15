from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st


APP_TITLE = "Pickup Stat Tracker"
DB_PATH = Path("data") / "basketball_stats.sqlite3"
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
    "rebounds": "REB",
    "assists": "AST",
    "steals": "STL",
    "blocks": "BLK",
    "threes": "3PM",
    "turnovers": "TO",
}


st.set_page_config(
    page_title=APP_TITLE,
    page_icon=":basketball:",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                photo_blob BLOB,
                photo_mime TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS game_stats (
                game_date TEXT NOT NULL,
                player_id INTEGER NOT NULL REFERENCES players(id),
                result TEXT NOT NULL DEFAULT '',
                points INTEGER NOT NULL DEFAULT 0,
                rebounds INTEGER NOT NULL DEFAULT 0,
                assists INTEGER NOT NULL DEFAULT 0,
                steals INTEGER NOT NULL DEFAULT 0,
                blocks INTEGER NOT NULL DEFAULT 0,
                threes INTEGER NOT NULL DEFAULT 0,
                turnovers INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (game_date, player_id)
            )
            """
        )
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


def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.environ.get(name, default))


def require_password() -> bool:
    configured_password = get_secret("APP_PASSWORD", "hoops")
    if st.session_state.get("authenticated"):
        return True

    st.title(APP_TITLE)
    st.caption("Private group access")
    with st.form("login_form"):
        password = st.text_input("Group password", type="password")
        submitted = st.form_submit_button("Enter")

    if submitted:
        if password == configured_password:
            st.session_state.authenticated = True
            st.rerun()
        st.error("That password did not match.")

    if configured_password == "hoops":
        st.info(
            "Local default password is `hoops`. Set `APP_PASSWORD` in Streamlit "
            "secrets before sharing the deployed app."
        )
    return False


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
    return [dict(row) for row in rows]


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


def stats_for_date(game_date: date) -> dict[int, dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM game_stats
            WHERE game_date = ?
            """,
            (game_date.isoformat(),),
        ).fetchall()
    return {row["player_id"]: dict(row) for row in rows}


def save_stat_line(game_date: date, player_id: int, values: dict) -> None:
    now = datetime.utcnow().isoformat()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO game_stats (
                game_date, player_id, result, points, rebounds, assists,
                steals, blocks, threes, turnovers, notes, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_date, player_id) DO UPDATE SET
                result = excluded.result,
                points = excluded.points,
                rebounds = excluded.rebounds,
                assists = excluded.assists,
                steals = excluded.steals,
                blocks = excluded.blocks,
                threes = excluded.threes,
                turnovers = excluded.turnovers,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (
                game_date.isoformat(),
                player_id,
                values["result"],
                values["points"],
                values["rebounds"],
                values["assists"],
                values["steals"],
                values["blocks"],
                values["threes"],
                values["turnovers"],
                values["notes"],
                now,
            ),
        )


@st.cache_data(ttl=2)
def all_stats() -> pd.DataFrame:
    with db() as conn:
        df = pd.read_sql_query(
            """
            SELECT
                gs.game_date,
                p.name,
                p.id AS player_id,
                gs.result,
                gs.points,
                gs.rebounds,
                gs.assists,
                gs.steals,
                gs.blocks,
                gs.threes,
                gs.turnovers,
                gs.notes,
                gs.updated_at
            FROM game_stats gs
            JOIN players p ON p.id = gs.player_id
            ORDER BY gs.game_date DESC, p.sort_order, p.id
            """,
            conn,
        )
    return df


def stat_input(label: str, key: str, value: int) -> int:
    return int(
        st.number_input(
            label,
            min_value=0,
            max_value=200,
            value=int(value or 0),
            step=1,
            key=key,
        )
    )


def format_game_date(game_date: date) -> str:
    return f"{game_date:%b} {game_date.day}, {game_date:%Y}"


def render_photo(player: dict, size: int = 96) -> None:
    if player.get("photo_blob"):
        st.image(player["photo_blob"], width=size)
        return
    st.markdown(
        f"""
        <div class="photo-placeholder" style="width:{size}px;height:{size}px;">
            +
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_game_night(players: list[dict]) -> None:
    st.subheader("Game Night")
    game_date = st.date_input("Playing date", value=date.today())
    existing_stats = stats_for_date(game_date)

    st.caption("Upload or replace profile photos next to names, then enter the stat line for the selected date.")

    for player in players:
        stats = existing_stats.get(player["id"], {})
        with st.container(border=True):
            top_cols = st.columns([1, 3, 2])
            with top_cols[0]:
                render_photo(player, size=92)
            with top_cols[1]:
                st.markdown(f"### {player['name']}")
                uploaded = st.file_uploader(
                    "+ profile photo",
                    type=["png", "jpg", "jpeg", "webp"],
                    key=f"photo_{player['id']}",
                )
                if uploaded is not None:
                    update_player_photo(player["id"], uploaded.getvalue(), uploaded.type)
                    st.success("Photo saved.")
                    st.rerun()
            with top_cols[2]:
                result_options = ["", "W", "L"]
                current_result = stats.get("result", "")
                result_index = result_options.index(current_result) if current_result in result_options else 0
                result = st.radio(
                    "Team result",
                    options=result_options,
                    index=result_index,
                    horizontal=True,
                    format_func=lambda option: "Unset" if option == "" else option,
                    key=f"result_{game_date}_{player['id']}",
                )

            stat_cols = st.columns(7)
            stat_values = {"result": result}
            for index, (field, label) in enumerate(STAT_FIELDS.items()):
                with stat_cols[index]:
                    stat_values[field] = stat_input(
                        label,
                        f"{field}_{game_date}_{player['id']}",
                        stats.get(field, 0),
                    )
            stat_values["notes"] = st.text_input(
                "Notes",
                value=stats.get("notes", ""),
                key=f"notes_{game_date}_{player['id']}",
                placeholder="Optional",
            )

            if st.button("Save stat line", key=f"save_{game_date}_{player['id']}", use_container_width=True):
                save_stat_line(game_date, player["id"], stat_values)
                all_stats.clear()
                st.success(f"Saved {player['name']} for {format_game_date(game_date)}.")


def render_leaderboard() -> None:
    st.subheader("Leaderboards")
    df = all_stats()
    if df.empty:
        st.info("No stat lines have been saved yet.")
        return

    completed = df[df["result"].isin(["W", "L"])].copy()
    if completed.empty:
        st.info("Saved rows need W/L results before standings can be calculated.")
        st.dataframe(df, use_container_width=True, hide_index=True)
        return

    grouped = completed.groupby("name", as_index=False).agg(
        GP=("game_date", "nunique"),
        W=("result", lambda values: int((values == "W").sum())),
        L=("result", lambda values: int((values == "L").sum())),
        PTS=("points", "sum"),
        REB=("rebounds", "sum"),
        AST=("assists", "sum"),
        STL=("steals", "sum"),
        BLK=("blocks", "sum"),
        THREES=("threes", "sum"),
        TO=("turnovers", "sum"),
    )
    grouped["WIN%"] = (grouped["W"] / grouped["GP"]).round(3)
    grouped["PPG"] = (grouped["PTS"] / grouped["GP"]).round(1)
    grouped["RPG"] = (grouped["REB"] / grouped["GP"]).round(1)
    grouped["APG"] = (grouped["AST"] / grouped["GP"]).round(1)
    grouped = grouped.sort_values(["W", "WIN%", "PPG"], ascending=False)

    metric_cols = st.columns(4)
    metric_cols[0].metric("Stat lines", len(df))
    metric_cols[1].metric("Game nights", df["game_date"].nunique())
    metric_cols[2].metric("Total points", int(df["points"].sum()))
    metric_cols[3].metric("Photos", sum(1 for player in get_players() if player.get("photo_blob")))

    st.dataframe(grouped, use_container_width=True, hide_index=True)

    with st.expander("All saved stat lines"):
        display_df = df.rename(columns={"threes": "3PM", "turnovers": "TO"})
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download CSV",
            data=df.to_csv(index=False),
            file_name="pickup_basketball_stats.csv",
            mime="text/csv",
        )


def render_roster(players: list[dict]) -> None:
    st.subheader("Roster")
    st.caption("Rename the seven player slots and manage profile photos.")

    for player in players:
        with st.container(border=True):
            cols = st.columns([1, 4, 2])
            with cols[0]:
                render_photo(player, size=84)
            with cols[1]:
                new_name = st.text_input(
                    "Player name",
                    value=player["name"],
                    key=f"name_{player['id']}",
                )
                if st.button("Save name", key=f"rename_{player['id']}"):
                    update_player_name(player["id"], new_name)
                    st.success("Name saved.")
                    st.rerun()
            with cols[2]:
                if player.get("photo_blob") and st.button("Remove photo", key=f"remove_photo_{player['id']}"):
                    remove_player_photo(player["id"])
                    st.success("Photo removed.")
                    st.rerun()


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.6rem;
            padding-bottom: 2.5rem;
            max-width: 1100px;
        }
        .photo-placeholder {
            align-items: center;
            background: #f3f4f6;
            border: 2px dashed #a3a3a3;
            border-radius: 8px;
            color: #737373;
            display: flex;
            font-size: 2rem;
            font-weight: 700;
            justify-content: center;
        }
        [data-testid="stMetric"] {
            background: #fafafa;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 0.75rem;
        }
        h1, h2, h3 {
            letter-spacing: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    init_db()
    inject_css()
    if not require_password():
        return

    players = get_players()
    header_cols = st.columns([3, 1])
    with header_cols[0]:
        st.title(APP_TITLE)
        st.caption("Shared box scores for pickup nights.")
    with header_cols[1]:
        if st.button("Log out", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()

    tab_game, tab_leaderboard, tab_roster = st.tabs(["Game Night", "Leaderboards", "Roster"])
    with tab_game:
        render_game_night(players)
    with tab_leaderboard:
        render_leaderboard()
    with tab_roster:
        render_roster(players)


if __name__ == "__main__":
    main()
