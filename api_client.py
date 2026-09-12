import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

from db_connection import get_connection


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

BASE_URL = "https://cricbuzz-cricket.p.rapidapi.com"

HEADERS = {
    "Content-Type": "application/json",
    "x-rapidapi-host": "cricbuzz-cricket.p.rapidapi.com",
    "x-rapidapi-key": RAPIDAPI_KEY,
}


# ============================================================
# COMMON API REQUEST FUNCTION
# ============================================================

def make_request(url, attempts=3, timeout=15):
    """
    Send GET request to Cricbuzz RapidAPI.

    Includes simple retry handling.
    """

    last_error = None

    for attempt in range(attempts):

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=timeout
            )

            response.raise_for_status()

            return response.json()

        except (requests.exceptions.RequestException, ValueError) as error:

            last_error = error

            if attempt < attempts - 1:
                time.sleep(1)

    print("API request error:", last_error)

    return None


# ============================================================
# DATE CONVERSION
# ============================================================

def convert_timestamp_to_date(timestamp):
    """
    Convert Cricbuzz timestamp in milliseconds
    to Python date.
    """

    if not timestamp:
        return None

    try:

        return datetime.fromtimestamp(
            int(timestamp) / 1000
        ).date()

    except (ValueError, TypeError, OSError):

        return None


# ============================================================
# LIVE MATCHES
# ============================================================

def get_live_matches():
    """
    Fetch currently live cricket matches.
    """

    url = f"{BASE_URL}/matches/v1/live"

    return make_request(url)


def get_upcoming_matches():
    """
    Fetch upcoming cricket matches.
    """

    url = f"{BASE_URL}/matches/v1/upcoming"

    return make_request(url)


def get_recent_matches():
    """
    Fetch recently completed cricket matches.
    """

    url = f"{BASE_URL}/matches/v1/recent"

    return make_request(url)


# ============================================================
# TEAM PLAYERS
# ============================================================

def get_team_players(team_id, match_id):
    """
    Fetch players belonging to a team for a particular match.
    """

    if not team_id or not match_id:
        return None

    url = (
        f"{BASE_URL}/mcenter/v1/"
        f"{match_id}/team/{team_id}"
    )

    return make_request(url)


# ============================================================
# SCORECARD
# ============================================================

def get_scorecard(match_id):
    """
    Fetch detailed scorecard for a match.
    """

    if not match_id:
        return None

    url = (
        f"{BASE_URL}/mcenter/v1/"
        f"{match_id}/scard"
    )

    return make_request(url)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_first_value(data, keys, default=None):
    """
    Return the first available value from a dictionary.
    """

    if not isinstance(data, dict):
        return default

    for key in keys:

        value = data.get(key)

        if value not in (None, ""):
            return value

    return default


def find_database_team(cursor, team_name):
    """
    Find team_id from PostgreSQL using team name.
    """

    cursor.execute(
        """
        SELECT team_id
        FROM teams
        WHERE team_name = %s
        LIMIT 1
        """,
        (team_name,)
    )

    row = cursor.fetchone()

    if row:
        return row[0]

    return None


# ============================================================
# PLAYER EXTRACTION
# ============================================================

def extract_players_from_response(data):
    """
    Extract player dictionaries from different Cricbuzz
    response structures.

    Cricbuzz may return players inside:
    - player
    - players
    - playerData
    - playersData
    - squad
    - playingXI
    - playing11
    - sections
    - nested dictionaries/lists
    """

    found_players = []

    def add_player(value):

        if not isinstance(value, dict):
            return

        player_id = (
            value.get("id")
            or value.get("playerId")
            or value.get("playerID")
        )

        player_name = (
            value.get("name")
            or value.get("fullName")
            or value.get("playerName")
        )

        if player_id or player_name:
            found_players.append(value)

    def walk(value):

        if isinstance(value, dict):

            # Check whether this dictionary itself is a player.
            add_player(value)

            for key, child in value.items():

                key_lower = str(key).lower()

                if key_lower in (
                    "player",
                    "players",
                    "playerdata",
                    "playersdata",
                    "squad",
                    "playingxi",
                    "playing11",
                    "teamplayers",
                    "teamplayersdata",
                ):

                    if isinstance(child, list):

                        for item in child:
                            add_player(item)

                            if isinstance(item, (dict, list)):
                                walk(item)

                    elif isinstance(child, dict):

                        for item in child.values():

                            if isinstance(item, dict):
                                add_player(item)
                                walk(item)

                if isinstance(child, (dict, list)):
                    walk(child)

        elif isinstance(value, list):

            for item in value:
                walk(item)

    walk(data)

    # Remove duplicates
    unique_players = []
    seen = set()

    for player in found_players:

        player_id = (
            player.get("id")
            or player.get("playerId")
            or player.get("playerID")
        )

        player_name = (
            player.get("name")
            or player.get("fullName")
            or player.get("playerName")
        )

        if not player_id and not player_name:
            continue

        unique_key = (
            str(player_id),
            str(player_name)
        )

        if unique_key not in seen:

            seen.add(unique_key)

            unique_players.append(player)

    return unique_players


# ============================================================
# SAVE PLAYERS
# ============================================================

def save_players_to_database(data):
    """
    Fetch players from teams in live-match data
    and save them into PostgreSQL.
    """

    if not data:
        return 0

    connection = get_connection()

    if not connection:
        return 0

    cursor = connection.cursor()

    saved_count = 0

    try:

        type_matches = data.get(
            "typeMatches",
            []
        )

        for match_type in type_matches:

            series_matches = match_type.get(
                "seriesMatches",
                []
            )

            for series_group in series_matches:

                wrapper = series_group.get(
                    "seriesAdWrapper",
                    {}
                )

                matches = wrapper.get(
                    "matches",
                    []
                )

                for match in matches:

                    match_info = match.get(
                        "matchInfo",
                        {}
                    )

                    match_id = match_info.get(
                        "matchId"
                    )

                    if not match_id:
                        continue

                    teams = [
                        match_info.get(
                            "team1",
                            {}
                        ),
                        match_info.get(
                            "team2",
                            {}
                        )
                    ]

                    for api_team in teams:

                        api_team_id = get_first_value(
                            api_team,
                            [
                                "teamId",
                                "id"
                            ]
                        )

                        team_name = get_first_value(
                            api_team,
                            [
                                "teamName",
                                "name"
                            ]
                        )

                        if not api_team_id or not team_name:
                            continue

                        # Find team in PostgreSQL
                        db_team_id = find_database_team(
                            cursor,
                            team_name
                        )

                        if not db_team_id:
                            continue

                        # Get team players from Cricbuzz
                        players_data = get_team_players(
                            api_team_id,
                            match_id
                        )

                        if not players_data:
                            continue

                        # Extract players
                        players = extract_players_from_response(
                            players_data
                        )

                        for player in players:

                            player_id = get_first_value(
                                player,
                                [
                                    "id",
                                    "playerId",
                                    "playerID"
                                ]
                            )

                            player_name = get_first_value(
                                player,
                                [
                                    "name",
                                    "fullName",
                                    "playerName"
                                ]
                            )

                            if not player_id or not player_name:
                                continue

                            playing_role = get_first_value(
                                player,
                                [
                                    "role",
                                    "playingRole",
                                    "roleName"
                                ]
                            )

                            batting_style = get_first_value(
                                player,
                                [
                                    "battingStyle",
                                    "batStyle"
                                ]
                            )

                            bowling_style = get_first_value(
                                player,
                                [
                                    "bowlingStyle",
                                    "bowlStyle"
                                ]
                            )

                            # Check existing player
                            cursor.execute(
                                """
                                SELECT player_id
                                FROM players
                                WHERE player_id = %s
                                LIMIT 1
                                """,
                                (player_id,)
                            )

                            existing = cursor.fetchone()

                            if existing:

                                cursor.execute(
                                    """
                                    UPDATE players
                                    SET player_name = %s,
                                        team_id = %s,
                                        playing_role = %s,
                                        batting_style = %s,
                                        bowling_style = %s
                                    WHERE player_id = %s
                                    """,
                                    (
                                        player_name,
                                        db_team_id,
                                        playing_role,
                                        batting_style,
                                        bowling_style,
                                        player_id
                                    )
                                )

                            else:

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
                                    VALUES
                                    (%s, %s, %s, %s, %s, %s)
                                    """,
                                    (
                                        player_id,
                                        player_name,
                                        db_team_id,
                                        playing_role,
                                        batting_style,
                                        bowling_style
                                    )
                                )

                                saved_count += 1

        connection.commit()

        print(
            f"Successfully saved {saved_count} player(s)."
        )

        return saved_count

    except Exception as error:

        connection.rollback()

        print(
            "Player save error:",
            error
        )

        return 0

    finally:

        cursor.close()
        connection.close()


# ============================================================
# SAVE LIVE MATCHES
# ============================================================

def save_live_matches_to_database(data):
    """
    Save live Cricbuzz match information into PostgreSQL.

    Saves:
    - Formats
    - Series
    - Venues
    - Teams
    - Matches
    - Match-team relationships
    """

    if not data:
        return 0

    connection = get_connection()

    if not connection:
        return 0

    cursor = connection.cursor()

    saved_count = 0

    try:

        for match_type in data.get(
            "typeMatches",
            []
        ):

            format_name = match_type.get(
                "matchType"
            )

            if not format_name:
                continue

            format_name = str(
                format_name
            ).strip()

            # ------------------------------------------------
            # FORMAT
            # ------------------------------------------------

            cursor.execute(
                """
                SELECT format_id
                FROM formats
                WHERE LOWER(format_name) = LOWER(%s)
                LIMIT 1
                """,
                (format_name,)
            )

            format_row = cursor.fetchone()

            if format_row:

                format_id = format_row[0]

            else:

                cursor.execute(
                    """
                    INSERT INTO formats
                    (format_name)
                    VALUES (%s)
                    RETURNING format_id
                    """,
                    (format_name,)
                )

                format_id = cursor.fetchone()[0]

            # ------------------------------------------------
            # SERIES
            # ------------------------------------------------

            for series_group in match_type.get(
                "seriesMatches",
                []
            ):

                wrapper = series_group.get(
                    "seriesAdWrapper",
                    {}
                )

                if not wrapper:
                    continue

                series_name = (
                    wrapper.get("seriesName")
                    or "Unknown Series"
                )

                # Find series by name
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
                        (series_name)
                        VALUES (%s)
                        RETURNING series_id
                        """,
                        (series_name,)
                    )

                    series_id = cursor.fetchone()[0]

                # ------------------------------------------------
                # MATCHES
                # ------------------------------------------------

                for match in wrapper.get(
                    "matches",
                    []
                ):

                    match_info = match.get(
                        "matchInfo",
                        {}
                    )

                    api_match_id = match_info.get(
                        "matchId"
                    )

                    if not api_match_id:
                        continue

                    match_description = (
                        match_info.get(
                            "matchDesc"
                        )
                        or match_info.get(
                            "matchDescription"
                        )
                        or "Cricket Match"
                    )

                    match_date = convert_timestamp_to_date(
                        match_info.get(
                            "startDate"
                        )
                    )

                    if not match_date:

                        match_date = convert_timestamp_to_date(
                            match_info.get(
                                "startTimestamp"
                            )
                        )

                    status = match_info.get(
                        "status"
                    )

                    if status:

                        status = str(
                            status
                        )[:50]

                    # ------------------------------------------------
                    # VENUE
                    # ------------------------------------------------

                    venue_info = match_info.get(
                        "venueInfo",
                        {}
                    )

                    venue_name = (
                        venue_info.get(
                            "ground"
                        )
                        or venue_info.get(
                            "groundName"
                        )
                        or "Unknown Venue"
                    )

                    city = (
                        venue_info.get(
                            "city"
                        )
                        or "Unknown City"
                    )

                    country = (
                        venue_info.get(
                            "country"
                        )
                        or "Unknown Country"
                    )

                    cursor.execute(
                        """
                        SELECT venue_id
                        FROM venues
                        WHERE venue_name = %s
                          AND city = %s
                        LIMIT 1
                        """,
                        (
                            venue_name,
                            city
                        )
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
                            VALUES
                            (%s, %s, %s)
                            RETURNING venue_id
                            """,
                            (
                                venue_name,
                                city,
                                country
                            )
                        )

                        venue_id = cursor.fetchone()[0]

                    # ------------------------------------------------
                    # TEAMS
                    # ------------------------------------------------

                    database_team_ids = []

                    for api_team in [
                        match_info.get(
                            "team1",
                            {}
                        ),
                        match_info.get(
                            "team2",
                            {}
                        )
                    ]:

                        team_name = get_first_value(
                            api_team,
                            [
                                "teamName",
                                "name"
                            ]
                        )

                        short_name = get_first_value(
                            api_team,
                            [
                                "teamSName",
                                "shortName"
                            ]
                        )

                        team_country = get_first_value(
                            api_team,
                            [
                                "country"
                            ],
                            default="Unknown"
                        )

                        if not team_name:
                            continue

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

                        if team_row:

                            db_team_id = team_row[0]

                        else:

                            cursor.execute(
                                """
                                INSERT INTO teams
                                (
                                    team_name,
                                    short_name,
                                    country
                                )
                                VALUES
                                (%s, %s, %s)
                                RETURNING team_id
                                """,
                                (
                                    team_name,
                                    short_name,
                                    team_country
                                )
                            )

                            db_team_id = cursor.fetchone()[0]

                        database_team_ids.append(
                            db_team_id
                        )

                    # ------------------------------------------------
                    # MATCH
                    # ------------------------------------------------

                    # Existing match is identified by the same
                    # description/date/teams because match_id is
                    # generated by PostgreSQL.

                    cursor.execute(
                        """
                        SELECT m.match_id
                        FROM matches m
                        WHERE m.match_description = %s
                          AND m.match_date = %s
                        LIMIT 1
                        """,
                        (
                            match_description,
                            match_date
                        )
                    )

                    existing_match = cursor.fetchone()

                    if existing_match:

                        db_match_id = existing_match[0]

                        cursor.execute(
                            """
                            UPDATE matches
                            SET status = %s,
                                venue_id = %s,
                                format_id = %s
                            WHERE match_id = %s
                            """,
                            (
                                status,
                                venue_id,
                                format_id,
                                db_match_id
                            )
                        )

                    else:

                        cursor.execute(
                            """
                            INSERT INTO matches
                            (
                                match_description,
                                match_date,
                                status,
                                venue_id,
                                format_id
                            )
                            VALUES
                            (%s, %s, %s, %s, %s)
                            RETURNING match_id
                            """,
                            (
                                match_description,
                                match_date,
                                status,
                                venue_id,
                                format_id
                            )
                        )

                        db_match_id = cursor.fetchone()[0]

                        saved_count += 1

                    # ------------------------------------------------
                    # MATCH TEAMS
                    # ------------------------------------------------

                    for db_team_id in database_team_ids:

                        cursor.execute(
                            """
                            SELECT 1
                            FROM match_teams
                            WHERE match_id = %s
                              AND team_id = %s
                            LIMIT 1
                            """,
                            (
                                db_match_id,
                                db_team_id
                            )
                        )

                        relationship_exists = cursor.fetchone()

                        if not relationship_exists:

                            cursor.execute(
                                """
                                INSERT INTO match_teams
                                (
                                    match_id,
                                    team_id
                                )
                                VALUES
                                (%s, %s)
                                """,
                                (
                                    db_match_id,
                                    db_team_id
                                )
                            )

        connection.commit()

        print(
            "Successfully saved/updated "
            f"{saved_count} match record(s)."
        )

        return saved_count

    except Exception as error:

        connection.rollback()

        print(
            "Match save error:",
            error
        )

        return 0

    finally:

        cursor.close()
        connection.close()


# ============================================================
# END OF FILE
# ============================================================