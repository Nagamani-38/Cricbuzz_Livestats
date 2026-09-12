# 🏏 Cricbuzz LiveStats

Cricbuzz LiveStats is a cricket analytics dashboard built using Python, Streamlit, PostgreSQL, REST API and pandas.

The application fetches cricket match data from the Cricbuzz Cricket API through RapidAPI, stores the data in PostgreSQL, and provides SQL analytics and CRUD operations through an interactive Streamlit dashboard.

---

## 📌 Project Features

### 1. Live Cricket Matches
- Fetch live cricket match data using REST API
- Display match ID, series, teams, format, status and venue
- Store fetched match information in PostgreSQL
- Refresh live match data through Streamlit

### 2. SQL Queries & Analytics
- 25 SQL analytical queries
- Match and team analysis
- Player performance analysis
- Format-wise match analysis
- Venue analysis
- Partnership analysis
- Time-series analysis

### 3. CRUD Operations
The application provides:
- Create team records
- Read team records
- Update team records
- Delete team records
- Form validation
- Database transactions
- Error handling

### 4. Top Players & Analytics
A dedicated section is included for displaying player performance statistics when player-performance data is available.

### 5. Project Information
The dashboard provides information about the technology stack and project modules.

---

## 🛠️ Technology Stack

- Python
- Streamlit
- PostgreSQL
- SQL
- REST API
- RapidAPI
- pandas
- requests
- psycopg2
- python-dotenv

---

## 📂 Project Structure

```text
Cricbuzz_Livestats/
│
├── app.py
├── api_client.py
├── db_connection.py
├── Cricbuzz_Analysis.sql
├── requirements.txt
├── readme.md
├── .env
├── .gitignore
└── venv/