# Personal Project Manager

A simple, single-user project management web app built with **Flask** and
**MySQL**. Pastel-themed UI with a light/dark mode toggle.

## Features

- Add, view, edit, and delete projects
- **Milestones tracking** with 1-click completion and dynamic progress percentage calculation
- **Deadline warning badges** (Overdue & Due Soon alerts) for projects and milestones
- Dashboard with status stat cards (Total / Not Started / In Progress / Completed / On Hold)
- Search by project name, technology, or description
- Filter by status and priority
- Project details page with meetings, change requests, and milestone roadmap
- Professional light / dark theme toggle
- Parameterized SQL queries throughout

## Project Structure

```
personal_project_manager/
│
├── app.py               ← Flask routes and business logic
├── config.py            ← DB config loaded from .env
├── database.py          ← MySQL connection helper
├── requirements.txt     ← Python dependencies
├── database.sql         ← Schema + optional sample data
├── web.config           ← IIS deployment configuration
├── .env                 ← Your secrets (never commit this!)
├── .gitignore
│
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── add_project.html
│   ├── edit_project.html
│   ├── project_details.html
│   ├── settings.html            ← Manage Guides & Assigned By
│   ├── milestone_form.html      ← Add / edit milestone
│   ├── meeting_form.html        ← Add / edit status meeting
│   └── change_request_form.html ← Add / edit change request
```
│
└── static/
    ├── css/
    │   └── style.css
    └── js/
        └── script.js
```

## Setup Instructions

### Step 1 — Install Python

Make sure Python 3.9+ is installed:

```
python --version
```

### Step 2 — Install MySQL Server

Install MySQL Server locally (or use an existing instance) and make sure it's
running.

### Step 3 — Create the database

Run the provided SQL script:

```
mysql -u root -p < database.sql
```

This creates the `personal_project_manager` database, the `projects` table,
and inserts 3 optional sample projects.

### Step 4 — Configure the database connection

Open `config.py` and set your actual MySQL password:

```python
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "YOUR_MYSQL_PASSWORD",
    "database": "personal_project_manager",
    "port": 3306
}
```

### Step 5 — Install dependencies

It's recommended to use a virtual environment:

```
python -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 6 — Run the application

```
python app.py
```

### Step 7 — Open the application

Visit:

```
http://127.0.0.1:5000
```

## Notes

- All project data is stored in MySQL — there is no SQLite/JSON fallback.
- Database errors are logged internally but never shown to the user in raw form.
- To remove the sample data, delete the `INSERT INTO projects ...` block at
  the bottom of `database.sql` before running it, or just delete the rows
  afterward from the dashboard.
