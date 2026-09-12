import os
import requests
from datetime import datetime
from dotenv import load_dotenv

from db_connection import get_connection


# --------------------------------------------------
# Load environment variables
# --------------------------------------------------

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

BASE_URL = "https://cricbuzz-cricket.p.rapidapi.com"

HEADERS = {
    "Content-Type": "application/json",
    "x-rapidapi-host": "cricbuzz-cricket.p.rapidapi.com",
    "x-rapidapi-key": RAPIDAPI_KEY
}


# --------------------------------------------------
# Convert Cricbuzz timestamp to date
# --------------------------------------------------

def convert_timestamp_to_date(timestamp):
    """Convert Cricbuzz timestamp in milliseconds to Python date."""

    if not timestamp:
        return None

    try:
        return datetime.fromtimestamp(
            int(timestamp) / 1000
        ).date()

    except (ValueError, TypeError):
        return None


# --------------------------------------------------
# Get live matches
# --------------------------------------------------

def get_live_matches():
    """Fetch currently live cricket matches from Cricbuzz API."""

    url = f"{BASE_URL}/matches/v1/live"

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15
        )

        response.raise_for_status()

        return response.json()

    except requests.exceptions.RequestException as e:

        print("API request error:", e)

        return None


# --------------------------------------------------
# Get team players
# --------------------------------------------------

def get_team_players(team_id, match_id):
    """Fetch players for a team in a specific match."""

    url = f"{BASE_URL}/mcenter/v1/{match_id}/team/{team_id}"

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15
        )

        response.raise_for_status()

        return response.json()

    except requests.exceptions.RequestException as e:

        print("Team API request error:", e)

        return None


# --------------------------------------------------
# Save live matches to PostgreSQL
# --------------------------------------------------

def save_live_matches_to_database(data):
    """Save live match information into PostgreSQL."""

    if not data:
        return 0

    connection = get_connection()

    if not connection:
        print("Database connection failed.")
        return 0

    cursor = connection.cursor()

    saved_count = 0

    try:

        # ------------------------------------------
        # Match Types
        # ------------------------------------------

        for match_type in data.get("typeMatches", []):

            match_type_name = match_type.get(
                "matchType",
                "Unknown"
            )

            # --------------------------------------
            # Series Groups
            # --------------------------------------

            for series_group in match_type.get(
                "seriesMatches",
                []
            ):

                wrapper = series_group.get(
                    "seriesAdWrapper",
                    {}
                )

                series_name = wrapper.get(
                    "seriesName"
                )

                if not series_name:
                    continue

                # ----------------------------------
                # Series dates
                # ----------------------------------

                series_start_date = convert_timestamp_to_date(
                    wrapper.get("seriesStartDt")
                )

                planned_matches = None

                # ----------------------------------
                # Find existing series
                # ----------------------------------

                cursor.execute(
                    """
                    SELECT series_id
                    FROM series
                    WHERE series_name = %s
                    LIMIT 1
                    """,
                    (series_name,)
                )

                series_row = cursor.fetchone()

                if series_row:

                    series_id = series_row[0]

                else:

                    cursor.execute(
                        """
                        INSERT INTO series
                        (
                            series_name,
                            host_country,
                            match_type,
                            start_date,
                            planned_matches
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING series_id
                        """,
                        (
                            series_name,
                            "Unknown",
                            match_type_name,
                            series_start_date,
                            planned_matches
                        )
                    )

                    series_id = cursor.fetchone()[0]

                # ----------------------------------
                # Matches
                # ----------------------------------

                for match in wrapper.get(
                    "matches",
                    []
                ):

                    match_info = match.get(
                        "matchInfo",
                        {}
                    )

                    match_description = match_info.get(
                        "matchDesc",
                        "Unknown Match"
                    )

                    match_date = convert_timestamp_to_date(
                        match_info.get("startDate")
                    )

                    if not match_date:
                        continue

                    match_status = match_info.get(
                        "status"
                    )
                    if match_status:
                        match_status = match_status[:50]

                    match_format = match_info.get(
                        "matchFormat"
                    )

                    # --------------------------------
                    # Find format
                    # --------------------------------

                    format_id = None

                    if match_format:

                        cursor.execute(
                            """
                            SELECT format_id
                            FROM formats
                            WHERE LOWER(format_name)
                                  = LOWER(%s)
                            LIMIT 1
                            """,
                            (match_format,)
                        )

                        format_row = cursor.fetchone()

                        if format_row:

                            format_id = format_row[0]

                    # --------------------------------
                    # Venue
                    # --------------------------------

                    venue_info = match_info.get(
                        "venueInfo",
                        {}
                    )

                    venue_name = venue_info.get(
                        "ground"
                    )

                    venue_city = venue_info.get(
                        "city"
                    )

                    venue_id = None

                    if venue_name:

                        cursor.execute(
                            """
                            SELECT venue_id
                            FROM venues
                            WHERE venue_name = %s
                            LIMIT 1
                            """,
                            (venue_name,)
                        )

                        venue_row = cursor.fetchone()

                        if venue_row:

                            venue_id = venue_row[0]

                        else:

                            cursor.execute(
                                """
                                INSERT INTO venues
                                (
                                    venue_name,
                                    city,
                                    country
                                )
                                VALUES (%s, %s, %s)
                                RETURNING venue_id
                                """,
                                (
                                    venue_name,
                                    venue_city,
                                    "Unknown"
                                )
                            )

                            venue_id = cursor.fetchone()[0]

                    # --------------------------------
                    # Team 1
                    # --------------------------------

                    team1 = match_info.get(
                        "team1",
                        {}
                    )

                    team1_id = None

                    if team1.get("teamName"):

                        cursor.execute(
                            """
                            SELECT team_id
                            FROM teams
                            WHERE team_name = %s
                            LIMIT 1
                            """,
                            (team1.get("teamName"),)
                        )

                        team1_row = cursor.fetchone()

                        if team1_row:

                            team1_id = team1_row[0]

                        else:

                            cursor.execute(
                                """
                                INSERT INTO teams
                                (
                                    team_name,
                                    short_name,
                                    country,
                                    team_type
                                )
                                VALUES (%s, %s, %s, %s)
                                RETURNING team_id
                                """,
                                (
                                    team1.get("teamName"),
                                    team1.get("teamSName"),
                                    team1.get("teamName"),
                                    match_type_name
                                )
                            )

                            team1_id = cursor.fetchone()[0]

                    # --------------------------------
                    # Team 2
                    # --------------------------------

                    team2 = match_info.get(
                        "team2",
                        {}
                    )

                    team2_id = None

                    if team2.get("teamName"):

                        cursor.execute(
                            """
                            SELECT team_id
                            FROM teams
                            WHERE team_name = %s
                            LIMIT 1
                            """,
                            (team2.get("teamName"),)
                        )

                        team2_row = cursor.fetchone()

                        if team2_row:

                            team2_id = team2_row[0]

                        else:

                            cursor.execute(
                                """
                                INSERT INTO teams
                                (
                                    team_name,
                                    short_name,
                                    country,
                                    team_type
                                )
                                VALUES (%s, %s, %s, %s)
                                RETURNING team_id
                                """,
                                (
                                    team2.get("teamName"),
                                    team2.get("teamSName"),
                                    team2.get("teamName"),
                                    match_type_name
                                )
                            )

                            team2_id = cursor.fetchone()[0]

                    # --------------------------------
                    # Find existing match
                    # --------------------------------

                    cursor.execute(
                        """
                        SELECT match_id
                        FROM matches
                        WHERE series_id = %s
                          AND match_description = %s
                          AND match_date = %s
                        LIMIT 1
                        """,
                        (
                            series_id,
                            match_description,
                            match_date
                        )
                    )

                    match_row = cursor.fetchone()

                    if match_row:

                        match_id = match_row[0]

                        # Update current status

                        cursor.execute(
                            """
                            UPDATE matches
                            SET status = %s,
                                format_id = %s,
                                venue_id = %s
                            WHERE match_id = %s
                            """,
                            (
                                match_status,
                                format_id,
                                venue_id,
                                match_id
                            )
                        )

                    else:

                        cursor.execute(
                            """
                            INSERT INTO matches
                            (
                                series_id,
                                format_id,
                                venue_id,
                                match_description,
                                match_date,
                                status
                            )
                            VALUES (%s, %s, %s, %s, %s, %s)
                            RETURNING match_id
                            """,
                            (
                                series_id,
                                format_id,
                                venue_id,
                                match_description,
                                match_date,
                                match_status
                            )
                        )

                        match_id = cursor.fetchone()[0]

                        saved_count += 1

                    # --------------------------------
                    # Match Teams - Team 1
                    # --------------------------------

                    if team1_id:

                        cursor.execute(
                            """
                            SELECT match_team_id
                            FROM match_teams
                            WHERE match_id = %s
                              AND team_id = %s
                            LIMIT 1
                            """,
                            (
                                match_id,
                                team1_id
                            )
                        )

                        if not cursor.fetchone():

                            cursor.execute(
                                """
                                INSERT INTO match_teams
                                (
                                    match_id,
                                    team_id,
                                    team_role
                                )
                                VALUES (%s, %s, %s)
                                """,
                                (
                                    match_id,
                                    team1_id,
                                    "Team 1"
                                )
                            )

                    # --------------------------------
                    # Match Teams - Team 2
                    # --------------------------------

                    if team2_id:

                        cursor.execute(
                            """
                            SELECT match_team_id
                            FROM match_teams
                            WHERE match_id = %s
                              AND team_id = %s
                            LIMIT 1
                            """,
                            (
                                match_id,
                                team2_id
                            )
                        )

                        if not cursor.fetchone():

                            cursor.execute(
                                """
                                INSERT INTO match_teams
                                (
                                    match_id,
                                    team_id,
                                    team_role
                                )
                                VALUES (%s, %s, %s)
                                """,
                                (
                                    match_id,
                                    team2_id,
                                    "Team 2"
                                )
                            )

        # ------------------------------------------
        # Commit
        # ------------------------------------------

        connection.commit()

        print(
            f"Successfully saved {saved_count} new match(es)."
        )

        return saved_count

    except Exception as e:

        connection.rollback()

        print(
            "Database save error:",
            e
        )

        return 0

    finally:

        cursor.close()
        connection.close()
        # --------------------------------------------------
# Save players to PostgreSQL
# --------------------------------------------------

def save_players_to_database(data):
    """Fetch and save players from live matches."""

    if not data:
        return 0

    connection = get_connection()

    if not connection:
        return 0

    cursor = connection.cursor()
    saved_count = 0

    try:

        for match_type in data.get("typeMatches", []):

            for series_group in match_type.get(
                "seriesMatches", []
            ):

                wrapper = series_group.get(
                    "seriesAdWrapper",
                    {}
                )

                for match in wrapper.get("matches", []):

                    match_info = match.get(
                        "matchInfo",
                        {}
                    )

                    match_id = match_info.get("matchId")

                    for team in [
                        match_info.get("team1", {}),
                        match_info.get("team2", {})
                    ]:

                        api_team_id = team.get("teamId")
                        team_name = team.get("teamName")

                        if not api_team_id or not team_name:
                            continue

                        # Find the database team
                        cursor.execute(
                            """
                            SELECT team_id
                            FROM teams
                            WHERE team_name = %s
                            LIMIT 1
                            """,
                            (team_name,)
                        )

                        team_row = cursor.fetchone()

                        if not team_row:
                            continue

                        db_team_id = team_row[0]

                        # Get players from API
                        players_data = get_team_players(
                            api_team_id,
                            match_id
                        )

                        if not players_data:
                            continue

                        for player in players_data.get(
                            "player",
                            []
                        ):

                            player_id = player.get("id")
                            player_name = player.get("name")

                            if not player_id or not player_name:
                                continue

                            cursor.execute(
                                """
                                SELECT player_id
                                FROM players
                                WHERE player_id = %s
                                """,
                                (player_id,)
                            )

                            existing_player = cursor.fetchone()

                            if existing_player:
                                continue

                            cursor.execute(
                                """
                                INSERT INTO players
                                (
                                    player_id,
                                    player_name,
                                    team_id,
                                    playing_role,
                                    batting_style,
                                    bowling_style
                                )
                                VALUES (%s, %s, %s, %s, %s, %s)
                                """,
                                (
                                    player_id,
                                    player_name,
                                    db_team_id,
                                    player.get("role"),
                                    player.get("battingStyle"),
                                    player.get("bowlingStyle")
                                )
                            )

                            saved_count += 1

        connection.commit()

        print(
            f"Successfully saved {saved_count} player(s)."
        )

        return saved_count

    except Exception as e:

        connection.rollback()

        print("Player save error:", e)

        return 0

    finally:

        cursor.close()
        connection.close()