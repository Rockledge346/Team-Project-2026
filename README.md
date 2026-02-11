# Team-Project-2026

Basic Flask app with SQL database, customer page, and admin page.

## Setup

```bash
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

- **Customer page:** http://127.0.0.1:5000/
- **Admin page:** http://127.0.0.1:5000/admin

The SQLite database is created at `instance/app.db` on first run (no tables until you add models).
