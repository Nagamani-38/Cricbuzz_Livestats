import streamlit as st
import pandas as pd

from api_client import get_live_matches, save_live_matches_to_database
from db_connection import get_connection


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
        data = get_live_matches()

    if data:
        saved_count = save_live_matches_to_database(data)
        matches = extract_live_matches(data)

        if matches:
            st.success(
                f"Fetched {len(matches)} match record(s). "
                f"Saved/updated {saved_count} match record(s) in PostgreSQL."
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
        WHERE t.country = 'India'
        ORDER BY p.player_name;
    """,

    "2. Matches in Last 30 Days": """
        SELECT m.match_id, m.match_description, m.match_date,
               v.venue_name, v.city, m.status
        FROM matches m
        LEFT JOIN venues v ON m.venue_id = v.venue_id
        WHERE m.match_date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY m.match_date DESC;
    """,

    "3. Top 10 Run Scorers": """
        SELECT p.player_name,
               SUM(bp.runs) AS total_runs,
               ROUND(AVG(bp.runs), 2) AS average_runs,
               COUNT(*) FILTER (WHERE bp.runs >= 100) AS centuries
        FROM players p
        JOIN batting_performances bp ON p.player_id = bp.player_id
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
        GROUP BY f.format_name
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
        SELECT p.player_name,
               SUM(bp.runs) AS total_runs,
               SUM(bb.wickets) AS total_wickets
        FROM players p
        JOIN batting_performances bp ON p.player_id = bp.player_id
        JOIN bowling_performances bb ON p.player_id = bb.player_id
        WHERE LOWER(p.playing_role) LIKE '%all%'
        GROUP BY p.player_id, p.player_name
        HAVING SUM(bp.runs) > 1000 AND SUM(bb.wickets) > 50
        ORDER BY total_runs DESC;
    """,

    "10. Last 20 Completed Matches": """
        SELECT m.match_id, m.match_description, m.match_date,
               t.team_name AS winner,
               m.victory_margin, m.victory_type, v.venue_name
        FROM matches m
        LEFT JOIN teams t ON m.winner_team_id = t.team_id
        LEFT JOIN venues v ON m.venue_id = v.venue_id
        WHERE LOWER(COALESCE(m.status, '')) LIKE '%complete%'
           OR LOWER(COALESCE(m.status, '')) LIKE '%finished%'
        ORDER BY m.match_date DESC
        LIMIT 20;
    """,

    "11. Player Performance Across Formats": """
        SELECT p.player_name, f.format_name,
               SUM(bp.runs) AS total_runs,
               COUNT(bp.batting_id) AS innings
        FROM players p
        JOIN batting_performances bp ON p.player_id = bp.player_id
        JOIN innings i ON bp.innings_id = i.innings_id
        JOIN matches m ON i.match_id = m.match_id
        JOIN formats f ON m.format_id = f.format_id
        GROUP BY p.player_id, p.player_name, f.format_name
        ORDER BY p.player_name, total_runs DESC;
    """,

    "12. Team Match Performance": """
        SELECT t.team_name,
               COUNT(mt.match_id) AS matches_played,
               COUNT(m.match_id) FILTER
                   (WHERE m.winner_team_id = t.team_id) AS wins
        FROM teams t
        LEFT JOIN match_teams mt ON t.team_id = mt.team_id
        LEFT JOIN matches m ON mt.match_id = m.match_id
        GROUP BY t.team_id, t.team_name
        ORDER BY wins DESC, matches_played DESC;
    """,

    "13. Partnerships of 100 or More": """
        SELECT partnership_runs, player1_position, player2_position
        FROM partnerships
        WHERE partnership_runs >= 100
        ORDER BY partnership_runs DESC;
    """,

    "14. Bowling Performance by Venue": """
        SELECT v.venue_name,
               SUM(bb.wickets) AS total_wickets,
               SUM(bb.runs_conceded) AS runs_conceded,
               ROUND(AVG(bb.economy_rate), 2) AS average_economy
        FROM bowling_performances bb
        JOIN innings i ON bb.innings_id = i.innings_id
        JOIN matches m ON i.match_id = m.match_id
        JOIN venues v ON m.venue_id = v.venue_id
        GROUP BY v.venue_id, v.venue_name
        ORDER BY total_wickets DESC;
    """,

    "15. Close Matches": """
        SELECT match_id, match_description, match_date,
               victory_margin, victory_type
        FROM matches
        WHERE victory_margin IS NOT NULL
        ORDER BY victory_margin ASC
        LIMIT 20;
    """,

    "16. Matches by Year": """
        SELECT EXTRACT(YEAR FROM match_date) AS match_year,
               COUNT(*) AS total_matches
        FROM matches
        WHERE match_date IS NOT NULL
        GROUP BY match_year
        ORDER BY match_year;
    """,

    "17. Toss Decisions": """
        SELECT toss_decision, COUNT(*) AS total_matches
        FROM matches
        GROUP BY toss_decision
        ORDER BY total_matches DESC;
    """,

    "18. Economical Limited-Overs Bowlers": """
        SELECT p.player_name,
               ROUND(AVG(bb.economy_rate), 2) AS average_economy,
               SUM(bb.wickets) AS total_wickets
        FROM players p
        JOIN bowling_performances bb ON p.player_id = bb.player_id
        JOIN innings i ON bb.innings_id = i.innings_id
        JOIN matches m ON i.match_id = m.match_id
        JOIN formats f ON m.format_id = f.format_id
        WHERE f.format_name IN ('ODI', 'T20', 'T20I')
        GROUP BY p.player_id, p.player_name
        ORDER BY average_economy ASC
        LIMIT 10;
    """,

    "19. Consistent Batsmen": """
        SELECT p.player_name,
               COUNT(bp.batting_id) AS innings,
               ROUND(AVG(bp.runs), 2) AS average_runs,
               MAX(bp.runs) AS highest_score
        FROM players p
        JOIN batting_performances bp ON p.player_id = bp.player_id
        GROUP BY p.player_id, p.player_name
        HAVING COUNT(bp.batting_id) >= 2
        ORDER BY average_runs DESC
        LIMIT 10;
    """,

    "20. Matches by Format": """
        SELECT f.format_name,
               COUNT(m.match_id) AS matches,
               MIN(m.match_date) AS first_match,
               MAX(m.match_date) AS latest_match
        FROM formats f
        LEFT JOIN matches m ON f.format_id = m.format_id
        GROUP BY f.format_id, f.format_name
        ORDER BY matches DESC;
    """,

    "21. Player Weighted Ranking": """
        SELECT p.player_name,
               COALESCE(SUM(bp.runs), 0) AS runs,
               COALESCE(SUM(bb.wickets), 0) AS wickets,
               COALESCE(SUM(ff.catches), 0) AS catches,
               COALESCE(SUM(bp.runs), 0)
               + COALESCE(SUM(bb.wickets), 0) * 20
               + COALESCE(SUM(ff.catches), 0) * 10 AS ranking_score
        FROM players p
        LEFT JOIN batting_performances bp ON p.player_id = bp.player_id
        LEFT JOIN bowling_performances bb ON p.player_id = bb.player_id
        LEFT JOIN fielding_performances ff ON p.player_id = ff.player_id
        GROUP BY p.player_id, p.player_name
        ORDER BY ranking_score DESC
        LIMIT 10;
    """,

    "22. Team Head-to-Head Matches": """
        SELECT t1.team_name AS team1,
               t2.team_name AS team2,
               COUNT(*) AS matches_played
        FROM match_teams mt1
        JOIN match_teams mt2
          ON mt1.match_id = mt2.match_id
         AND mt1.team_id < mt2.team_id
        JOIN teams t1 ON mt1.team_id = t1.team_id
        JOIN teams t2 ON mt2.team_id = t2.team_id
        GROUP BY t1.team_name, t2.team_name
        ORDER BY matches_played DESC;
    """,

    "23. Recent Form by Team": """
        SELECT t.team_name,
               COUNT(mt.match_id) AS recent_matches,
               COUNT(m.match_id) FILTER
                   (WHERE m.winner_team_id = t.team_id) AS recent_wins
        FROM teams t
        JOIN match_teams mt ON t.team_id = mt.team_id
        JOIN matches m ON mt.match_id = m.match_id
        WHERE m.match_date >= CURRENT_DATE - INTERVAL '90 days'
        GROUP BY t.team_id, t.team_name
        ORDER BY recent_wins DESC;
    """,

    "24. Successful Partnerships": """
        SELECT partnership_runs, player1_position, player2_position
        FROM partnerships
        WHERE partnership_runs >= 50
        ORDER BY partnership_runs DESC
        LIMIT 20;
    """,

    "25. Player Performance Time Series": """
        SELECT p.player_name, m.match_date,
               SUM(bp.runs) AS runs
        FROM players p
        JOIN batting_performances bp ON p.player_id = bp.player_id
        JOIN innings i ON bp.innings_id = i.innings_id
        JOIN matches m ON i.match_id = m.match_id
        GROUP BY p.player_id, p.player_name, m.match_date
        ORDER BY m.match_date, p.player_name;
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

top_players_query = """
    SELECT p.player_name,
           COALESCE(SUM(bp.runs), 0) AS total_runs,
           COALESCE(SUM(bb.wickets), 0) AS total_wickets,
           COALESCE(SUM(ff.catches), 0) AS total_catches
    FROM players p
    LEFT JOIN batting_performances bp
        ON p.player_id = bp.player_id
    LEFT JOIN bowling_performances bb
        ON p.player_id = bb.player_id
    LEFT JOIN fielding_performances ff
        ON p.player_id = ff.player_id
    GROUP BY p.player_id, p.player_name
    ORDER BY total_runs DESC
    LIMIT 10;
"""

top_players = run_query(top_players_query)

if top_players is not None:

    if top_players.empty:
        st.info(
            "Player statistics will appear here when player "
            "performance data is available."
        )
    else:
        st.dataframe(
            top_players,
            width="stretch",
            hide_index=True
        )


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
