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
}
PLAYER_NIGHT_COLUMNS = {
    "game_date": "Date",
    **NIGHTLY_TOTAL_COLUMNS,
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


def ensure_game_stats_schema(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]: row for row in conn.execute("PRAGMA table_info(game_stats)").fetchall()
    }
    migrations = {
        "field_goals_made": "INTEGER NOT NULL DEFAULT 0",
        "field_goals_attempted": "INTEGER NOT NULL DEFAULT 0",
        "three_attempts": "INTEGER NOT NULL DEFAULT 0",
    }
    for column, definition in migrations.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE game_stats ADD COLUMN {column} {definition}")

    columns = {
        row["name"]: row for row in conn.execute("PRAGMA table_info(game_stats)").fetchall()
    }
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
        create_game_stats_table(conn)
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
    return [dict(row) for row in rows]


def stats_by_game(game_date: date, player_id: int) -> dict[int, dict]:
    return {
        row["game_number"]: row
        for row in stats_for_date(game_date)
        if row["player_id"] == player_id
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


@st.cache_data(ttl=2)
def all_stats() -> pd.DataFrame:
    with db() as conn:
        df = pd.read_sql_query(
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


def selected_player_id(players: list[dict]) -> int:
    try:
        requested_id = int(st.query_params.get("player_id", players[0]["id"]))
    except (TypeError, ValueError):
        requested_id = players[0]["id"]

    player_ids = {player["id"] for player in players}
    return requested_id if requested_id in player_ids else players[0]["id"]


def render_player_picker(
    players: list[dict],
    current_player_id: int,
    player_badges: dict[int, str],
    scope: str,
) -> None:
    cols = st.columns(len(players))
    for index, player in enumerate(players):
        with cols[index]:
            render_photo(player, size=86)
            if player_badges.get(player["id"]):
                st.caption(player_badges[player["id"]])
            button_label = f"Selected: {player['name']}" if player["id"] == current_player_id else player["name"]
            if st.button(button_label, key=f"{scope}_pick_{player['id']}", use_container_width=True):
                st.query_params["player_id"] = str(player["id"])
                st.rerun()


def add_percentages(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if result.empty:
        return result
    result["fg_pct"] = result.apply(
        lambda row: round(row["field_goals_made"] / row["field_goals_attempted"], 3)
        if row["field_goals_attempted"]
        else None,
        axis=1,
    )
    result["three_pct"] = result.apply(
        lambda row: round(row["threes"] / row["three_attempts"], 3)
        if row["three_attempts"]
        else None,
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
    return add_percentages(grouped)


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


def render_photo_upload_control(player: dict, key: str, size: int = 112) -> object | None:
    if player.get("photo_blob"):
        render_photo(player, size=size)
        st.caption("Tap + to replace")
    return st.file_uploader(
        "+ profile photo",
        type=["png", "jpg", "jpeg", "webp"],
        key=key,
        label_visibility="collapsed",
    )


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
        save_stat_line(game_date, game_number, player["id"], stat_values)
        all_stats.clear()
        st.session_state[f"editing_{game_date}_{game_number}_{player['id']}"] = False
        st.session_state[f"selected_game_{game_date}_{player['id']}"] = next_game_number(game_date, player["id"])
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

    if st.button("Edit Game Stats", key=f"edit_{game_date}_{game_number}_{player['id']}", type="primary", use_container_width=True):
        st.session_state[f"editing_{game_date}_{game_number}_{player['id']}"] = True
        st.rerun()


def render_game_night(players: list[dict]) -> None:
    st.subheader("Game Night")
    game_date = st.date_input("Playing date", value=date.today())
    player_badges = game_counts_for_date(game_date)
    current_player_id = selected_player_id(players)
    current_player = next(player for player in players if player["id"] == current_player_id)
    player_games = stats_by_game(game_date, current_player_id)
    next_game = max(player_games.keys(), default=0) + 1
    game_options = sorted(player_games.keys()) + [next_game]
    game_key = f"selected_game_{game_date}_{current_player_id}"
    if st.session_state.get(game_key) not in game_options:
        st.session_state[game_key] = next_game

    st.caption("Pick your photo/name from the row, enter one game at a time, then save. The next game opens automatically.")
    render_player_picker(players, current_player_id, player_badges, scope="game_night")

    with st.container(border=True):
        top_cols = st.columns([1, 4])
        with top_cols[0]:
            uploaded = render_photo_upload_control(
                current_player,
                key=f"photo_{current_player['id']}",
                size=112,
            )
            if uploaded is not None:
                update_player_photo(current_player["id"], uploaded.getvalue(), uploaded.type)
                st.success("Photo saved.")
                st.rerun()
        with top_cols[1]:
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
    game_date = st.date_input("Summary date", value=date.today(), key="summary_date")
    summary = nightly_summary(game_date)
    game_log = nightly_game_log(game_date)

    if summary.empty:
        st.info(f"No stat lines saved for {format_game_date(game_date)} yet.")
        return

    display = summary[list(NIGHTLY_TOTAL_COLUMNS.keys())].rename(columns=NIGHTLY_TOTAL_COLUMNS)
    st.caption("Nightly totals across all games. Click any column header to sort.")
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.download_button(
        "Download Nightly Totals CSV",
        data=display.to_csv(index=False),
        file_name=f"pickup_totals_{game_date.isoformat()}.csv",
        mime="text/csv",
    )

    with st.expander("Game-by-game log"):
        game_display = game_log[list(GAME_LOG_COLUMNS.keys())].rename(columns=GAME_LOG_COLUMNS)
        st.dataframe(game_display, use_container_width=True, hide_index=True)
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


def render_player_page(players: list[dict]) -> None:
    st.subheader("Player Page")
    current_player_id = selected_player_id(players)
    current_player = next(player for player in players if player["id"] == current_player_id)
    render_player_picker(players, current_player_id, {}, scope="player_page")

    header_cols = st.columns([1, 4])
    with header_cols[0]:
        render_photo(current_player, size=112)
    with header_cols[1]:
        st.markdown(f"### {current_player['name']}")
        st.caption("Night-by-night stat history. Click any column header to sort.")

    history = player_history(current_player_id)
    if history.empty:
        st.info(f"No stat lines saved for {current_player['name']} yet.")
        return

    metric_cols = st.columns(4)
    total_games = int(history["games"].sum())
    metric_cols[0].metric("Games", total_games)
    metric_cols[1].metric("Wins", int(history["wins"].sum()))
    metric_cols[2].metric("PPG", round(history["points"].sum() / total_games, 1))
    metric_cols[3].metric("RPG", round(history["rebounds"].sum() / total_games, 1))

    display_columns = list(PLAYER_NIGHT_COLUMNS.keys())
    display_columns.remove("name")
    display = history[display_columns].rename(
        columns={
            **PLAYER_NIGHT_COLUMNS,
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.download_button(
        "Download Player CSV",
        data=display.to_csv(index=False),
        file_name=f"{csv_safe_name(current_player['name'])}_stats.csv",
        mime="text/csv",
    )

    with st.expander("Game-by-game log"):
        games = player_game_log(current_player_id)
        game_columns = ["game_date", *GAME_LOG_COLUMNS.keys()]
        game_columns.remove("name")
        game_display = games[game_columns].rename(
            columns={
                "game_date": "Date",
                **GAME_LOG_COLUMNS,
            }
        )
        st.dataframe(game_display, use_container_width=True, hide_index=True)


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
    grouped["FG%"] = grouped.apply(lambda row: round(row["FGM"] / row["FGA"], 3) if row["FGA"] else None, axis=1)
    grouped["3P%"] = grouped.apply(lambda row: round(row["THREE_PM"] / row["THREE_PA"], 3) if row["THREE_PA"] else None, axis=1)
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
        display_columns = ["game_date", *GAME_LOG_COLUMNS.keys()]
        display_df = add_percentages(df)[display_columns].rename(
            columns={
                "game_date": "Date",
                **GAME_LOG_COLUMNS,
            }
        )
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download CSV",
            data=display_df.to_csv(index=False),
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
                uploaded = render_photo_upload_control(
                    player,
                    key=f"roster_photo_{player['id']}",
                    size=84,
                )
                if uploaded is not None:
                    update_player_photo(player["id"], uploaded.getvalue(), uploaded.type)
                    st.success("Photo saved.")
                    st.rerun()
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
        div[data-testid="stFileUploader"] {
            width: 112px;
        }
        div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] {
            align-items: center;
            background: #f3f4f6;
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
        }
        div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"]::before {
            color: #737373;
            content: "+";
            font-size: 2rem;
            font-weight: 800;
            line-height: 1;
        }
        div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] > div {
            display: none;
        }
        div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] button {
            cursor: pointer;
            height: 112px;
            inset: 0;
            opacity: 0;
            position: absolute;
            width: 112px;
        }
        div[data-testid="stFormSubmitButton"] button[kind="primary"],
        div[data-testid="stButton"] button[kind="primary"] {
            min-height: 3rem;
            font-size: 1.05rem;
            font-weight: 800;
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

    tab_game, tab_player, tab_summary, tab_leaderboard, tab_roster = st.tabs(
        ["Game Night", "Player Page", "Nightly Summary", "Leaderboards", "Roster"]
    )
    with tab_game:
        render_game_night(players)
    with tab_player:
        render_player_page(players)
    with tab_summary:
        render_nightly_summary()
    with tab_leaderboard:
        render_leaderboard()
    with tab_roster:
        render_roster(players)


if __name__ == "__main__":
    main()
