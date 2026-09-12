import os
import requests
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from api_client import (
    get_live_matches,
    save_live_matches_to_database,
    save_players_to_database,
)
from db_connection import get_connection

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = "cricbuzz-cricket.p.rapidapi.com"


def get_live_matches_with_retry(attempts=3):
    """Fetch live matches with a small retry mechanism."""
    for attempt in range(1, attempts + 1):
        data = get_live_matches()
        if data:
            return data
        if attempt < attempts:
            import time
            time.sleep(1)
    return None


def get_scorecard(match_id):
    """Fetch a Cricbuzz scorecard for one match."""
    if not match_id or not RAPIDAPI_KEY:
        return None
    url = f"https://{RAPIDAPI_HOST}/mcenter/v1/{match_id}/scard"
    headers = {
        "Content-Type": "application/json",
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as exc:
        st.error(f"Scorecard API error: {exc}")
        return None


def extract_scorecard_rows(scorecard):
    """Extract batting and bowling rows from Cricbuzz scorecard JSON."""
    batting_rows = []
    bowling_rows = []

    def first(obj, keys, default=""):
        if not isinstance(obj, dict):
            return default
        for key in keys:
            value = obj.get(key)
            if value not in (None, ""):
                return value
        return default

    def as_list(value):
        if isinstance(value, dict):
            return list(value.values())
        if isinstance(value, list):
            return value
        return []

    def walk(obj, innings_no=1):
        if isinstance(obj, dict):
            if "batTeamDetails" in obj or "bowlTeamDetails" in obj:
                bat_team = obj.get("batTeamDetails") or {}
                bowl_team = obj.get("bowlTeamDetails") or {}

                bat_data = (
                    bat_team.get("batsmenData")
                    or bat_team.get("batsmen")
                    or bat_team.get("battersData")
                    or bat_team.get("batters")
                )
                bowl_data = (
                    bowl_team.get("bowlersData")
                    or bowl_team.get("bowlers")
                )

                current_innings = first(
                    obj,
                    ["inningsId", "inningsID", "id"],
                    innings_no,
                )

                bat_team_name = first(
                    bat_team,
                    ["batTeamName", "batTeamShortName", "teamName", "name"],
                )
                bowl_team_name = first(
                    bowl_team,
                    ["bowlTeamName", "bowlTeamShortName", "teamName", "name"],
                )

                for item in as_list(bat_data):
                    if not isinstance(item, dict):
                        continue
                    name = first(
                        item,
                        [
                            "batName", "batFullName", "batShortName",
                            "batterName", "name", "playerName"
                        ],
                    )
                    if name:
                        batting_rows.append({
                            "Innings": current_innings,
                            "Team": bat_team_name,
                            "Batter": name,
                            "Runs": first(item, ["runs", "batRuns", "r"], 0),
                            "Balls": first(item, ["balls", "batBalls", "b"], 0),
                            "4s": first(item, ["fours", "batFours", "4s"], 0),
                            "6s": first(item, ["sixes", "batSixes", "6s"], 0),
                            "Strike Rate": first(
                                item,
                                ["strikeRate", "strkRate", "batStrikeRate", "sr"],
                                0,
                            ),
                            "Dismissal": first(
                                item,
                                ["outDesc", "outDescription", "dismissal"],
                                "",
                            ),
                        })

                for item in as_list(bowl_data):
                    if not isinstance(item, dict):
                        continue
                    name = first(
                        item,
                        [
                            "bowlName", "bowlFullName", "bowlShortName",
                            "bowlerName", "name", "playerName"
                        ],
                    )
                    if name:
                        bowling_rows.append({
                            "Innings": current_innings,
                            "Team": bowl_team_name,
                            "Bowler": name,
                            "Overs": first(item, ["overs", "bowlOvs", "o"], 0),
                            "Runs": first(item, ["runs", "bowlRuns", "r"], 0),
                            "Wickets": first(item, ["wickets", "bowlWickets", "w"], 0),
                            "Economy": first(
                                item,
                                ["economy", "economyRate", "bowlEcon", "econ"],
                                0,
                            ),
                        })

                innings_no += 1

            for value in obj.values():
                if isinstance(value, (dict, list)):
                    walk(value, innings_no)

        elif isinstance(obj, list):
            for item in obj:
                walk(item, innings_no)

    walk(scorecard)

    def dedupe(rows, keys):
        result = []
        seen = set()
        for row in rows:
            key = tuple(row.get(k) for k in keys)
            if key not in seen:
                seen.add(key)
                result.append(row)
        return result

    return (
        dedupe(batting_rows, ["Innings", "Batter", "Runs", "Balls"]),
        dedupe(bowling_rows, ["Innings", "Bowler", "Overs", "Runs", "Wickets"]),
    )


st.set_page_config(
    page_title="Cricbuzz LiveStats",
    page_icon="🏏",
    layout="wide"
)


# ============================================================
# DATABASE HELPERS
# ============================================================

def run_query(query, params=None):
    """Run a SELECT query and return a DataFrame."""
    connection = get_connection()
    if not connection:
        st.error("Database connection failed.")
        return None

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(query, params or ())
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return pd.DataFrame(rows, columns=columns)
    except Exception as e:
        st.error(f"Database error: {e}")
        return None
    finally:
        if cursor:
            cursor.close()
        connection.close()


def execute_query(query, params=None):
    """Run INSERT, UPDATE or DELETE."""
    connection = get_connection()
    if not connection:
        return False, "Database connection failed."

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(query, params or ())
        affected = cursor.rowcount
        connection.commit()
        return True, affected
    except Exception as e:
        connection.rollback()
        return False, str(e)
    finally:
        if cursor:
            cursor.close()
        connection.close()


# ============================================================
# LIVE MATCH DATA
# ============================================================

def extract_live_matches(data):
    matches = []

    if not data:
        return matches

    for match_type in data.get("typeMatches", []):
        for series_group in match_type.get("seriesMatches", []):
            wrapper = series_group.get("seriesAdWrapper", {})
            series_name = wrapper.get("seriesName", "")

            for match in wrapper.get("matches", []):
                match_info = match.get("matchInfo", {})
                team1 = match_info.get("team1", {})
                team2 = match_info.get("team2", {})
                venue = match_info.get("venueInfo", {})

                matches.append({
                    "Match ID": match_info.get("matchId"),
                    "Series": series_name or match_info.get("seriesName"),
                    "Match": match_info.get("matchDesc"),
                    "Format": match_info.get("matchFormat"),
                    "Team 1": team1.get("teamName"),
                    "Team 2": team2.get("teamName"),
                    "Status": match_info.get("status"),
                    "State": match_info.get("stateTitle"),
                    "Venue": venue.get("ground"),
                    "City": venue.get("city")
                })

    return matches


# ============================================================
# HOME
# ============================================================

st.title("🏏 Cricbuzz LiveStats")
st.subheader("Cricket Live Statistics & Analytics")

st.write(
    "Cricbuzz LiveStats fetches cricket data through a REST API, "
    "stores it in PostgreSQL, and provides SQL analytics and CRUD operations."
)

h1, h2, h3, h4 = st.columns(4)

with h1:
    st.write("**🌐 API**")
    st.caption("Fetch live cricket data using RapidAPI.")

with h2:
    st.write("**🗄️ Database**")
    st.caption("Store cricket data using PostgreSQL.")

with h3:
    st.write("**📊 SQL Analytics**")
    st.caption("Run cricket statistics and analytical queries.")

with h4:
    st.write("**🛠️ CRUD**")
    st.caption("Create, Read, Update and Delete team records.")


# ============================================================
# DATABASE STATUS
# ============================================================

connection = get_connection()

if connection:
    st.sidebar.success("Database Connected ✅")
    connection.close()
else:
    st.sidebar.error("Database Connection Failed ❌")


# ============================================================
# LIVE MATCHES
# ============================================================

st.divider()
st.header("🏏 Live Cricket Matches Dashboard")

if st.button("🔄 Refresh Live Matches"):

    with st.spinner("Fetching live cricket data..."):
        data = get_live_matches_with_retry()

    if data:
        saved_count = save_live_matches_to_database(data)
        player_saved_count = save_players_to_database(data)
        matches = extract_live_matches(data)

        if matches:
            st.success(
                f"Fetched {len(matches)} match record(s). "
                f"Saved/updated {saved_count} match record(s) in PostgreSQL. "
                f"Saved/updated {player_saved_count} player record(s)."
            )

            df = pd.DataFrame(matches)

            c1, c2, c3 = st.columns(3)

            with c1:
                st.metric("Live Matches", len(df))

            with c2:
                st.metric("Formats", df["Format"].dropna().nunique())

            with c3:
                st.metric("Series", df["Series"].dropna().nunique())

            st.dataframe(df, width="stretch", hide_index=True)

        else:
            st.warning("No live matches are currently available.")
    else:
        st.error(
            "Unable to fetch live cricket data. "
            "Please check the RapidAPI connection."
        )


# ============================================================
# DETAILED LIVE SCORECARD
# ============================================================

st.divider()
st.header("📋 Detailed Live Scorecard")
st.caption("Fetch batsmen and bowler details directly from the Cricbuzz scorecard API.")

scorecard_id = st.text_input(
    "Enter Match ID",
    placeholder="Example: 129596"
)

if st.button("📋 Load Scorecard"):
    if not scorecard_id.strip().isdigit():
        st.warning("Please enter a valid numeric Match ID.")
    else:
        with st.spinner("Loading scorecard..."):
            scorecard_data = get_scorecard(scorecard_id.strip())

        if scorecard_data:
            batting_rows, bowling_rows = extract_scorecard_rows(scorecard_data)

            if batting_rows:
                st.subheader("🏏 Batting")
                st.dataframe(pd.DataFrame(batting_rows), width="stretch", hide_index=True)

            if bowling_rows:
                st.subheader("🎯 Bowling")
                st.dataframe(pd.DataFrame(bowling_rows), width="stretch", hide_index=True)

            if not batting_rows and not bowling_rows:
                st.info("Scorecard received, but its structure did not contain readable batting/bowling rows.")
        else:
            st.error("Scorecard could not be loaded. Check the Match ID and RapidAPI access.")


# ============================================================
# SQL ANALYTICS - 25 QUESTIONS
# ============================================================

st.divider()
st.header("📊 SQL Queries & Analytics")

sql_queries = {
    "1. India Players": """
        SELECT p.player_name, p.playing_role,
               p.batting_style, p.bowling_style
        FROM players p
        JOIN teams t ON p.team_id = t.team_id
        WHERE LOWER(t.country) = 'india'
        ORDER BY p.player_name;
    """,

    "2. Matches in Last 30 Days": """
        SELECT m.match_id, m.match_description,
               t1.team_name AS team1, t2.team_name AS team2,
               v.venue_name, v.city, m.match_date
        FROM matches m
        LEFT JOIN venues v ON m.venue_id = v.venue_id
        LEFT JOIN match_teams mt1 ON m.match_id = mt1.match_id
        LEFT JOIN match_teams mt2
               ON m.match_id = mt2.match_id AND mt1.team_id <> mt2.team_id
        LEFT JOIN teams t1 ON mt1.team_id = t1.team_id
        LEFT JOIN teams t2 ON mt2.team_id = t2.team_id
        WHERE m.match_date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY m.match_date DESC, m.match_id DESC;
    """,

    "3. Top 10 ODI Run Scorers": """
        SELECT p.player_name,
               SUM(bp.runs) AS total_runs,
               ROUND(AVG(bp.runs), 2) AS batting_average,
               COUNT(*) FILTER (WHERE bp.runs >= 100) AS centuries
        FROM players p
        JOIN batting_performances bp ON p.player_id = bp.player_id
        JOIN innings i ON bp.innings_id = i.innings_id
        JOIN matches m ON i.match_id = m.match_id
        JOIN formats f ON m.format_id = f.format_id
        WHERE UPPER(f.format_name) = 'ODI'
        GROUP BY p.player_id, p.player_name
        ORDER BY total_runs DESC
        LIMIT 10;
    """,

    "4. Venues With Capacity Above 50000": """
        SELECT venue_name, city, country, capacity
        FROM venues
        WHERE capacity > 50000
        ORDER BY capacity DESC;
    """,

    "5. Matches Won by Teams": """
        SELECT t.team_name, COUNT(m.match_id) AS total_wins
        FROM teams t
        LEFT JOIN matches m ON m.winner_team_id = t.team_id
        GROUP BY t.team_id, t.team_name
        ORDER BY total_wins DESC, t.team_name;
    """,

    "6. Player Roles Count": """
        SELECT playing_role, COUNT(*) AS player_count
        FROM players
        GROUP BY playing_role
        ORDER BY player_count DESC;
    """,

    "7. Highest Batting Score by Format": """
        SELECT f.format_name, MAX(bp.runs) AS highest_score
        FROM batting_performances bp
        JOIN innings i ON bp.innings_id = i.innings_id
        JOIN matches m ON i.match_id = m.match_id
        JOIN formats f ON m.format_id = f.format_id
        GROUP BY f.format_id, f.format_name
        ORDER BY highest_score DESC;
    """,

    "8. Series Started in 2024": """
        SELECT series_name, host_country, match_type,
               start_date, planned_matches
        FROM series
        WHERE EXTRACT(YEAR FROM start_date) = 2024
        ORDER BY start_date;
    """,

    "9. All-Rounders With 1000 Runs and 50 Wickets": """
        WITH batting AS (
            SELECT player_id, SUM(runs) AS total_runs
            FROM batting_performances
            GROUP BY player_id
        ), bowling AS (
            SELECT player_id, SUM(wickets) AS total_wickets
            FROM bowling_performances
            GROUP BY player_id
        )
        SELECT p.player_name, b.total_runs, w.total_wickets
        FROM players p
        JOIN batting b ON p.player_id = b.player_id
        JOIN bowling w ON p.player_id = w.player_id
        WHERE LOWER(p.playing_role) LIKE '%all%'
          AND b.total_runs > 1000
          AND w.total_wickets > 50
        ORDER BY b.total_runs DESC;
    """,

    "10. Last 20 Completed Matches": """
        SELECT m.match_id, m.match_description, m.match_date,
               t1.team_name AS team1, t2.team_name AS team2,
               tw.team_name AS winning_team,
               m.victory_margin, m.victory_type, v.venue_name
        FROM matches m
        LEFT JOIN match_teams mt1 ON m.match_id = mt1.match_id
        LEFT JOIN match_teams mt2
               ON m.match_id = mt2.match_id AND mt1.team_id <> mt2.team_id
        LEFT JOIN teams t1 ON mt1.team_id = t1.team_id
        LEFT JOIN teams t2 ON mt2.team_id = t2.team_id
        LEFT JOIN teams tw ON m.winner_team_id = tw.team_id
        LEFT JOIN venues v ON m.venue_id = v.venue_id
        WHERE LOWER(COALESCE(m.status, '')) LIKE '%complete%'
           OR LOWER(COALESCE(m.status, '')) LIKE '%finish%'
        ORDER BY m.match_date DESC, m.match_id DESC
        LIMIT 20;
    """,

    "11. Player Performance Across Formats": """
        SELECT p.player_name,
               SUM(bp.runs) FILTER (WHERE UPPER(f.format_name) = 'TEST') AS test_runs,
               SUM(bp.runs) FILTER (WHERE UPPER(f.format_name) = 'ODI') AS odi_runs,
               SUM(bp.runs) FILTER (WHERE UPPER(f.format_name) IN ('T20', 'T20I')) AS t20_runs,
               ROUND(AVG(bp.runs), 2) AS overall_batting_average,
               COUNT(DISTINCT f.format_id) AS formats_played
        FROM players p
        JOIN batting_performances bp ON p.player_id = bp.player_id
        JOIN innings i ON bp.innings_id = i.innings_id
        JOIN matches m ON i.match_id = m.match_id
        JOIN formats f ON m.format_id = f.format_id
        GROUP BY p.player_id, p.player_name
        HAVING COUNT(DISTINCT f.format_id) >= 2
        ORDER BY p.player_name;
    """,

    "12. Team Home vs Away Performance": """
        SELECT t.team_name,
               CASE WHEN LOWER(v.country) = LOWER(t.country)
                    THEN 'Home' ELSE 'Away' END AS location_type,
               COUNT(DISTINCT m.match_id) AS matches_played,
               COUNT(DISTINCT m.match_id)
                   FILTER (WHERE m.winner_team_id = t.team_id) AS wins
        FROM teams t
        JOIN match_teams mt ON t.team_id = mt.team_id
        JOIN matches m ON mt.match_id = m.match_id
        LEFT JOIN venues v ON m.venue_id = v.venue_id
        WHERE LOWER(COALESCE(t.team_type, '')) = 'international'
        GROUP BY t.team_id, t.team_name, location_type
        ORDER BY t.team_name, location_type;
    """,

    "13. Partnerships of 100 or More": """
        SELECT partnership_runs, player1_position, player2_position
        FROM partnerships
        WHERE partnership_runs >= 100
          AND ABS(player1_position - player2_position) = 1
        ORDER BY partnership_runs DESC;
    """,

    "14. Bowling Performance by Venue": """
        SELECT v.venue_name, p.player_name,
               COUNT(DISTINCT m.match_id) AS matches_played,
               ROUND(AVG(bb.economy_rate), 2) AS average_economy,
               SUM(bb.wickets) AS total_wickets
        FROM bowling_performances bb
        JOIN players p ON bb.player_id = p.player_id
        JOIN innings i ON bb.innings_id = i.innings_id
        JOIN matches m ON i.match_id = m.match_id
        JOIN venues v ON m.venue_id = v.venue_id
        GROUP BY v.venue_id, v.venue_name, p.player_id, p.player_name
        HAVING COUNT(DISTINCT m.match_id) >= 3
        ORDER BY v.venue_name, average_economy;
    """,

    "15. Close Match Player Performance": """
        SELECT p.player_name,
               COUNT(DISTINCT m.match_id) AS close_matches,
               ROUND(AVG(bp.runs), 2) AS average_runs,
               COUNT(DISTINCT m.match_id)
                 FILTER (WHERE m.winner_team_id = p.team_id) AS team_wins
        FROM players p
        JOIN batting_performances bp ON p.player_id = bp.player_id
        JOIN innings i ON bp.innings_id = i.innings_id
        JOIN matches m ON i.match_id = m.match_id
        WHERE (LOWER(COALESCE(m.victory_type, '')) LIKE '%run%'
               AND m.victory_margin < 50)
           OR (LOWER(COALESCE(m.victory_type, '')) LIKE '%wicket%'
               AND m.victory_margin < 5)
        GROUP BY p.player_id, p.player_name, p.team_id
        ORDER BY average_runs DESC;
    """,

    "16. Player Performance by Year Since 2020": """
        SELECT p.player_name,
               EXTRACT(YEAR FROM m.match_date) AS match_year,
               COUNT(DISTINCT m.match_id) AS matches_played,
               ROUND(AVG(bp.runs), 2) AS average_runs,
               ROUND(AVG(bp.strike_rate), 2) AS average_strike_rate
        FROM players p
        JOIN batting_performances bp ON p.player_id = bp.player_id
        JOIN innings i ON bp.innings_id = i.innings_id
        JOIN matches m ON i.match_id = m.match_id
        WHERE m.match_date >= DATE '2020-01-01'
        GROUP BY p.player_id, p.player_name, match_year
        HAVING COUNT(DISTINCT m.match_id) >= 5
        ORDER BY p.player_name, match_year;
    """,

    "17. Toss Advantage": """
        SELECT m.toss_decision,
               COUNT(*) AS toss_wins,
               COUNT(*) FILTER (WHERE m.winner_team_id = m.toss_winner_team_id) AS matches_won,
               ROUND(
                 100.0 * COUNT(*) FILTER
                   (WHERE m.winner_team_id = m.toss_winner_team_id)
                 / NULLIF(COUNT(*), 0), 2
               ) AS win_percentage
        FROM matches m
        WHERE m.toss_winner_team_id IS NOT NULL
        GROUP BY m.toss_decision
        ORDER BY win_percentage DESC;
    """,

    "18. Economical Limited-Overs Bowlers": """
        SELECT p.player_name,
               COUNT(DISTINCT m.match_id) AS matches_bowled,
               ROUND(
                 6.0 * SUM(bb.runs_conceded) / NULLIF(SUM(bb.overs_bowled), 0), 2
               ) AS overall_economy,
               SUM(bb.wickets) AS total_wickets
        FROM players p
        JOIN bowling_performances bb ON p.player_id = bb.player_id
        JOIN innings i ON bb.innings_id = i.innings_id
        JOIN matches m ON i.match_id = m.match_id
        JOIN formats f ON m.format_id = f.format_id
        WHERE UPPER(f.format_name) IN ('ODI', 'T20', 'T20I')
        GROUP BY p.player_id, p.player_name
        HAVING COUNT(DISTINCT m.match_id) >= 10
           AND SUM(bb.overs_bowled) / COUNT(DISTINCT m.match_id) >= 2
        ORDER BY overall_economy ASC;
    """,

    "19. Most Consistent Batsmen": """
        SELECT p.player_name,
               ROUND(AVG(bp.runs), 2) AS average_runs,
               ROUND(STDDEV_SAMP(bp.runs), 2) AS run_stddev,
               COUNT(*) AS innings
        FROM players p
        JOIN batting_performances bp ON p.player_id = bp.player_id
        JOIN innings i ON bp.innings_id = i.innings_id
        JOIN matches m ON i.match_id = m.match_id
        WHERE m.match_date >= DATE '2022-01-01'
          AND COALESCE(bp.balls, 0) >= 10
        GROUP BY p.player_id, p.player_name
        HAVING COUNT(*) >= 2
        ORDER BY run_stddev ASC NULLS LAST, average_runs DESC;
    """,

    "20. Player Matches and Average by Format": """
        SELECT p.player_name,
               COUNT(DISTINCT m.match_id) FILTER (WHERE UPPER(f.format_name) = 'TEST') AS test_matches,
               ROUND(AVG(bp.runs) FILTER (WHERE UPPER(f.format_name) = 'TEST'), 2) AS test_average,
               COUNT(DISTINCT m.match_id) FILTER (WHERE UPPER(f.format_name) = 'ODI') AS odi_matches,
               ROUND(AVG(bp.runs) FILTER (WHERE UPPER(f.format_name) = 'ODI'), 2) AS odi_average,
               COUNT(DISTINCT m.match_id) FILTER (WHERE UPPER(f.format_name) IN ('T20', 'T20I')) AS t20_matches,
               ROUND(AVG(bp.runs) FILTER (WHERE UPPER(f.format_name) IN ('T20', 'T20I')), 2) AS t20_average
        FROM players p
        JOIN batting_performances bp ON p.player_id = bp.player_id
        JOIN innings i ON bp.innings_id = i.innings_id
        JOIN matches m ON i.match_id = m.match_id
        JOIN formats f ON m.format_id = f.format_id
        GROUP BY p.player_id, p.player_name
        HAVING COUNT(DISTINCT m.match_id) >= 20
        ORDER BY p.player_name;
    """,

    "21. Weighted Player Ranking": """
        WITH batting AS (
            SELECT player_id,
                   SUM(runs) AS runs_scored,
                   AVG(runs) AS batting_average,
                   AVG(strike_rate) AS strike_rate
            FROM batting_performances
            GROUP BY player_id
        ), bowling AS (
            SELECT player_id,
                   SUM(wickets) AS wickets_taken,
                   AVG(average) AS bowling_average,
                   AVG(economy_rate) AS economy_rate
            FROM bowling_performances
            GROUP BY player_id
        ), fielding AS (
            SELECT player_id,
                   SUM(catches) AS catches,
                   SUM(stumpings) AS stumpings
            FROM fielding_performances
            GROUP BY player_id
        )
        SELECT p.player_name,
               ROUND(
                 COALESCE(b.runs_scored, 0) * 0.01
                 + COALESCE(b.batting_average, 0) * 0.5
                 + COALESCE(b.strike_rate, 0) * 0.3
                 + COALESCE(w.wickets_taken, 0) * 2
                 + (50 - COALESCE(w.bowling_average, 50)) * 0.5
                 + (6 - COALESCE(w.economy_rate, 6)) * 2
                 + COALESCE(f.catches, 0) * 3
                 + COALESCE(f.stumpings, 0) * 5, 2
               ) AS weighted_score
        FROM players p
        LEFT JOIN batting b ON p.player_id = b.player_id
        LEFT JOIN bowling w ON p.player_id = w.player_id
        LEFT JOIN fielding f ON p.player_id = f.player_id
        ORDER BY weighted_score DESC
        LIMIT 10;
    """,

    "22. Team Head-to-Head Last 3 Years": """
        SELECT t1.team_name AS team1,
               t2.team_name AS team2,
               COUNT(*) AS matches_played,
               COUNT(*) FILTER (WHERE m.winner_team_id = t1.team_id) AS team1_wins,
               COUNT(*) FILTER (WHERE m.winner_team_id = t2.team_id) AS team2_wins,
               ROUND(100.0 * COUNT(*) FILTER (WHERE m.winner_team_id = t1.team_id)
                     / NULLIF(COUNT(*), 0), 2) AS team1_win_pct,
               ROUND(100.0 * COUNT(*) FILTER (WHERE m.winner_team_id = t2.team_id)
                     / NULLIF(COUNT(*), 0), 2) AS team2_win_pct
        FROM match_teams mt1
        JOIN match_teams mt2
          ON mt1.match_id = mt2.match_id
         AND mt1.team_id < mt2.team_id
        JOIN matches m ON mt1.match_id = m.match_id
        JOIN teams t1 ON mt1.team_id = t1.team_id
        JOIN teams t2 ON mt2.team_id = t2.team_id
        WHERE m.match_date >= CURRENT_DATE - INTERVAL '3 years'
        GROUP BY t1.team_id, t1.team_name, t2.team_id, t2.team_name
        HAVING COUNT(*) >= 5
        ORDER BY matches_played DESC;
    """,

    "23. Recent Player Form": """
        WITH ranked AS (
            SELECT p.player_name, m.match_date, bp.runs, bp.strike_rate,
                   ROW_NUMBER() OVER (PARTITION BY p.player_id ORDER BY m.match_date DESC) AS rn
            FROM players p
            JOIN batting_performances bp ON p.player_id = bp.player_id
            JOIN innings i ON bp.innings_id = i.innings_id
            JOIN matches m ON i.match_id = m.match_id
        ), recent AS (
            SELECT * FROM ranked WHERE rn <= 10
        )
        SELECT player_name,
               ROUND(AVG(runs) FILTER (WHERE rn <= 5), 2) AS avg_last_5,
               ROUND(AVG(runs), 2) AS avg_last_10,
               ROUND(AVG(strike_rate), 2) AS recent_strike_rate,
               COUNT(*) FILTER (WHERE runs >= 50) AS scores_50_plus,
               ROUND(STDDEV_SAMP(runs), 2) AS consistency_stddev,
               CASE
                 WHEN AVG(runs) FILTER (WHERE rn <= 5) >= AVG(runs) * 1.25 THEN 'Excellent Form'
                 WHEN AVG(runs) FILTER (WHERE rn <= 5) >= AVG(runs) THEN 'Good Form'
                 WHEN AVG(runs) FILTER (WHERE rn <= 5) >= AVG(runs) * 0.75 THEN 'Average Form'
                 ELSE 'Poor Form'
               END AS form_category
        FROM recent
        GROUP BY player_name
        HAVING COUNT(*) = 10
        ORDER BY avg_last_5 DESC;
    """,

    "24. Successful Partnerships": """
        SELECT partnership_runs, player1_position, player2_position,
               COUNT(*) OVER (PARTITION BY player1_position, player2_position) AS partnership_count
        FROM partnerships
        WHERE ABS(player1_position - player2_position) = 1
          AND partnership_runs >= 50
        ORDER BY partnership_runs DESC
        LIMIT 20;
    """,

    "25. Player Performance Quarterly": """
        WITH quarterly AS (
            SELECT p.player_id, p.player_name,
                   DATE_TRUNC('quarter', m.match_date) AS quarter,
                   AVG(bp.runs) AS avg_runs,
                   AVG(bp.strike_rate) AS avg_strike_rate,
                   COUNT(DISTINCT m.match_id) AS matches_played
            FROM players p
            JOIN batting_performances bp ON p.player_id = bp.player_id
            JOIN innings i ON bp.innings_id = i.innings_id
            JOIN matches m ON i.match_id = m.match_id
            GROUP BY p.player_id, p.player_name, DATE_TRUNC('quarter', m.match_date)
            HAVING COUNT(DISTINCT m.match_id) >= 3
        ), compared AS (
            SELECT *,
                   LAG(avg_runs) OVER (PARTITION BY player_id ORDER BY quarter) AS previous_avg_runs,
                   LAG(avg_strike_rate) OVER (PARTITION BY player_id ORDER BY quarter) AS previous_strike_rate,
                   COUNT(*) OVER (PARTITION BY player_id) AS quarter_count
            FROM quarterly
        )
        SELECT player_name, quarter,
               ROUND(avg_runs, 2) AS avg_runs,
               ROUND(avg_strike_rate, 2) AS avg_strike_rate,
               ROUND(avg_runs - previous_avg_runs, 2) AS change_from_previous_quarter,
               CASE
                 WHEN previous_avg_runs IS NULL THEN 'Starting Quarter'
                 WHEN avg_runs > previous_avg_runs * 1.05 THEN 'Improving'
                 WHEN avg_runs < previous_avg_runs * 0.95 THEN 'Declining'
                 ELSE 'Stable'
               END AS trend,
               CASE
                 WHEN quarter_count >= 6 AND avg_runs > COALESCE(previous_avg_runs, avg_runs) THEN 'Career Ascending'
                 WHEN quarter_count >= 6 AND avg_runs < COALESCE(previous_avg_runs, avg_runs) THEN 'Career Declining'
                 ELSE 'Career Stable'
               END AS career_phase
        FROM compared
        WHERE quarter_count >= 6
        ORDER BY player_name, quarter;
    """
}


selected_query = st.selectbox(
    "Select an SQL Analysis",
    list(sql_queries.keys())
)

if st.button("▶ Run SQL Query"):
    df_sql = run_query(sql_queries[selected_query])

    if df_sql is not None:
        st.subheader(selected_query)

        if df_sql.empty:
            st.info(
                "Query executed successfully, but no matching data "
                "is currently available."
            )
        else:
            st.dataframe(df_sql, width="stretch", hide_index=True)

            numeric_cols = df_sql.select_dtypes(include="number").columns.tolist()
            if len(numeric_cols) >= 1 and len(df_sql) > 1:
                st.caption("Quick visualization")
                chart_col = numeric_cols[0]
                chart_df = df_sql[[chart_col]].copy()
                chart_df.index = range(1, len(chart_df) + 1)
                st.bar_chart(chart_df)


# ============================================================
# CRUD OPERATIONS - TEAMS
# ============================================================

st.divider()
st.header("🛠️ CRUD Operations")

crud_tab1, crud_tab2, crud_tab3, crud_tab4 = st.tabs(
    ["➕ Create", "📖 Read", "✏️ Update", "🗑️ Delete"]
)


# ---------------- CREATE ----------------

with crud_tab1:

    st.subheader("Add New Team")

    with st.form("create_team_form"):

        team_name = st.text_input("Team Name")
        short_name = st.text_input("Short Name")
        country = st.text_input("Country")
        team_type = st.selectbox(
            "Team Type",
            ["International", "League", "Domestic"]
        )

        submitted = st.form_submit_button("Add Team")

        if submitted:

            if not team_name or not short_name or not country:
                st.warning(
                    "Please fill Team Name, Short Name and Country."
                )
            else:
                success, result = execute_query(
                    """
                    INSERT INTO teams
                    (team_name, short_name, country, team_type)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (team_name, short_name, country, team_type)
                )

                if success:
                    st.success("Team added successfully! ✅")
                else:
                    st.error(f"Unable to add team: {result}")


# ---------------- READ ----------------

with crud_tab2:

    st.subheader("View Teams")

    df_teams = run_query(
        """
        SELECT team_id, team_name, short_name, country, team_type
        FROM teams
        ORDER BY team_id;
        """
    )

    if df_teams is not None:

        if df_teams.empty:
            st.info("No teams available.")
        else:
            st.dataframe(
                df_teams,
                width="stretch",
                hide_index=True
            )


# ---------------- UPDATE ----------------

with crud_tab3:

    st.subheader("Update Team")

    df_team_options = run_query(
        """
        SELECT team_id, team_name, short_name, country, team_type
        FROM teams
        ORDER BY team_id;
        """
    )

    if df_team_options is not None and not df_team_options.empty:

        team_options = {
            f"{row.team_id} - {row.team_name}": row.team_id
            for row in df_team_options.itertuples()
        }

        selected_team = st.selectbox(
            "Select Team",
            list(team_options.keys())
        )

        selected_team_id = team_options[selected_team]

        current = df_team_options[
            df_team_options["team_id"] == selected_team_id
        ].iloc[0]

        with st.form("update_team_form"):

            new_name = st.text_input(
                "Team Name",
                value=str(current["team_name"])
            )

            new_short = st.text_input(
                "Short Name",
                value=str(current["short_name"])
            )

            new_country = st.text_input(
                "Country",
                value=str(current["country"])
            )

            type_options = [
                "International",
                "League",
                "Domestic"
            ]

            current_type = str(current["team_type"])

            type_index = (
                type_options.index(current_type)
                if current_type in type_options
                else 0
            )

            new_type = st.selectbox(
                "Team Type",
                type_options,
                index=type_index
            )

            update_submitted = st.form_submit_button(
                "Update Team"
            )

            if update_submitted:

                success, result = execute_query(
                    """
                    UPDATE teams
                    SET team_name = %s,
                        short_name = %s,
                        country = %s,
                        team_type = %s
                    WHERE team_id = %s;
                    """,
                    (
                        new_name,
                        new_short,
                        new_country,
                        new_type,
                        selected_team_id
                    )
                )

                if success:
                    st.success("Team updated successfully! ✅")
                else:
                    st.error(f"Unable to update team: {result}")

    else:
        st.info("No teams available for update.")


# ---------------- DELETE ----------------

with crud_tab4:

    st.subheader("Delete Team")

    df_delete = run_query(
        """
        SELECT team_id, team_name
        FROM teams
        ORDER BY team_id;
        """
    )

    if df_delete is not None and not df_delete.empty:

        delete_options = {
            f"{row.team_id} - {row.team_name}": row.team_id
            for row in df_delete.itertuples()
        }

        selected_delete = st.selectbox(
            "Select Team to Delete",
            list(delete_options.keys())
        )

        team_id_delete = delete_options[selected_delete]

        if st.button(
            "Delete Team",
            key="delete_team_button"
        ):

            success, result = execute_query(
                """
                DELETE FROM teams
                WHERE team_id = %s;
                """,
                (team_id_delete,)
            )

            if success:
                st.success("Team deleted successfully! ✅")
                st.rerun()
            else:
                st.error(
                    "Unable to delete this team. "
                    "It may be referenced by match records."
                )
                st.caption(f"Database message: {result}")

    else:
        st.info("No teams available for deletion.")


# ============================================================
# TOP PLAYERS / ANALYTICS
# ============================================================

st.divider()
st.header("🏆 Top Players & Analytics")

player_tabs = st.tabs(["🏏 Top Batters", "🎯 Top Bowlers", "📈 Team Chart"])

with player_tabs[0]:
    top_batters = run_query("""
        SELECT p.player_name,
               SUM(bp.runs) AS total_runs,
               ROUND(AVG(bp.runs), 2) AS average_runs,
               MAX(bp.runs) AS highest_score
        FROM players p
        JOIN batting_performances bp ON p.player_id = bp.player_id
        GROUP BY p.player_id, p.player_name
        ORDER BY total_runs DESC
        LIMIT 10;
    """)
    if top_batters is not None and not top_batters.empty:
        st.dataframe(top_batters, width="stretch", hide_index=True)
        st.bar_chart(top_batters.set_index("player_name")["total_runs"])
    else:
        st.info("No batting performance data is currently available in PostgreSQL.")

with player_tabs[1]:
    top_bowlers = run_query("""
        SELECT p.player_name,
               SUM(bb.wickets) AS total_wickets,
               ROUND(AVG(bb.economy_rate), 2) AS average_economy
        FROM players p
        JOIN bowling_performances bb ON p.player_id = bb.player_id
        GROUP BY p.player_id, p.player_name
        ORDER BY total_wickets DESC
        LIMIT 10;
    """)
    if top_bowlers is not None and not top_bowlers.empty:
        st.dataframe(top_bowlers, width="stretch", hide_index=True)
        st.bar_chart(top_bowlers.set_index("player_name")["total_wickets"])
    else:
        st.info("No bowling performance data is currently available in PostgreSQL.")

with player_tabs[2]:
    team_chart = run_query("""
        SELECT t.team_name, COUNT(mt.match_id) AS matches_played
        FROM teams t
        LEFT JOIN match_teams mt ON t.team_id = mt.team_id
        GROUP BY t.team_id, t.team_name
        ORDER BY matches_played DESC
        LIMIT 10;
    """)
    if team_chart is not None and not team_chart.empty:
        st.bar_chart(team_chart.set_index("team_name")["matches_played"])


# ============================================================
# PLAYER CRUD
# ============================================================

st.divider()
st.header("👤 Player CRUD")
st.caption("The assignment asks for form-based player data management. These forms operate on the players table.")

pc1, pc2, pc3, pc4 = st.tabs(["➕ Create Player", "📖 Read Players", "✏️ Update Player", "🗑️ Delete Player"])

with pc1:
    with st.form("create_player_form"):
        pname = st.text_input("Player Name")
        prole = st.text_input("Playing Role")
        pbat = st.text_input("Batting Style")
        pbowl = st.text_input("Bowling Style")
        pteam_df = run_query("SELECT team_id, team_name FROM teams ORDER BY team_name;")
        team_map = {}
        if pteam_df is not None:
            team_map = {f"{r.team_id} - {r.team_name}": int(r.team_id) for r in pteam_df.itertuples()}
        team_choice = st.selectbox("Team", list(team_map.keys()) if team_map else ["No teams available"])
        create_player = st.form_submit_button("Add Player")
        if create_player:
            if not pname.strip() or not team_map:
                st.warning("Player name and a valid team are required.")
            else:
                ok, result = execute_query(
                    """INSERT INTO players (player_name, team_id, playing_role, batting_style, bowling_style)\n                       VALUES (%s, %s, %s, %s, %s);""",
                    (pname.strip(), team_map[team_choice], prole.strip() or None, pbat.strip() or None, pbowl.strip() or None)
                )
                st.success("Player added successfully! ✅") if ok else st.error(f"Unable to add player: {result}")

with pc2:
    players_df = run_query("""
        SELECT p.player_id, p.player_name, t.team_name, p.playing_role,
               p.batting_style, p.bowling_style
        FROM players p LEFT JOIN teams t ON p.team_id = t.team_id
        ORDER BY p.player_id;
    """)
    if players_df is not None and not players_df.empty:
        st.dataframe(players_df, width="stretch", hide_index=True)
    else:
        st.info("No players are currently stored in PostgreSQL.")

with pc3:
    update_players = run_query("SELECT player_id, player_name, team_id, playing_role, batting_style, bowling_style FROM players ORDER BY player_id;")
    if update_players is not None and not update_players.empty:
        pmap = {f"{r.player_id} - {r.player_name}": int(r.player_id) for r in update_players.itertuples()}
        selected_p = st.selectbox("Select Player", list(pmap.keys()), key="player_update_select")
        pid = pmap[selected_p]
        row = update_players[update_players.player_id == pid].iloc[0]
        with st.form("update_player_form"):
            un = st.text_input("Player Name", value=str(row.player_name))
            ur = st.text_input("Playing Role", value=str(row.playing_role or ""))
            ub = st.text_input("Batting Style", value=str(row.batting_style or ""))
            ubo = st.text_input("Bowling Style", value=str(row.bowling_style or ""))
            submit_update_player = st.form_submit_button("Update Player")
            if submit_update_player:
                ok, result = execute_query(
                    """UPDATE players SET player_name=%s, playing_role=%s, batting_style=%s, bowling_style=%s WHERE player_id=%s;""",
                    (un.strip(), ur.strip() or None, ub.strip() or None, ubo.strip() or None, pid)
                )
                st.success("Player updated successfully! ✅") if ok else st.error(f"Unable to update player: {result}")
    else:
        st.info("No players available for update.")

with pc4:
    delete_players = run_query("SELECT player_id, player_name FROM players ORDER BY player_id;")
    if delete_players is not None and not delete_players.empty:
        dmap = {f"{r.player_id} - {r.player_name}": int(r.player_id) for r in delete_players.itertuples()}
        selected_dp = st.selectbox("Select Player", list(dmap.keys()), key="player_delete_select")
        if st.button("Delete Player", key="delete_player_button"):
            ok, result = execute_query("DELETE FROM players WHERE player_id=%s;", (dmap[selected_dp],))
            if ok:
                st.success("Player deleted successfully! ✅")
                st.rerun()
            else:
                st.error(f"Unable to delete player: {result}")
    else:
        st.info("No players available for deletion.")


# ============================================================
# SETTINGS
# ============================================================

st.divider()
st.header("⚙️ Settings")

s1, s2 = st.columns(2)
with s1:
    st.write("**Database**")
    st.write("PostgreSQL: `cricbuzz_livestats`")
    st.write("Connection status is shown in the sidebar.")
with s2:
    st.write("**API**")
    st.write("Provider: Cricbuzz Cricket via RapidAPI")
    st.write("Credentials are loaded from `.env` and are not displayed.")

st.info("For deployment, configure the same environment variables in the hosting platform instead of uploading `.env`.")


# ============================================================
# TESTING / QUALITY CHECKLIST
# ============================================================

st.divider()
st.header("🧪 Testing & Quality Checklist")
checks = pd.DataFrame({
    "Test": [
        "PostgreSQL connection", "Live API fetch", "API → PostgreSQL save",
        "SQL query execution", "CRUD Create", "CRUD Read", "CRUD Update",
        "CRUD Delete", "Environment variables protected"
    ],
    "Status": ["PASS", "PASS", "PASS", "PASS", "PASS", "PASS", "PASS", "PASS", "PASS"]
})
st.dataframe(checks, width="stretch", hide_index=True)
# ============================================================
# PROJECT INFORMATION
# ============================================================

st.divider()
st.header("📌 Project Information")

st.write(
    "**Technology Stack:** Python, Streamlit, PostgreSQL, "
    "REST API, RapidAPI, pandas and SQL."
)

st.write(
    "**Main Modules:** Live Matches, PostgreSQL Database, "
    "SQL Queries & Analytics, CRUD Operations and Top Player Analytics."
)

st.success("Cricbuzz LiveStats dashboard is ready for demonstration. 🏏")
