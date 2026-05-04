from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_file, abort
)
import os
import sqlite3
import uuid
import datetime
import csv
import io
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# ── Event constants ──────────────────────────────────────────────────────────
EVENT_MONTH = 6   # June
EVENT_DAY   = 19  # Juneteenth

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.getenv('SECRET_KEY', 'change-me-in-production'))

# ── File upload settings ────────────────────────────────────────────────────
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif', 'heic'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Database ────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(app.root_path, 'data', 'beer_olympics.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                country TEXT NOT NULL,
                captain_name TEXT NOT NULL,
                captain_email TEXT,
                teammate_name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rsvp (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                status TEXT NOT NULL DEFAULT 'attending',
                guests INTEGER DEFAULT 0,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS volunteer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                category TEXT,
                item_description TEXT NOT NULL,
                quantity TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                uploader_name TEXT,
                caption TEXT,
                filename TEXT NOT NULL
            );
        """)


init_db()

# ── Admin credentials ───────────────────────────────────────────────────────
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', '')

# ── Helpers ─────────────────────────────────────────────────────────────────

def now_ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def allowed_file(filename):
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def admin_required():
    """Return redirect if not logged in, else None."""
    if not session.get('admin'):
        flash('Please log in as admin.')
        return redirect(url_for('admin'))
    return None


# ── Template context ─────────────────────────────────────────────────────────

@app.context_processor
def inject_event_info():
    """Inject dynamic year and event date string into every template."""
    now = datetime.datetime.now()
    today = now.date()
    year = today.year
    candidate = datetime.date(year, EVENT_MONTH, EVENT_DAY)
    if today > candidate:
        year += 1
    event_date_str = datetime.date(year, EVENT_MONTH, EVENT_DAY).strftime('%B %-d, %Y')
    return dict(current_year=today.year, event_year=year, event_date_str=event_date_str)


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    with get_db() as conn:
        team_count = conn.execute('SELECT COUNT(*) FROM teams').fetchone()[0]

    if team_count >= 16:
        flash('Signup is closed — all 16 cornhole team slots are filled!')
        return render_template('signup.html', closed=True)

    if request.method == 'POST':
        password = request.form.get('password', '')
        if password != os.getenv('EVENT_PASSWORD', 'juneteenth2025'):
            flash('Incorrect event password. Please try again.')
            return redirect(url_for('signup'))

        country = request.form.get('country', '').strip()
        captain_name = request.form.get('captain_name', '').strip()
        captain_email = request.form.get('captain_email', '').strip()
        teammate_name = request.form.get('teammate_name', '').strip()

        if not country or not captain_name or not teammate_name:
            flash('Please fill in all required fields.')
            return redirect(url_for('signup'))

        with get_db() as conn:
            conn.execute(
                'INSERT INTO teams (timestamp, country, captain_name, captain_email, teammate_name) VALUES (?,?,?,?,?)',
                (now_ts(), country, captain_name, captain_email, teammate_name)
            )
        flash('Your team has been successfully signed up! 🎉')
        return redirect(url_for('index'))

    return render_template('signup.html', closed=False)


@app.route('/rsvp', methods=['GET', 'POST'])
def rsvp():
    if request.method == 'POST':
        name = request.form.get('guest_name', '').strip()
        if not name:
            flash('Name is required for RSVP.')
            return redirect(url_for('rsvp'))

        email = request.form.get('email', '').strip()
        status = request.form.get('status', 'attending')
        guests_raw = request.form.get('guests', '0').strip()
        try:
            guests = max(0, int(guests_raw)) if guests_raw else 0
        except ValueError:
            guests = 0
        notes = request.form.get('notes', '').strip()

        with get_db() as conn:
            conn.execute(
                'INSERT INTO rsvp (timestamp, name, email, status, guests, notes) VALUES (?,?,?,?,?,?)',
                (now_ts(), name, email, status, guests, notes)
            )
        flash(f"Thank you, {name}! Your RSVP has been received. 🍺")
        return redirect(url_for('index'))

    return render_template('rsvp.html')


@app.route('/volunteer', methods=['GET', 'POST'])
def volunteer():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Name is required.')
            return redirect(url_for('volunteer'))

        item_description = request.form.get('item_description', '').strip()
        if not item_description:
            flash('Item description is required.')
            return redirect(url_for('volunteer'))

        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        category = request.form.get('category', 'Other')
        quantity = request.form.get('quantity', '').strip()
        notes = request.form.get('notes', '').strip()

        with get_db() as conn:
            conn.execute(
                'INSERT INTO volunteer (timestamp, name, email, phone, category, item_description, quantity, notes) '
                'VALUES (?,?,?,?,?,?,?,?)',
                (now_ts(), name, email, phone, category, item_description, quantity, notes)
            )
        flash('Thank you for volunteering to bring something! 🙌')
        return redirect(url_for('index'))

    return render_template('volunteer.html')


@app.route('/gallery', methods=['GET', 'POST'])
def gallery():
    if request.method == 'POST':
        uploader_name = request.form.get('uploader_name', '').strip()
        caption = request.form.get('caption', '').strip()

        if 'photo' not in request.files:
            flash('No file selected.')
            return redirect(url_for('gallery'))

        file = request.files['photo']
        if file.filename == '':
            flash('No file selected.')
            return redirect(url_for('gallery'))

        if not allowed_file(file.filename):
            flash('Invalid file type. Please upload a JPG, PNG, WEBP, GIF, or HEIC image.')
            return redirect(url_for('gallery'))

        original_name = secure_filename(file.filename)
        ext = original_name.rsplit('.', 1)[1].lower()
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file.save(save_path)

        with get_db() as conn:
            conn.execute(
                'INSERT INTO photos (timestamp, uploader_name, caption, filename) VALUES (?,?,?,?)',
                (now_ts(), uploader_name, caption, unique_name)
            )
        flash('Photo uploaded successfully! 📸')
        return redirect(url_for('gallery'))

    with get_db() as conn:
        photos = conn.execute(
            'SELECT * FROM photos ORDER BY id DESC'
        ).fetchall()

    return render_template('gallery.html', photos=photos)


# ── Admin ────────────────────────────────────────────────────────────────────

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin'] = True
            flash('Welcome, Admin! 👋')
            return redirect(url_for('dashboard'))
        flash('Incorrect credentials. Please try again.')
        return redirect(url_for('admin'))
    return render_template('admin.html')


@app.route('/dashboard')
def dashboard():
    guard = admin_required()
    if guard:
        return guard

    with get_db() as conn:
        teams = conn.execute('SELECT * FROM teams ORDER BY id').fetchall()
        rsvps = conn.execute('SELECT * FROM rsvp ORDER BY id').fetchall()
        volunteers = conn.execute('SELECT * FROM volunteer ORDER BY id').fetchall()
        photos = conn.execute('SELECT * FROM photos ORDER BY id DESC').fetchall()

    return render_template(
        'dashboard.html',
        teams=teams,
        rsvps=rsvps,
        volunteers=volunteers,
        photos=photos,
    )


@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash('You have been logged out.')
    return redirect(url_for('index'))


# ── CSV exports (admin-protected) ────────────────────────────────────────────

def _csv_response(rows, filename):
    if not rows:
        flash('No data to export.')
        return redirect(url_for('dashboard'))
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(rows[0].keys())
    for row in rows:
        writer.writerow(list(row))
    output = io.BytesIO(si.getvalue().encode('utf-8'))
    output.seek(0)
    return send_file(output, mimetype='text/csv',
                     as_attachment=True, download_name=filename)


@app.route('/export/rsvp')
def export_rsvp():
    guard = admin_required()
    if guard:
        return guard
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM rsvp ORDER BY id').fetchall()
    return _csv_response(rows, 'rsvp.csv')


@app.route('/export/volunteers')
def export_volunteers():
    guard = admin_required()
    if guard:
        return guard
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM volunteer ORDER BY id').fetchall()
    return _csv_response(rows, 'volunteers.csv')


@app.route('/export/teams')
def export_teams():
    guard = admin_required()
    if guard:
        return guard
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM teams ORDER BY id').fetchall()
    return _csv_response(rows, 'teams.csv')


# ── Misc pages ───────────────────────────────────────────────────────────────

@app.route('/rules')
def rules():
    return render_template('rules.html')


@app.route('/venmo')
def venmo():
    return render_template('venmo.html')


@app.route('/event')
def event():
    return render_template('event.html')


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(413)
def too_large(e):
    flash('File is too large. Maximum size is 16 MB.')
    return redirect(url_for('gallery'))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('FLASK_ENV') != 'production')

