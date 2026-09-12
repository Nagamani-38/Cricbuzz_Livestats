-- =========================================================
-- CRICBUZZ LIVESTATS - DATABASE SCHEMA
-- PostgreSQL
-- =========================================================


-- 1. FORMATS
CREATE TABLE formats (
    format_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    format_name VARCHAR(20) NOT NULL UNIQUE
);


-- 2. TEAMS
CREATE TABLE teams (
    team_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL UNIQUE,
    short_name VARCHAR(20),
    country VARCHAR(100) NOT NULL,
    team_type VARCHAR(30)
);


-- 3. PLAYERS
CREATE TABLE players (
    player_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    player_name VARCHAR(150) NOT NULL,
    team_id INTEGER,
    playing_role VARCHAR(50),
    batting_style VARCHAR(50),
    bowling_style VARCHAR(100),

    CONSTRAINT fk_player_team
        FOREIGN KEY (team_id)
        REFERENCES teams(team_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
);


-- 4. VENUES
CREATE TABLE venues (
    venue_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    venue_name VARCHAR(200) NOT NULL,
    city VARCHAR(100),
    country VARCHAR(100) NOT NULL,
    capacity INTEGER,

    CONSTRAINT chk_venue_capacity
        CHECK (capacity IS NULL OR capacity >= 0)
);


-- 5. SERIES
CREATE TABLE series (
    series_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    series_name VARCHAR(200) NOT NULL,
    host_country VARCHAR(100),
    match_type VARCHAR(30),
    start_date DATE,
    planned_matches INTEGER,

    CONSTRAINT chk_planned_matches
        CHECK (planned_matches IS NULL OR planned_matches >= 0)
);


-- 6. MATCHES
CREATE TABLE matches (
    match_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    series_id INTEGER,
    format_id INTEGER,
    venue_id INTEGER,

    match_description VARCHAR(250) NOT NULL,
    match_date DATE NOT NULL,
    status VARCHAR(50),

    toss_winner_team_id INTEGER,
    toss_decision VARCHAR(20),

    winner_team_id INTEGER,
    victory_margin INTEGER,
    victory_type VARCHAR(20),

    CONSTRAINT fk_match_series
        FOREIGN KEY (series_id)
        REFERENCES series(series_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,

    CONSTRAINT fk_match_format
        FOREIGN KEY (format_id)
        REFERENCES formats(format_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    CONSTRAINT fk_match_venue
        FOREIGN KEY (venue_id)
        REFERENCES venues(venue_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,

    CONSTRAINT fk_match_toss_winner
        FOREIGN KEY (toss_winner_team_id)
        REFERENCES teams(team_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,

    CONSTRAINT fk_match_winner
        FOREIGN KEY (winner_team_id)
        REFERENCES teams(team_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,

    CONSTRAINT chk_toss_decision
        CHECK (
            toss_decision IS NULL
            OR toss_decision IN ('Bat', 'Bowl')
        ),

    CONSTRAINT chk_victory_type
        CHECK (
            victory_type IS NULL
            OR victory_type IN ('Runs', 'Wickets', 'Tie', 'Draw', 'NR')
        ),

    CONSTRAINT chk_victory_margin
        CHECK (
            victory_margin IS NULL
            OR victory_margin >= 0
        )
);


-- 7. MATCH TEAMS
CREATE TABLE match_teams (
    match_team_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    match_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,

    team_role VARCHAR(20),

    CONSTRAINT fk_match_team_match
        FOREIGN KEY (match_id)
        REFERENCES matches(match_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_match_team_team
        FOREIGN KEY (team_id)
        REFERENCES teams(team_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_match_team
        UNIQUE (match_id, team_id)
);


-- 8. INNINGS
CREATE TABLE innings (
    innings_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    match_id INTEGER NOT NULL,
    innings_number INTEGER NOT NULL,
    batting_team_id INTEGER NOT NULL,
    bowling_team_id INTEGER NOT NULL,

    total_runs INTEGER,
    total_wickets INTEGER,

    CONSTRAINT fk_innings_match
        FOREIGN KEY (match_id)
        REFERENCES matches(match_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_innings_batting_team
        FOREIGN KEY (batting_team_id)
        REFERENCES teams(team_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_innings_bowling_team
        FOREIGN KEY (bowling_team_id)
        REFERENCES teams(team_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_match_innings
        UNIQUE (match_id, innings_number),

    CONSTRAINT chk_innings_number
        CHECK (innings_number > 0),

    CONSTRAINT chk_total_runs
        CHECK (total_runs IS NULL OR total_runs >= 0),

    CONSTRAINT chk_total_wickets
        CHECK (total_wickets IS NULL OR total_wickets >= 0)
);


-- 9. BATTING PERFORMANCES
CREATE TABLE batting_performances (
    batting_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    innings_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,

    batting_position INTEGER,
    runs INTEGER NOT NULL DEFAULT 0,
    balls INTEGER NOT NULL DEFAULT 0,
    fours INTEGER DEFAULT 0,
    sixes INTEGER DEFAULT 0,
    strike_rate NUMERIC(6,2),
    dismissal_status VARCHAR(100),

    CONSTRAINT fk_batting_innings
        FOREIGN KEY (innings_id)
        REFERENCES innings(innings_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_batting_player
        FOREIGN KEY (player_id)
        REFERENCES players(player_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_innings_player_batting
        UNIQUE (innings_id, player_id),

    CONSTRAINT chk_batting_position
        CHECK (
            batting_position IS NULL
            OR batting_position > 0
        ),

    CONSTRAINT chk_runs
        CHECK (runs >= 0),

    CONSTRAINT chk_balls
        CHECK (balls >= 0),

    CONSTRAINT chk_fours
        CHECK (fours >= 0),

    CONSTRAINT chk_sixes
        CHECK (sixes >= 0)
);


-- 10. BOWLING PERFORMANCES
CREATE TABLE bowling_performances (
    bowling_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    innings_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,

    overs NUMERIC(5,1) DEFAULT 0,
    maidens INTEGER DEFAULT 0,
    runs_conceded INTEGER DEFAULT 0,
    wickets INTEGER DEFAULT 0,
    economy_rate NUMERIC(6,2),

    CONSTRAINT fk_bowling_innings
        FOREIGN KEY (innings_id)
        REFERENCES innings(innings_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_bowling_player
        FOREIGN KEY (player_id)
        REFERENCES players(player_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_innings_player_bowling
        UNIQUE (innings_id, player_id),

    CONSTRAINT chk_overs
        CHECK (overs >= 0),

    CONSTRAINT chk_maidens
        CHECK (maidens >= 0),

    CONSTRAINT chk_runs_conceded
        CHECK (runs_conceded >= 0),

    CONSTRAINT chk_wickets
        CHECK (wickets >= 0)
);
CREATE INDEX IF NOT EXISTS idx_fielding_player
ON fielding_performances(player_id);

CREATE INDEX IF NOT EXISTS idx_fielding_innings
ON fielding_performances(innings_id);

CREATE INDEX IF NOT EXISTS idx_partnership_innings
ON partnerships(innings_id);

CREATE INDEX IF NOT EXISTS idx_partnership_player1
ON partnerships(player1_id);

CREATE INDEX IF NOT EXISTS idx_partnership_player2
ON partnerships(player2_id);
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'series'
ORDER BY ordinal_position;
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'matches'
ORDER BY ordinal_position;
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'teams'
ORDER BY ordinal_position;
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'venues'
ORDER BY ordinal_position;
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'formats'
ORDER BY ordinal_position;
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'match_teams'
ORDER BY ordinal_position;
SELECT
    'series' AS table_name, COUNT(*) AS row_count FROM series
UNION ALL
SELECT 'matches', COUNT(*) FROM matches
UNION ALL
SELECT 'formats', COUNT(*) FROM formats
UNION ALL
SELECT 'teams', COUNT(*) FROM teams
UNION ALL
SELECT 'venues', COUNT(*) FROM venues
UNION ALL
SELECT 'match_teams', COUNT(*) FROM match_teams;
SELECT
    table_name,
    column_name,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
      'series',
      'matches',
      'formats',
      'teams',
      'venues',
      'match_teams'
  )
ORDER BY table_name, ordinal_position;
INSERT INTO formats (format_id, format_name)
VALUES
    (1, 'Test'),
    (2, 'ODI'),
    (3, 'T20'),
    (4, 'T20I'),
    (5, 'Other')
ON CONFLICT (format_id) DO NOTHING;
SELECT * FROM formats ORDER BY format_id;
INSERT INTO formats (format_id, format_name)
VALUES
    (1, 'Test'),
    (2, 'ODI'),
    (3, 'T20'),
    (4, 'T20I'),
    (5, 'Other')
ON CONFLICT (format_id) DO NOTHING;
INSERT INTO formats (format_name)
VALUES
    ('Test'),
    ('ODI'),
    ('T20'),
    ('T20I');
	SELECT * FROM formats ORDER BY format_id;
	SELECT
    table_name,
    column_name,
    is_identity,
    identity_generation
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
      'series',
      'matches',
      'teams',
      'venues',
      'match_teams'
  )
  AND column_name LIKE '%_id'
ORDER BY table_name, ordinal_position;
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type
FROM information_schema.table_constraints tc
WHERE tc.table_schema = 'public'
  AND tc.table_name IN (
      'series',
      'matches',
      'teams',
      'venues',
      'match_teams'
  )
ORDER BY tc.table_name, tc.constraint_type;