# app.py
# ---------------------------------------------------------------
# Personal Project Management System
# A single-user Flask + MySQL application for tracking personal
# projects: add, view, edit, delete, search and filter.
# ---------------------------------------------------------------

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, abort, session
)
from mysql.connector import Error
from datetime import date, timedelta, datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import SECRET_KEY, MAIL_CONFIG
from database import get_db_connection

# ---------------------------------------------------------------
# Logging
# ---------------------------------------------------------------
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


app = Flask(__name__)
app.secret_key = SECRET_KEY

VALID_STATUSES = ['Not Started', 'In Progress', 'Completed', 'On Hold']
VALID_PRIORITIES = ['Low', 'Medium', 'High']

VALID_MILESTONE_STATUSES = ['Pending', 'In Progress', 'Completed', 'Delayed']
VALID_MEETING_STATUSES = ['Not Started', 'In Progress', 'On Hold', 'Completed', 'Delayed']
VALID_CR_PRIORITIES = ['Low', 'Medium', 'High', 'Critical']
VALID_CR_STATUSES = ['Open', 'In Progress', 'Completed', 'Rejected']

# Project progress isn't stored as its own column. It's derived from the
# project's overall status so the dashboard/details page always shows a
# reasonable estimate without needing a second field to keep in sync.
PROGRESS_BY_STATUS = {
    'Not Started': 0,
    'In Progress': 50,
    'On Hold': 50,
    'Completed': 100,
}



# ---------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------

def login_required(f):
    """Decorator: redirect to /login when the user is not logged in."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            flash("Please log in to access this page.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.context_processor
def inject_user():
    """Make session user info available in every template."""
    return {
        'current_user_id':   session.get('user_id'),
        'current_username':  session.get('username'),
        'current_full_name': session.get('full_name'),
    }


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def parse_date(value):
    """Convert an empty string to None, otherwise return the value."""
    if not value:
        return None
    return value


def validate_project_form(form):
    """
    Validate submitted project form data.
    Returns a list of error messages (empty list = valid).
    """
    errors = []

    project_name = form.get('project_name', '').strip()
    if not project_name:
        errors.append("Project Name is required.")
    elif len(project_name) > 200:
        errors.append("Project Name must be 200 characters or fewer.")

    technology = form.get('technology', '').strip()
    if len(technology) > 200:
        errors.append("Technology must be 200 characters or fewer.")

    project_link = form.get('project_link', '').strip()
    if len(project_link) > 500:
        errors.append("Project Link must be 500 characters or fewer.")

    status = form.get('status', 'Not Started')
    if status not in VALID_STATUSES:
        errors.append("Invalid status selected.")

    priority = form.get('priority', 'Medium')
    if priority not in VALID_PRIORITIES:
        errors.append("Invalid priority selected.")

    start_date = form.get('start_date') or None
    end_date = form.get('end_date') or None
    if start_date and end_date and end_date < start_date:
        errors.append("End Date cannot be before Start Date.")

    revised_start_date = form.get('revised_start_date') or None
    revised_end_date = form.get('revised_end_date') or None
    if revised_start_date and revised_end_date and revised_end_date < revised_start_date:
        errors.append("Revised End Date cannot be before Revised Start Date.")

    return errors


def validate_meeting_form(form):
    """Validate a Project Status Meeting form. Returns a list of errors."""
    errors = []

    meeting_date = form.get('meeting_date') or None
    if not meeting_date:
        errors.append("Meeting Date is required.")

    meeting_title = form.get('meeting_title', '').strip()
    if not meeting_title:
        errors.append("Meeting Title is required.")
    elif len(meeting_title) > 200:
        errors.append("Meeting Title must be 200 characters or fewer.")

    current_status = form.get('current_status', 'In Progress')
    if current_status not in VALID_MEETING_STATUSES:
        errors.append("Invalid meeting status selected.")

    next_meeting_date = form.get('next_meeting_date') or None
    if meeting_date and next_meeting_date and next_meeting_date < meeting_date:
        errors.append("Next Meeting Date cannot be before the Meeting Date.")

    return errors


def validate_change_request_form(form):
    """Validate a Change Request form. Returns a list of errors."""
    errors = []

    request_date = form.get('request_date') or None
    if not request_date:
        errors.append("Request Date is required.")

    title = form.get('title', '').strip()
    if not title:
        errors.append("Title is required.")
    elif len(title) > 200:
        errors.append("Title must be 200 characters or fewer.")

    priority = form.get('priority', 'Medium')
    if priority not in VALID_CR_PRIORITIES:
        errors.append("Invalid priority selected.")

    status = form.get('status', 'Open')
    if status not in VALID_CR_STATUSES:
        errors.append("Invalid status selected.")

    requested_by = form.get('requested_by', '').strip()
    if len(requested_by) > 150:
        errors.append("Requested By must be 150 characters or fewer.")

    completion_date = form.get('completion_date') or None
    if request_date and completion_date and completion_date < request_date:
        errors.append("Completion Date cannot be before the Request Date.")

    return errors


def validate_milestone_form(form):
    """Validate a Milestone form. Returns a list of errors."""
    errors = []

    title = form.get('title', '').strip()
    if not title:
        errors.append("Milestone Title is required.")
    elif len(title) > 200:
        errors.append("Milestone Title must be 200 characters or fewer.")

    status = form.get('status', 'Pending')
    if status not in VALID_MILESTONE_STATUSES:
        errors.append("Invalid milestone status selected.")

    return errors


# ---------------------------------------------------------------
# Authentication Routes
# ---------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))

    if request.method == 'GET':
        return render_template('login.html', identity='')

    identity = request.form.get('identity', '').strip()
    password = request.form.get('password', '')

    if not identity or not password:
        flash("Please enter both username/email and password.", "error")
        return render_template('login.html', identity=identity)

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE username = %s OR email = %s",
            (identity, identity)
        )
        user = cursor.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['full_name'] = user['full_name'] or user['username']
            flash(f"Welcome back, {session['full_name']}!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username/email or password.", "error")
            return render_template('login.html', identity=identity)
    except Error:
        logger.exception("login: DB error")
        flash("A database error occurred. Please try again.", "error")
        return render_template('login.html', identity=identity)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))

    if request.method == 'GET':
        return render_template('register.html', form_data={})

    full_name = request.form.get('full_name', '').strip()
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')

    errors = []
    if not username:
        errors.append("Username is required.")
    elif len(username) < 3 or len(username) > 80:
        errors.append("Username must be between 3 and 80 characters.")

    if not email or '@' not in email:
        errors.append("A valid email address is required.")

    if not password:
        errors.append("Password is required.")
    elif len(password) < 6:
        errors.append("Password must be at least 6 characters.")

    if password != confirm_password:
        errors.append("Passwords do not match.")

    if errors:
        for err in errors:
            flash(err, "error")
        return render_template('register.html', form_data=request.form)

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
        existing = cursor.fetchone()
        if existing:
            if existing['username'].lower() == username.lower():
                flash("This username is already taken. Please choose another.", "error")
            else:
                flash("An account with this email already exists.", "error")
            return render_template('register.html', form_data=request.form)

        pwd_hash = generate_password_hash(password)
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, full_name)
            VALUES (%s, %s, %s, %s)
            """,
            (username, email, pwd_hash, full_name or None)
        )
        new_user_id = cursor.lastrowid
        conn.commit()

        session['user_id'] = new_user_id
        session['username'] = username
        session['full_name'] = full_name or username

        flash("Account created successfully! Welcome to your project manager.", "success")
        return redirect(url_for('dashboard'))

    except Error:
        logger.exception("register: DB error")
        flash("A database error occurred during registration. Please try again.", "error")
        return render_template('register.html', form_data=request.form)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/logout', methods=['POST', 'GET'])
def logout():
    session.clear()
    flash("You have been signed out successfully.", "success")
    return redirect(url_for('login'))


def mask_email(email):
    """Mask email for privacy, e.g. user@example.com -> u***r@example.com"""
    if not email or '@' not in email:
        return email
    name, domain = email.split('@', 1)
    if len(name) <= 2:
        masked_name = name[0] + '*'
    else:
        masked_name = name[0] + '*' * (len(name) - 2) + name[-1]
    return f"{masked_name}@{domain}"


def send_reset_password_email(recipient_email, recipient_name, reset_url):
    """
    Send password reset email via SMTP.
    Returns (True, None) on success or (False, error_msg).
    """
    server_host = MAIL_CONFIG.get("server")
    username = MAIL_CONFIG.get("username")
    password = MAIL_CONFIG.get("password")

    if not server_host or not username:
        return False, "SMTP is not configured in .env"

    sender = MAIL_CONFIG.get("default_sender") or username
    subject = "Reset Your Password · Personal Project Manager"

    text_body = f"""Hello {recipient_name},

We received a request to reset your password for Personal Project Manager.
To set a new password, click the link below or paste it into your browser:

{reset_url}

This link is valid for 2 hours. If you did not request this, please ignore this email.
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f0f4f8; margin: 0; padding: 24px; color: #1a2640;">
  <div style="max-width: 520px; margin: 0 auto; background: #ffffff; border: 1px solid #d0d9e4; border-radius: 10px; padding: 32px; box-shadow: 0 4px 12px rgba(30,58,138,0.08);">
    <h2 style="color: #1e3a8a; margin-top: 0; font-size: 1.3rem; border-bottom: 2px solid #eff6ff; padding-bottom: 12px;">Personal Project Manager</h2>
    <p style="font-size: 1rem; color: #1a2640;">Hello <strong>{recipient_name}</strong>,</p>
    <p style="font-size: 0.95rem; color: #475569; line-height: 1.5;">We received a request to reset the password for your Personal Project Manager account. Click the button below to set a new password:</p>
    <div style="text-align: center; margin: 26px 0;">
      <a href="{reset_url}" style="display: inline-block; background: #2563eb; color: #ffffff; padding: 12px 28px; font-weight: 700; text-decoration: none; border-radius: 6px; font-size: 0.95rem;">Reset Password →</a>
    </div>
    <p style="font-size: 0.85rem; color: #64748b; line-height: 1.4;">If the button doesn't work, copy and paste this link into your browser:<br>
      <a href="{reset_url}" style="color: #2563eb; word-break: break-all;">{reset_url}</a>
    </p>
    <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #e2e8f0; font-size: 0.8rem; color: #94a3b8;">
      <p style="margin: 0 0 4px;">This link will expire in <strong>2 hours</strong>.</p>
      <p style="margin: 0;">If you didn't request a password reset, you can safely ignore this email.</p>
    </div>
  </div>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient_email

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        port = MAIL_CONFIG.get("port", 587)
        if MAIL_CONFIG.get("use_ssl"):
            server = smtplib.SMTP_SSL(server_host, port, timeout=12)
        else:
            server = smtplib.SMTP(server_host, port, timeout=12)
            if MAIL_CONFIG.get("use_tls"):
                server.starttls()

        if username and password:
            server.login(username, password)

        server.sendmail(sender, [recipient_email], msg.as_string())
        server.quit()
        return True, None
    except Exception as e:
        logger.exception("send_reset_password_email error to %s: %s", recipient_email, str(e))
        return False, str(e)


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'GET':
        return render_template(
            'forgot_password.html',
            identity='',
            reset_link=None,
            email_sent=False,
            masked_email=None,
            smtp_configured=bool(MAIL_CONFIG.get("server") and MAIL_CONFIG.get("username"))
        )

    identity = request.form.get('identity', '').strip()
    smtp_is_configured = bool(MAIL_CONFIG.get("server") and MAIL_CONFIG.get("username"))

    if not identity:
        flash("Please enter your username or email.", "error")
        return render_template(
            'forgot_password.html',
            identity=identity,
            reset_link=None,
            email_sent=False,
            masked_email=None,
            smtp_configured=smtp_is_configured
        )

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE username = %s OR email = %s",
            (identity, identity)
        )
        user = cursor.fetchone()

        if not user:
            flash("No account found matching that username or email.", "error")
            return render_template(
                'forgot_password.html',
                identity=identity,
                reset_link=None,
                email_sent=False,
                masked_email=None,
                smtp_configured=smtp_is_configured
            )

        token = secrets.token_urlsafe(32)
        expiry = datetime.now() + timedelta(hours=2)

        cursor.execute(
            "UPDATE users SET reset_token = %s, reset_token_expiry = %s WHERE user_id = %s",
            (token, expiry, user['user_id'])
        )
        conn.commit()

        reset_url = url_for('reset_password', token=token, _external=True)
        recipient_email = user.get('email')
        recipient_name = user.get('full_name') or user.get('username')

        # Attempt to send email via SMTP if configured
        email_sent = False
        if smtp_is_configured and recipient_email:
            success, err_msg = send_reset_password_email(recipient_email, recipient_name, reset_url)
            if success:
                email_sent = True
                flash(f"A password reset link has been sent to your email ({mask_email(recipient_email)}).", "success")
            else:
                flash(f"Could not send email ({err_msg}). Displaying link below as fallback.", "error")
        else:
            flash("Password reset link generated successfully!", "success")

        return render_template(
            'forgot_password.html',
            identity=identity,
            reset_link=reset_url if not email_sent else None,
            email_sent=email_sent,
            masked_email=mask_email(recipient_email) if recipient_email else None,
            smtp_configured=smtp_is_configured
        )

    except Error:
        logger.exception("forgot_password: DB error")
        flash("A database error occurred. Please try again.", "error")
        return render_template(
            'forgot_password.html',
            identity=identity,
            reset_link=None,
            email_sent=False,
            masked_email=None,
            smtp_configured=smtp_is_configured
        )
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn = None
    cursor = None
    user = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE reset_token = %s AND reset_token_expiry > %s",
            (token, datetime.now())
        )
        user = cursor.fetchone()
    except Error:
        flash("A database error occurred.", "error")
        return redirect(url_for('login'))
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if not user:
        flash("This password reset link is invalid or has expired.", "error")
        return redirect(url_for('forgot_password'))

    if request.method == 'GET':
        return render_template('reset_password.html', token=token, target_username=user['username'])

    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not new_password or len(new_password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return render_template('reset_password.html', token=token, target_username=user['username'])

    if new_password != confirm_password:
        flash("Passwords do not match.", "error")
        return render_template('reset_password.html', token=token, target_username=user['username'])

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        pwd_hash = generate_password_hash(new_password)
        cursor.execute(
            "UPDATE users SET password_hash = %s, reset_token = NULL, reset_token_expiry = NULL WHERE user_id = %s",
            (pwd_hash, user['user_id'])
        )
        conn.commit()
        flash("Your password has been reset successfully! You can now sign in.", "success")
        return redirect(url_for('login'))
    except Error:
        flash("Failed to update password. Please try again.", "error")
        return render_template('reset_password.html', token=token, target_username=user['username'])
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# ---------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------

@app.route('/')
@login_required
def dashboard():
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()
    priority_filter = request.args.get('priority', '').strip()
    tag_filter = request.args.get('tag', '').strip()
    show_archived = request.args.get('archived', '0') == '1'
    user_id = session['user_id']

    conn = None
    cursor = None
    projects = []
    upcoming_items = []
    all_tags = []
    stats = {
        'total': 0,
        'not_started': 0,
        'in_progress': 0,
        'completed': 0,
        'on_hold': 0,
        'archived': 0,
    }

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # ---- Stats (active projects only for status counts) ----
        cursor.execute(
            "SELECT status, COUNT(*) AS count FROM projects WHERE user_id = %s AND is_archived = 0 GROUP BY status",
            (user_id,)
        )
        for row in cursor.fetchall():
            stats['total'] += row['count']
            if row['status'] == 'Not Started':
                stats['not_started'] = row['count']
            elif row['status'] == 'In Progress':
                stats['in_progress'] = row['count']
            elif row['status'] == 'Completed':
                stats['completed'] = row['count']
            elif row['status'] == 'On Hold':
                stats['on_hold'] = row['count']

        # Archived count
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM projects WHERE user_id = %s AND is_archived = 1",
            (user_id,)
        )
        stats['archived'] = cursor.fetchone()['cnt']

        # ---- All user tags (for tag filter dropdown) ----
        all_tags = get_all_tags(cursor, user_id)

        # ---- Build filtered project query ----
        query = "SELECT * FROM projects WHERE user_id = %s AND is_archived = %s"
        params = [user_id, 1 if show_archived else 0]

        if search:
            query += " AND (project_name LIKE %s OR technology LIKE %s OR description LIKE %s)"
            like_term = f"%{search}%"
            params.extend([like_term, like_term, like_term])

        if status_filter in VALID_STATUSES:
            query += " AND status = %s"
            params.append(status_filter)

        if priority_filter in VALID_PRIORITIES:
            query += " AND priority = %s"
            params.append(priority_filter)

        if tag_filter:
            try:
                tag_id_val = int(tag_filter)
                query += " AND project_id IN (SELECT project_id FROM project_tags WHERE tag_id = %s)"
                params.append(tag_id_val)
            except ValueError:
                pass

        query += " ORDER BY updated_at DESC"

        cursor.execute(query, tuple(params))
        projects = cursor.fetchall()

        # ---- Fetch tags for each project ----
        if projects:
            project_ids = [p['project_id'] for p in projects]
            fmt = ','.join(['%s'] * len(project_ids))
            cursor.execute(
                f"""SELECT pt.project_id, t.tag_id, t.name, t.color
                    FROM project_tags pt
                    JOIN tags t ON t.tag_id = pt.tag_id
                    WHERE pt.project_id IN ({fmt})
                    ORDER BY t.name ASC""",
                tuple(project_ids)
            )
            tags_by_project = {}
            for row in cursor.fetchall():
                tags_by_project.setdefault(row['project_id'], []).append(row)
            for p in projects:
                p['tags'] = tags_by_project.get(p['project_id'], [])
        else:
            for p in projects:
                p['tags'] = []

        # ---- Upcoming: milestones + tasks due within 7 days or overdue (active projects only) ----
        today_val = date.today()
        week_ahead = (today_val + timedelta(days=7)).strftime('%Y-%m-%d')
        today_str = today_val.strftime('%Y-%m-%d')

        cursor.execute(
            """
            SELECT pm.milestone_id, pm.title AS item_title, pm.due_date,
                   pm.status AS item_status, 'milestone' AS item_type,
                   p.project_name, p.project_id
            FROM project_milestones pm
            JOIN projects p ON p.project_id = pm.project_id
            WHERE p.user_id = %s AND p.is_archived = 0
              AND pm.status != 'Completed'
              AND pm.due_date IS NOT NULL
              AND pm.due_date <= %s
            ORDER BY pm.due_date ASC
            LIMIT 20
            """,
            (user_id, week_ahead)
        )
        upcoming_milestones = cursor.fetchall()

        cursor.execute(
            """
            SELECT mt.task_id, mt.task_title AS item_title, mt.due_date,
                   mt.is_completed AS item_status, 'task' AS item_type,
                   p.project_name, p.project_id, pm.title AS milestone_title
            FROM milestone_tasks mt
            JOIN project_milestones pm ON pm.milestone_id = mt.milestone_id
            JOIN projects p ON p.project_id = pm.project_id
            WHERE p.user_id = %s AND p.is_archived = 0
              AND mt.is_completed = 0
              AND mt.due_date IS NOT NULL
              AND mt.due_date <= %s
            ORDER BY mt.due_date ASC
            LIMIT 20
            """,
            (user_id, week_ahead)
        )
        upcoming_tasks = cursor.fetchall()

        upcoming_items = upcoming_milestones + upcoming_tasks
        upcoming_items.sort(key=lambda x: str(x.get('due_date') or '9999-99-99'))

    except Error:
        logger.exception("dashboard: DB error while loading")
        flash("A database error occurred while loading the dashboard. "
              "Please check your MySQL connection and try again.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    today = date.today()
    return render_template(
        'dashboard.html',
        projects=projects,
        stats=stats,
        search=search,
        status_filter=status_filter,
        priority_filter=priority_filter,
        tag_filter=tag_filter,
        show_archived=show_archived,
        all_tags=all_tags,
        upcoming_items=upcoming_items,
        statuses=VALID_STATUSES,
        priorities=VALID_PRIORITIES,
        now=today.strftime('%Y-%m-%d'),
        due_soon_date=(today + timedelta(days=3)).strftime('%Y-%m-%d')
    )


# ---------------------------------------------------------------
# Project list (same data as dashboard, kept as a distinct route
# per the required routing structure)
# ---------------------------------------------------------------

@app.route('/projects')
@login_required
def project_list():
    return dashboard()


# ---------------------------------------------------------------
# Project details & Helpers
# ---------------------------------------------------------------

def get_all_guides(cursor, user_id):
    """Fetch guides for the given user, ordered by name."""
    cursor.execute(
        "SELECT * FROM guides WHERE user_id = %s ORDER BY name ASC",
        (user_id,)
    )
    return cursor.fetchall()


def get_all_assigned_by(cursor, user_id):
    """Fetch assigned_by persons for the given user, ordered by name."""
    cursor.execute(
        "SELECT * FROM assigned_by_persons WHERE user_id = %s ORDER BY name ASC",
        (user_id,)
    )
    return cursor.fetchall()


def get_project_guides(cursor, project_id):
    """Fetch all guides associated with a given project."""
    cursor.execute(
        """
        SELECT g.* FROM guides g
        INNER JOIN project_guides pg ON g.guide_id = pg.guide_id
        WHERE pg.project_id = %s
        ORDER BY g.name ASC
        """,
        (project_id,)
    )
    return cursor.fetchall()


def get_all_tags(cursor, user_id):
    """Fetch all tags for the given user, ordered by name."""
    cursor.execute(
        "SELECT * FROM tags WHERE user_id = %s ORDER BY name ASC",
        (user_id,)
    )
    return cursor.fetchall()


def get_project_tags(cursor, project_id):
    """Fetch all tags associated with a given project."""
    cursor.execute(
        """
        SELECT t.* FROM tags t
        INNER JOIN project_tags pt ON t.tag_id = pt.tag_id
        WHERE pt.project_id = %s
        ORDER BY t.name ASC
        """,
        (project_id,)
    )
    return cursor.fetchall()


def get_project_or_none(cursor, project_id, user_id=None):
    """Fetch a single project by id, optionally verifying user_id, or None if it doesn't exist."""
    if user_id is not None:
        cursor.execute(
            "SELECT * FROM projects WHERE project_id = %s AND user_id = %s",
            (project_id, user_id)
        )
    else:
        cursor.execute(
            "SELECT * FROM projects WHERE project_id = %s",
            (project_id,)
        )
    return cursor.fetchone()


@app.route('/project/<int:project_id>')
@login_required
def project_details(project_id):
    # Validate project_id before doing anything else.
    if project_id <= 0:
        flash("Invalid project ID.", "error")
        return redirect(url_for('dashboard'))

    conn = None
    cursor = None
    project = None
    milestones = []
    meetings = []
    change_requests = []
    project_guides = []
    assigned_by_name = None
    cr_counts = {'total': 0, 'open': 0, 'in_progress': 0, 'completed': 0, 'rejected': 0}
    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        project = get_project_or_none(cursor, project_id, user_id)
        if project is None:
            flash("Project not found.", "error")
            return redirect(url_for('dashboard'))

        # ---- Assigned By Name ----
        if project.get('assigned_by_id'):
            cursor.execute(
                "SELECT name FROM assigned_by_persons WHERE person_id = %s",
                (project['assigned_by_id'],)
            )
            person_row = cursor.fetchone()
            if person_row:
                assigned_by_name = person_row['name']

        # ---- Project Guides ----
        project_guides = get_project_guides(cursor, project_id)

        # ---- Project Tags ----
        project_tags = get_project_tags(cursor, project_id)

        # ---- Milestones, ordered by due date ----
        cursor.execute(
            """
            SELECT * FROM project_milestones
            WHERE project_id = %s
            ORDER BY due_date IS NULL, due_date ASC, milestone_id ASC
            """,
            (project_id,)
        )
        milestones = cursor.fetchall()

        # ---- Milestone Sub-Tasks ----
        cursor.execute(
            """
            SELECT t.* FROM milestone_tasks t
            INNER JOIN project_milestones m ON t.milestone_id = m.milestone_id
            WHERE m.project_id = %s
            ORDER BY t.is_completed ASC, t.task_id ASC
            """,
            (project_id,)
        )
        all_tasks = cursor.fetchall()
        tasks_by_milestone = {}
        for t in all_tasks:
            tasks_by_milestone.setdefault(t['milestone_id'], []).append(t)

        for m in milestones:
            m['tasks'] = tasks_by_milestone.get(m['milestone_id'], [])

        # ---- Status meetings, newest first ----
        cursor.execute(
            """
            SELECT * FROM project_status_meetings
            WHERE project_id = %s
            ORDER BY meeting_date DESC, meeting_id DESC
            """,
            (project_id,)
        )
        meetings = cursor.fetchall()

        # ---- Change requests, newest first ----
        cursor.execute(
            """
            SELECT * FROM change_requests
            WHERE project_id = %s
            ORDER BY request_date DESC, change_request_id DESC
            """,
            (project_id,)
        )
        change_requests = cursor.fetchall()

        # ---- Change request counts, calculated from MySQL (not stored) ----
        cursor.execute(
            "SELECT COUNT(*) AS total FROM change_requests WHERE project_id = %s",
            (project_id,)
        )
        cr_counts['total'] = cursor.fetchone()['total']

        cursor.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM change_requests
            WHERE project_id = %s
            GROUP BY status
            """,
            (project_id,)
        )
        for row in cursor.fetchall():
            if row['status'] == 'Open':
                cr_counts['open'] = row['count']
            elif row['status'] == 'In Progress':
                cr_counts['in_progress'] = row['count']
            elif row['status'] == 'Completed':
                cr_counts['completed'] = row['count']
            elif row['status'] == 'Rejected':
                cr_counts['rejected'] = row['count']

    except Error:
        logger.exception("project_details: DB error for project_id=%s", project_id)
        flash("A database error occurred while loading this project.", "error")
        return redirect(url_for('dashboard'))
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    milestones_total = len(milestones)
    milestones_completed = sum(1 for m in milestones if m['status'] == 'Completed')
    total_tasks = len(all_tasks)
    completed_tasks = sum(1 for t in all_tasks if t['is_completed'])

    if project['status'] == 'Completed':
        progress = 100
    elif total_tasks > 0:
        progress = int(round((completed_tasks / total_tasks) * 100))
    elif milestones_total > 0:
        progress = int(round((milestones_completed / milestones_total) * 100))
    else:
        progress = PROGRESS_BY_STATUS.get(project['status'], 0)

    today = date.today()
    return render_template(
        'project_details.html',
        project=project,
        assigned_by_name=assigned_by_name,
        project_guides=project_guides,
        project_tags=project_tags,
        milestones=milestones,
        milestones_total=milestones_total,
        milestones_completed=milestones_completed,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        meetings=meetings,
        change_requests=change_requests,
        cr_counts=cr_counts,
        progress=progress,
        milestone_statuses=VALID_MILESTONE_STATUSES,
        meeting_statuses=VALID_MEETING_STATUSES,
        cr_priorities=VALID_CR_PRIORITIES,
        cr_statuses=VALID_CR_STATUSES,
        now=today.strftime('%Y-%m-%d'),
        due_soon_date=(today + timedelta(days=3)).strftime('%Y-%m-%d')
    )


# ---------------------------------------------------------------
# Add project
# ---------------------------------------------------------------

@app.route('/project/add', methods=['GET', 'POST'])
@login_required
def add_project():
    user_id = session['user_id']
    conn = None
    cursor = None
    guides = []
    assigned_by_persons = []
    tags = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        guides = get_all_guides(cursor, user_id)
        assigned_by_persons = get_all_assigned_by(cursor, user_id)
        tags = get_all_tags(cursor, user_id)
    except Error:
        logger.exception("add_project GET: DB error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if request.method == 'GET':
        return render_template(
            'add_project.html',
            statuses=VALID_STATUSES,
            priorities=VALID_PRIORITIES,
            guides=guides,
            assigned_by_persons=assigned_by_persons,
            tags=tags,
            selected_guide_ids=[],
            selected_tag_ids=[],
            form_data={}
        )

    # POST: save the new project
    errors = validate_project_form(request.form)
    selected_guide_ids = request.form.getlist('guide_ids')
    selected_tag_ids = request.form.getlist('tag_ids')

    if errors:
        for message in errors:
            flash(message, "error")
        return render_template(
            'add_project.html',
            statuses=VALID_STATUSES,
            priorities=VALID_PRIORITIES,
            guides=guides,
            assigned_by_persons=assigned_by_persons,
            tags=tags,
            selected_guide_ids=selected_guide_ids,
            selected_tag_ids=selected_tag_ids,
            form_data=request.form
        )

    assigned_by_id = int(request.form.get('assigned_by_id')) if request.form.get('assigned_by_id') else None

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO projects
                (project_name, description, technology, start_date, end_date,
                 status, priority, project_link, notes, assigned_by_id,
                 revised_start_date, revised_end_date, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                request.form.get('project_name', '').strip(),
                request.form.get('description', '').strip() or None,
                request.form.get('technology', '').strip() or None,
                parse_date(request.form.get('start_date')),
                parse_date(request.form.get('end_date')),
                request.form.get('status', 'Not Started'),
                request.form.get('priority', 'Medium'),
                request.form.get('project_link', '').strip() or None,
                request.form.get('notes', '').strip() or None,
                assigned_by_id,
                parse_date(request.form.get('revised_start_date')),
                parse_date(request.form.get('revised_end_date')),
                user_id,
            )
        )
        new_project_id = cursor.lastrowid

        # Insert multiple guides
        for gid in selected_guide_ids:
            try:
                cursor.execute(
                    "INSERT INTO project_guides (project_id, guide_id) VALUES (%s, %s)",
                    (new_project_id, int(gid))
                )
            except Error:
                pass

        # Insert multiple tags
        for tid in selected_tag_ids:
            try:
                cursor.execute(
                    "INSERT INTO project_tags (project_id, tag_id) VALUES (%s, %s)",
                    (new_project_id, int(tid))
                )
            except Error:
                pass

        # Insert initial milestones if provided
        ms_titles = request.form.getlist('ms_title[]')
        ms_due_dates = request.form.getlist('ms_due_date[]')
        ms_statuses = request.form.getlist('ms_status[]')
        ms_descs = request.form.getlist('ms_desc[]')

        for i in range(len(ms_titles)):
            title = ms_titles[i].strip()
            if title:
                due_date = parse_date(ms_due_dates[i]) if i < len(ms_due_dates) else None
                status = ms_statuses[i] if (i < len(ms_statuses) and ms_statuses[i] in VALID_MILESTONE_STATUSES) else 'Pending'
                desc = ms_descs[i].strip() if (i < len(ms_descs) and ms_descs[i].strip()) else None
                comp_date = date.today() if status == 'Completed' else None

                cursor.execute(
                    """
                    INSERT INTO project_milestones
                        (project_id, title, description, due_date, status, completion_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (new_project_id, title, desc, due_date, status, comp_date)
                )

        conn.commit()
        flash("Project added successfully.", "success")
    except Error:
        logger.exception("add_project POST: DB error")
        flash("A database error occurred while saving the project. "
              "Please try again.", "error")
        return render_template(
            'add_project.html',
            statuses=VALID_STATUSES,
            priorities=VALID_PRIORITIES,
            guides=guides,
            assigned_by_persons=assigned_by_persons,
            tags=tags,
            selected_guide_ids=selected_guide_ids,
            selected_tag_ids=selected_tag_ids,
            form_data=request.form
        )
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('dashboard'))


# ---------------------------------------------------------------
# Edit project
# ---------------------------------------------------------------

@app.route('/project/edit/<int:project_id>', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    guides = []
    assigned_by_persons = []
    tags = []
    project = None
    selected_guide_ids = []
    selected_tag_ids = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        guides = get_all_guides(cursor, user_id)
        assigned_by_persons = get_all_assigned_by(cursor, user_id)
        tags = get_all_tags(cursor, user_id)
        project = get_project_or_none(cursor, project_id, user_id)
        if project:
            proj_guides = get_project_guides(cursor, project_id)
            selected_guide_ids = [str(g['guide_id']) for g in proj_guides]
            proj_tags = get_project_tags(cursor, project_id)
            selected_tag_ids = [str(t['tag_id']) for t in proj_tags]
    except Error:
        logger.exception("edit_project DB error for project_id=%s", project_id)
        flash("A database error occurred.", "error")
        return redirect(url_for('dashboard'))
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if project is None:
        flash("Project not found.", "error")
        return redirect(url_for('dashboard'))

    if request.method == 'GET':
        return render_template(
            'edit_project.html',
            project=project,
            statuses=VALID_STATUSES,
            priorities=VALID_PRIORITIES,
            guides=guides,
            assigned_by_persons=assigned_by_persons,
            tags=tags,
            selected_guide_ids=selected_guide_ids,
            selected_tag_ids=selected_tag_ids,
            today=date.today().strftime('%Y-%m-%d')
        )

    # POST: update the project
    errors = validate_project_form(request.form)
    selected_guide_ids = request.form.getlist('guide_ids')
    selected_tag_ids = request.form.getlist('tag_ids')

    if errors:
        for message in errors:
            flash(message, "error")
        merged = dict(project)
        merged.update(request.form)
        return render_template(
            'edit_project.html',
            project=merged,
            statuses=VALID_STATUSES,
            priorities=VALID_PRIORITIES,
            guides=guides,
            assigned_by_persons=assigned_by_persons,
            tags=tags,
            selected_guide_ids=selected_guide_ids,
            selected_tag_ids=selected_tag_ids,
            today=date.today().strftime('%Y-%m-%d')
        )

    assigned_by_id = int(request.form.get('assigned_by_id')) if request.form.get('assigned_by_id') else None

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE projects
            SET project_name = %s,
                description = %s,
                technology = %s,
                start_date = %s,
                end_date = %s,
                status = %s,
                priority = %s,
                project_link = %s,
                notes = %s,
                assigned_by_id = %s,
                revised_start_date = %s,
                revised_end_date = %s
            WHERE project_id = %s AND user_id = %s
            """,
            (
                request.form.get('project_name', '').strip(),
                request.form.get('description', '').strip() or None,
                request.form.get('technology', '').strip() or None,
                parse_date(request.form.get('start_date')),
                parse_date(request.form.get('end_date')),
                request.form.get('status', 'Not Started'),
                request.form.get('priority', 'Medium'),
                request.form.get('project_link', '').strip() or None,
                request.form.get('notes', '').strip() or None,
                assigned_by_id,
                parse_date(request.form.get('revised_start_date')),
                parse_date(request.form.get('revised_end_date')),
                project_id,
                user_id
            )
        )

        # Update guides: delete old, insert newly selected
        cursor.execute("DELETE FROM project_guides WHERE project_id = %s", (project_id,))
        for gid in selected_guide_ids:
            try:
                cursor.execute(
                    "INSERT INTO project_guides (project_id, guide_id) VALUES (%s, %s)",
                    (project_id, int(gid))
                )
            except Error:
                pass

        # Update tags: delete old, insert newly selected
        cursor.execute("DELETE FROM project_tags WHERE project_id = %s", (project_id,))
        for tid in selected_tag_ids:
            try:
                cursor.execute(
                    "INSERT INTO project_tags (project_id, tag_id) VALUES (%s, %s)",
                    (project_id, int(tid))
                )
            except Error:
                pass

        conn.commit()
        flash("Project updated successfully.", "success")
    except Error:
        logger.exception("edit_project: DB error for project_id=%s", project_id)
        flash("A database error occurred while updating the project.", "error")
        return redirect(url_for('edit_project', project_id=project_id))
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('project_details', project_id=project_id))



# ---------------------------------------------------------------
# Delete project
# ---------------------------------------------------------------

@app.route('/project/delete/<int:project_id>', methods=['POST'])
@login_required
def delete_project(project_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM projects WHERE project_id = %s AND user_id = %s",
            (project_id, user_id)
        )
        conn.commit()

        if cursor.rowcount == 0:
            flash("Project not found or not authorized.", "error")
        else:
            flash("Project deleted successfully.", "success")
    except Error:
        flash("A database error occurred while deleting the project.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('dashboard'))


# ---------------------------------------------------------------
# Archive / Unarchive project
# ---------------------------------------------------------------

@app.route('/project/<int:project_id>/archive', methods=['POST'])
@login_required
def toggle_archive_project(project_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        project = get_project_or_none(cursor, project_id, user_id)
        if not project:
            flash("Project not found or not authorized.", "error")
            return redirect(url_for('dashboard'))

        new_archived = 0 if project.get('is_archived') else 1
        cursor.execute(
            "UPDATE projects SET is_archived = %s WHERE project_id = %s AND user_id = %s",
            (new_archived, project_id, user_id)
        )
        conn.commit()
        if new_archived:
            flash(f"Project '{project['project_name']}' has been archived.", "success")
        else:
            flash(f"Project '{project['project_name']}' has been restored to active projects.", "success")
    except Error:
        logger.exception("toggle_archive_project: DB error")
        flash("A database error occurred while updating the archive status.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(request.referrer or url_for('dashboard'))


# ---------------------------------------------------------------
# Project Status Meetings
# ---------------------------------------------------------------

@app.route('/project/<int:project_id>/meeting/add', methods=['GET', 'POST'])
@login_required
def add_meeting(project_id):
    user_id = session['user_id']
    conn = None
    cursor = None

    # Make sure the parent project exists before showing/accepting the form.
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        project = get_project_or_none(cursor, project_id, user_id)
    except Error:
        flash("A database error occurred.", "error")
        return redirect(url_for('dashboard'))
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if project is None:
        flash("Project not found.", "error")
        return redirect(url_for('dashboard'))

    if request.method == 'GET':
        return render_template(
            'meeting_form.html',
            project=project,
            meeting=None,
            statuses=VALID_MEETING_STATUSES,
            form_action=url_for('add_meeting', project_id=project_id)
        )

    errors = validate_meeting_form(request.form)
    if errors:
        for message in errors:
            flash(message, "error")
        return render_template(
            'meeting_form.html',
            project=project,
            meeting=request.form,
            statuses=VALID_MEETING_STATUSES,
            form_action=url_for('add_meeting', project_id=project_id)
        )

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO project_status_meetings
                (project_id, meeting_date, meeting_title, summary, current_status,
                 decisions, action_items, next_meeting_date, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                project_id,
                parse_date(request.form.get('meeting_date')),
                request.form.get('meeting_title', '').strip(),
                request.form.get('summary', '').strip() or None,
                request.form.get('current_status', 'In Progress'),
                request.form.get('decisions', '').strip() or None,
                request.form.get('action_items', '').strip() or None,
                parse_date(request.form.get('next_meeting_date')),
                request.form.get('notes', '').strip() or None,
            )
        )
        conn.commit()
        flash("Status meeting added successfully.", "success")
    except Error:
        flash("A database error occurred while saving the meeting.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('project_details', project_id=project_id))


@app.route('/meeting/edit/<int:meeting_id>', methods=['GET', 'POST'])
@login_required
def edit_meeting(meeting_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM project_status_meetings WHERE meeting_id = %s",
            (meeting_id,)
        )
        meeting = cursor.fetchone()

        project = None
        if meeting is not None:
            project = get_project_or_none(cursor, meeting['project_id'], user_id)
    except Error:
        flash("A database error occurred.", "error")
        return redirect(url_for('dashboard'))
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if meeting is None or project is None:
        flash("Status meeting not found.", "error")
        return redirect(url_for('dashboard'))

    if request.method == 'GET':
        return render_template(
            'meeting_form.html',
            project=project,
            meeting=meeting,
            statuses=VALID_MEETING_STATUSES,
            form_action=url_for('edit_meeting', meeting_id=meeting_id)
        )

    errors = validate_meeting_form(request.form)
    if errors:
        for message in errors:
            flash(message, "error")
        merged = dict(meeting)
        merged.update(request.form)
        return render_template(
            'meeting_form.html',
            project=project,
            meeting=merged,
            statuses=VALID_MEETING_STATUSES,
            form_action=url_for('edit_meeting', meeting_id=meeting_id)
        )

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE project_status_meetings
            SET meeting_date = %s,
                meeting_title = %s,
                summary = %s,
                current_status = %s,
                decisions = %s,
                action_items = %s,
                next_meeting_date = %s,
                notes = %s
            WHERE meeting_id = %s
            """,
            (
                parse_date(request.form.get('meeting_date')),
                request.form.get('meeting_title', '').strip(),
                request.form.get('summary', '').strip() or None,
                request.form.get('current_status', 'In Progress'),
                request.form.get('decisions', '').strip() or None,
                request.form.get('action_items', '').strip() or None,
                parse_date(request.form.get('next_meeting_date')),
                request.form.get('notes', '').strip() or None,
                meeting_id
            )
        )
        conn.commit()
        flash("Status meeting updated successfully.", "success")
    except Error:
        flash("A database error occurred while updating the meeting.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('project_details', project_id=meeting['project_id']))


@app.route('/meeting/delete/<int:meeting_id>', methods=['POST'])
@login_required
def delete_meeting(meeting_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    project_id = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT project_id FROM project_status_meetings WHERE meeting_id = %s",
            (meeting_id,)
        )
        row = cursor.fetchone()
        if row is None:
            flash("Status meeting not found.", "error")
            return redirect(url_for('dashboard'))
        project_id = row['project_id']
        project = get_project_or_none(cursor, project_id, user_id)
        if not project:
            flash("Not authorized.", "error")
            return redirect(url_for('dashboard'))

        cursor.execute(
            "DELETE FROM project_status_meetings WHERE meeting_id = %s",
            (meeting_id,)
        )
        conn.commit()
        flash("Status meeting deleted successfully.", "success")
    except Error:
        flash("A database error occurred while deleting the meeting.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if project_id is None:
        return redirect(url_for('dashboard'))
    return redirect(url_for('project_details', project_id=project_id))


# ---------------------------------------------------------------
# Change Requests
# ---------------------------------------------------------------

@app.route('/project/<int:project_id>/change-request/add', methods=['GET', 'POST'])
@login_required
def add_change_request(project_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        project = get_project_or_none(cursor, project_id, user_id)
    except Error:
        flash("A database error occurred.", "error")
        return redirect(url_for('dashboard'))
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if project is None:
        flash("Project not found.", "error")
        return redirect(url_for('dashboard'))

    if request.method == 'GET':
        return render_template(
            'change_request_form.html',
            project=project,
            cr=None,
            priorities=VALID_CR_PRIORITIES,
            statuses=VALID_CR_STATUSES,
            form_action=url_for('add_change_request', project_id=project_id)
        )

    errors = validate_change_request_form(request.form)
    if errors:
        for message in errors:
            flash(message, "error")
        return render_template(
            'change_request_form.html',
            project=project,
            cr=request.form,
            priorities=VALID_CR_PRIORITIES,
            statuses=VALID_CR_STATUSES,
            form_action=url_for('add_change_request', project_id=project_id)
        )

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO change_requests
                (project_id, request_date, title, description, reason,
                 priority, status, requested_by, completion_date, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                project_id,
                parse_date(request.form.get('request_date')),
                request.form.get('title', '').strip(),
                request.form.get('description', '').strip() or None,
                request.form.get('reason', '').strip() or None,
                request.form.get('priority', 'Medium'),
                request.form.get('status', 'Open'),
                request.form.get('requested_by', '').strip() or None,
                parse_date(request.form.get('completion_date')),
                request.form.get('notes', '').strip() or None,
            )
        )
        conn.commit()
        flash("Change request added successfully.", "success")
    except Error:
        flash("A database error occurred while saving the change request.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('project_details', project_id=project_id))


@app.route('/change-request/edit/<int:change_request_id>', methods=['GET', 'POST'])
@login_required
def edit_change_request(change_request_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM change_requests WHERE change_request_id = %s",
            (change_request_id,)
        )
        cr = cursor.fetchone()

        project = None
        if cr is not None:
            project = get_project_or_none(cursor, cr['project_id'], user_id)
    except Error:
        flash("A database error occurred.", "error")
        return redirect(url_for('dashboard'))
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if cr is None or project is None:
        flash("Change request not found.", "error")
        return redirect(url_for('dashboard'))

    if request.method == 'GET':
        return render_template(
            'change_request_form.html',
            project=project,
            cr=cr,
            priorities=VALID_CR_PRIORITIES,
            statuses=VALID_CR_STATUSES,
            form_action=url_for('edit_change_request', change_request_id=change_request_id)
        )

    errors = validate_change_request_form(request.form)
    if errors:
        for message in errors:
            flash(message, "error")
        merged = dict(cr)
        merged.update(request.form)
        return render_template(
            'change_request_form.html',
            project=project,
            cr=merged,
            priorities=VALID_CR_PRIORITIES,
            statuses=VALID_CR_STATUSES,
            form_action=url_for('edit_change_request', change_request_id=change_request_id)
        )

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE change_requests
            SET request_date = %s,
                title = %s,
                description = %s,
                reason = %s,
                priority = %s,
                status = %s,
                requested_by = %s,
                completion_date = %s,
                notes = %s
            WHERE change_request_id = %s
            """,
            (
                parse_date(request.form.get('request_date')),
                request.form.get('title', '').strip(),
                request.form.get('description', '').strip() or None,
                request.form.get('reason', '').strip() or None,
                request.form.get('priority', 'Medium'),
                request.form.get('status', 'Open'),
                request.form.get('requested_by', '').strip() or None,
                parse_date(request.form.get('completion_date')),
                request.form.get('notes', '').strip() or None,
                change_request_id
            )
        )
        conn.commit()
        flash("Change request updated successfully.", "success")
    except Error:
        flash("A database error occurred while updating the change request.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('project_details', project_id=cr['project_id']))


@app.route('/change-request/delete/<int:change_request_id>', methods=['POST'])
@login_required
def delete_change_request(change_request_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    project_id = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT project_id FROM change_requests WHERE change_request_id = %s",
            (change_request_id,)
        )
        row = cursor.fetchone()
        if row is None:
            flash("Change request not found.", "error")
            return redirect(url_for('dashboard'))
        project_id = row['project_id']
        project = get_project_or_none(cursor, project_id, user_id)
        if not project:
            flash("Not authorized.", "error")
            return redirect(url_for('dashboard'))

        cursor.execute(
            "DELETE FROM change_requests WHERE change_request_id = %s",
            (change_request_id,)
        )
        conn.commit()
        flash("Change request deleted successfully.", "success")
    except Error:
        flash("A database error occurred while deleting the change request.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

# ---------------------------------------------------------------
# Project Milestones
# ---------------------------------------------------------------

@app.route('/project/<int:project_id>/milestone/add', methods=['GET', 'POST'])
@login_required
def add_milestone(project_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        project = get_project_or_none(cursor, project_id, user_id)
    except Error:
        logger.exception("add_milestone GET: DB error")
        flash("A database error occurred.", "error")
        return redirect(url_for('dashboard'))
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if project is None:
        flash("Project not found.", "error")
        return redirect(url_for('dashboard'))

    if request.method == 'GET':
        return render_template(
            'milestone_form.html',
            project=project,
            milestone=None,
            statuses=VALID_MILESTONE_STATUSES,
            form_action=url_for('add_milestone', project_id=project_id)
        )

    errors = validate_milestone_form(request.form)
    if errors:
        for message in errors:
            flash(message, "error")
        return render_template(
            'milestone_form.html',
            project=project,
            milestone=request.form,
            statuses=VALID_MILESTONE_STATUSES,
            form_action=url_for('add_milestone', project_id=project_id)
        )

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO project_milestones
                (project_id, title, description, due_date, status, completion_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                project_id,
                request.form.get('title', '').strip(),
                request.form.get('description', '').strip() or None,
                parse_date(request.form.get('due_date')),
                request.form.get('status', 'Pending'),
                parse_date(request.form.get('completion_date')),
            )
        )
        conn.commit()
        flash("Milestone added successfully.", "success")
    except Error:
        logger.exception("add_milestone POST: DB error")
        flash("A database error occurred while saving the milestone.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('project_details', project_id=project_id))


@app.route('/milestone/edit/<int:milestone_id>', methods=['GET', 'POST'])
@login_required
def edit_milestone(milestone_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM project_milestones WHERE milestone_id = %s",
            (milestone_id,)
        )
        milestone = cursor.fetchone()

        project = None
        if milestone is not None:
            project = get_project_or_none(cursor, milestone['project_id'], user_id)
    except Error:
        logger.exception("edit_milestone GET: DB error")
        flash("A database error occurred.", "error")
        return redirect(url_for('dashboard'))
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if milestone is None or project is None:
        flash("Milestone not found.", "error")
        return redirect(url_for('dashboard'))

    if request.method == 'GET':
        return render_template(
            'milestone_form.html',
            project=project,
            milestone=milestone,
            statuses=VALID_MILESTONE_STATUSES,
            form_action=url_for('edit_milestone', milestone_id=milestone_id)
        )

    errors = validate_milestone_form(request.form)
    if errors:
        for message in errors:
            flash(message, "error")
        merged = dict(milestone)
        merged.update(request.form)
        return render_template(
            'milestone_form.html',
            project=project,
            milestone=merged,
            statuses=VALID_MILESTONE_STATUSES,
            form_action=url_for('edit_milestone', milestone_id=milestone_id)
        )

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE project_milestones
            SET title = %s,
                description = %s,
                due_date = %s,
                status = %s,
                completion_date = %s
            WHERE milestone_id = %s
            """,
            (
                request.form.get('title', '').strip(),
                request.form.get('description', '').strip() or None,
                parse_date(request.form.get('due_date')),
                request.form.get('status', 'Pending'),
                parse_date(request.form.get('completion_date')),
                milestone_id
            )
        )
        conn.commit()
        flash("Milestone updated successfully.", "success")
    except Error:
        logger.exception("edit_milestone POST: DB error")
        flash("A database error occurred while updating the milestone.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('project_details', project_id=milestone['project_id']))


@app.route('/milestone/delete/<int:milestone_id>', methods=['POST'])
@login_required
def delete_milestone(milestone_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    project_id = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT project_id FROM project_milestones WHERE milestone_id = %s",
            (milestone_id,)
        )
        row = cursor.fetchone()
        if row is None:
            flash("Milestone not found.", "error")
            return redirect(url_for('dashboard'))
        project_id = row['project_id']
        project = get_project_or_none(cursor, project_id, user_id)
        if not project:
            flash("Not authorized.", "error")
            return redirect(url_for('dashboard'))

        cursor.execute(
            "DELETE FROM project_milestones WHERE milestone_id = %s",
            (milestone_id,)
        )
        conn.commit()
        flash("Milestone deleted successfully.", "success")
    except Error:
        logger.exception("delete_milestone: DB error")
        flash("A database error occurred while deleting the milestone.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if project_id is None:
        return redirect(url_for('dashboard'))
    return redirect(url_for('project_details', project_id=project_id))


@app.route('/milestone/toggle/<int:milestone_id>', methods=['POST'])
@login_required
def toggle_milestone(milestone_id):
    """Quick toggle milestone between Completed and Pending/In Progress, syncing all sub-tasks."""
    user_id = session['user_id']
    conn = None
    cursor = None
    project_id = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM project_milestones WHERE milestone_id = %s",
            (milestone_id,)
        )
        milestone = cursor.fetchone()
        if milestone is None:
            flash("Milestone not found.", "error")
            return redirect(url_for('dashboard'))
        project_id = milestone['project_id']
        project = get_project_or_none(cursor, project_id, user_id)
        if not project:
            flash("Not authorized.", "error")
            return redirect(url_for('dashboard'))

        if milestone['status'] == 'Completed':
            new_status = 'In Progress'
            new_completion = None
            msg = f"Milestone '{milestone['title']}' marked as In Progress."
            task_status = 0
        else:
            new_status = 'Completed'
            new_completion = date.today().strftime('%Y-%m-%d')
            msg = f"Milestone '{milestone['title']}' marked as Completed!"
            task_status = 1

        cursor.execute(
            """
            UPDATE project_milestones
            SET status = %s, completion_date = %s
            WHERE milestone_id = %s
            """,
            (new_status, new_completion, milestone_id)
        )

        # Sync all sub-tasks of this milestone
        cursor.execute(
            "UPDATE milestone_tasks SET is_completed = %s WHERE milestone_id = %s",
            (task_status, milestone_id)
        )

        conn.commit()
        flash(msg, "success")
    except Error:
        logger.exception("toggle_milestone: DB error")
        flash("A database error occurred while updating the milestone status.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if project_id is None:
        return redirect(url_for('dashboard'))
    return redirect(request.referrer or url_for('project_details', project_id=project_id))


# ---------------------------------------------------------------
# Milestone Sub-Tasks
# ---------------------------------------------------------------

@app.route('/milestone/<int:milestone_id>/task/add', methods=['POST'])
@login_required
def add_task(milestone_id):
    user_id = session['user_id']
    task_title = request.form.get('task_title', '').strip()
    due_date = parse_date(request.form.get('due_date'))

    if not task_title:
        flash("Task title is required.", "error")
        return redirect(request.referrer or url_for('dashboard'))

    conn = None
    cursor = None
    project_id = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT project_id, status FROM project_milestones WHERE milestone_id = %s",
            (milestone_id,)
        )
        milestone = cursor.fetchone()
        if milestone is None:
            flash("Milestone not found.", "error")
            return redirect(url_for('dashboard'))
        project_id = milestone['project_id']
        project = get_project_or_none(cursor, project_id, user_id)
        if not project:
            flash("Not authorized.", "error")
            return redirect(url_for('dashboard'))

        cursor.execute(
            """
            INSERT INTO milestone_tasks (milestone_id, task_title, is_completed, due_date)
            VALUES (%s, %s, 0, %s)
            """,
            (milestone_id, task_title, due_date)
        )

        # If the milestone was marked Completed, revert it to In Progress since a new pending task is added
        if milestone['status'] == 'Completed':
            cursor.execute(
                "UPDATE project_milestones SET status = 'In Progress', completion_date = NULL WHERE milestone_id = %s",
                (milestone_id,)
            )

        conn.commit()
        flash(f"Task '{task_title}' added.", "success")
    except Error:
        logger.exception("add_task: DB error")
        flash("A database error occurred while adding the task.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if project_id is None:
        return redirect(url_for('dashboard'))
    return redirect(request.referrer or url_for('project_details', project_id=project_id))


@app.route('/task/toggle/<int:task_id>', methods=['POST'])
@login_required
def toggle_task(task_id):
    """Toggle a task between complete and incomplete, automatically checking milestone completion."""
    user_id = session['user_id']
    conn = None
    cursor = None
    project_id = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT t.*, m.project_id, m.status AS milestone_status
            FROM milestone_tasks t
            INNER JOIN project_milestones m ON t.milestone_id = m.milestone_id
            WHERE t.task_id = %s
            """,
            (task_id,)
        )
        task = cursor.fetchone()
        if task is None:
            flash("Task not found.", "error")
            return redirect(url_for('dashboard'))
        project_id = task['project_id']
        project = get_project_or_none(cursor, project_id, user_id)
        if not project:
            flash("Not authorized.", "error")
            return redirect(url_for('dashboard'))
        milestone_id = task['milestone_id']

        new_val = 0 if task['is_completed'] else 1
        cursor.execute(
            "UPDATE milestone_tasks SET is_completed = %s WHERE task_id = %s",
            (new_val, task_id)
        )

        # Check all sibling tasks of this milestone
        cursor.execute(
            "SELECT is_completed FROM milestone_tasks WHERE milestone_id = %s",
            (milestone_id,)
        )
        sibling_tasks = cursor.fetchall()

        all_done = all(st['is_completed'] for st in sibling_tasks)
        if all_done and sibling_tasks:
            # Auto-mark milestone completed
            cursor.execute(
                "UPDATE project_milestones SET status = 'Completed', completion_date = %s WHERE milestone_id = %s",
                (date.today().strftime('%Y-%m-%d'), milestone_id)
            )
        elif not all_done and task['milestone_status'] == 'Completed':
            # Revert milestone to In Progress
            cursor.execute(
                "UPDATE project_milestones SET status = 'In Progress', completion_date = NULL WHERE milestone_id = %s",
                (milestone_id,)
            )

        conn.commit()
    except Error:
        logger.exception("toggle_task: DB error")
        flash("A database error occurred while updating the task.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if project_id is None:
        return redirect(url_for('dashboard'))
    return redirect(request.referrer or url_for('project_details', project_id=project_id))


@app.route('/task/delete/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    project_id = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT m.project_id
            FROM milestone_tasks t
            INNER JOIN project_milestones m ON t.milestone_id = m.milestone_id
            WHERE t.task_id = %s
            """,
            (task_id,)
        )
        row = cursor.fetchone()
        if row is None:
            flash("Task not found.", "error")
            return redirect(url_for('dashboard'))
        project_id = row['project_id']
        project = get_project_or_none(cursor, project_id, user_id)
        if not project:
            flash("Not authorized.", "error")
            return redirect(url_for('dashboard'))

        cursor.execute("DELETE FROM milestone_tasks WHERE task_id = %s", (task_id,))
        conn.commit()
        flash("Task deleted.", "success")
    except Error:
        logger.exception("delete_task: DB error")
        flash("A database error occurred while deleting the task.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if project_id is None:
        return redirect(url_for('dashboard'))
    return redirect(request.referrer or url_for('project_details', project_id=project_id))


# ---------------------------------------------------------------
# Settings (Manage Guides, Assigned By, Tags & Password)
# ---------------------------------------------------------------

@app.route('/settings')
@login_required
def settings():
    user_id = session['user_id']
    conn = None
    cursor = None
    guides = []
    assigned_by_persons = []
    tags = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        guides = get_all_guides(cursor, user_id)
        assigned_by_persons = get_all_assigned_by(cursor, user_id)
        tags = get_all_tags(cursor, user_id)
    except Error:
        logger.exception("settings GET: DB error")
        flash("A database error occurred while loading settings.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return render_template(
        'settings.html',
        guides=guides,
        assigned_by_persons=assigned_by_persons,
        tags=tags
    )


@app.route('/settings/change-password', methods=['POST'])
@login_required
def change_password():
    user_id = session['user_id']
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not current_password or not new_password or not confirm_password:
        flash("Please fill in all password fields.", "error")
        return redirect(url_for('settings'))

    if len(new_password) < 6:
        flash("New password must be at least 6 characters long.", "error")
        return redirect(url_for('settings'))

    if new_password != confirm_password:
        flash("New password and confirm password do not match.", "error")
        return redirect(url_for('settings'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT password_hash FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        if not user or not check_password_hash(user['password_hash'], current_password):
            flash("Current password is incorrect.", "error")
            return redirect(url_for('settings'))

        new_hash = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (new_hash, user_id))
        conn.commit()
        flash("Your password has been changed successfully!", "success")
    except Error:
        logger.exception("change_password: DB error")
        flash("A database error occurred while updating your password.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('settings'))


@app.route('/settings/guide/add', methods=['POST'])
@login_required
def add_guide():
    user_id = session['user_id']
    name = request.form.get('name', '').strip()
    if not name:
        flash("Guide name is required.", "error")
        return redirect(url_for('settings'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO guides (name, user_id) VALUES (%s, %s)", (name, user_id))
        conn.commit()
        flash(f"Guide '{name}' added successfully.", "success")
    except Error:
        logger.exception("add_guide: DB error")
        flash("A database error occurred while adding the guide.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('settings'))


@app.route('/settings/guide/delete/<int:guide_id>', methods=['POST'])
@login_required
def delete_guide(guide_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM guides WHERE guide_id = %s AND user_id = %s", (guide_id, user_id))
        conn.commit()
        flash("Guide deleted successfully.", "success")
    except Error:
        logger.exception("delete_guide: DB error")
        flash("A database error occurred while deleting the guide.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('settings'))


@app.route('/settings/assigned-by/add', methods=['POST'])
@login_required
def add_assigned_by():
    user_id = session['user_id']
    name = request.form.get('name', '').strip()
    if not name:
        flash("Person name is required.", "error")
        return redirect(url_for('settings'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO assigned_by_persons (name, user_id) VALUES (%s, %s)", (name, user_id))
        conn.commit()
        flash(f"Assigned By person '{name}' added successfully.", "success")
    except Error:
        logger.exception("add_assigned_by: DB error")
        flash("A database error occurred while adding the person.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('settings'))


@app.route('/settings/assigned-by/delete/<int:person_id>', methods=['POST'])
@login_required
def delete_assigned_by(person_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM assigned_by_persons WHERE person_id = %s AND user_id = %s", (person_id, user_id))
        conn.commit()
        flash("Person deleted successfully.", "success")
    except Error:
        logger.exception("delete_assigned_by: DB error")
        flash("A database error occurred while deleting the person.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('settings'))


@app.route('/settings/tag/add', methods=['POST'])
@login_required
def add_tag():
    user_id = session['user_id']
    name = request.form.get('name', '').strip()
    color = request.form.get('color', '#3b82f6').strip()
    if not name:
        flash("Tag name is required.", "error")
        return redirect(url_for('settings'))

    if not color:
        color = '#3b82f6'

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tags (name, color, user_id) VALUES (%s, %s, %s)", (name, color, user_id))
        conn.commit()
        flash(f"Tag '{name}' added successfully.", "success")
    except Error:
        logger.exception("add_tag: DB error")
        flash("A database error occurred while adding the tag.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('settings'))


@app.route('/settings/tag/delete/<int:tag_id>', methods=['POST'])
@login_required
def delete_tag(tag_id):
    user_id = session['user_id']
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tags WHERE tag_id = %s AND user_id = %s", (tag_id, user_id))
        conn.commit()
        flash("Tag deleted successfully.", "success")
    except Error:
        logger.exception("delete_tag: DB error")
        flash("A database error occurred while deleting the tag.", "error")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for('settings'))


# ---------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    logger.warning("404 hit: %s", request.url)
    flash("The page you requested was not found.", "error")
    return redirect(url_for('dashboard'))


@app.errorhandler(500)
def server_error(e):
    flash("An unexpected server error occurred.", "error")
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)

