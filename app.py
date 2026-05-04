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
import math
import random
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

            CREATE TABLE IF NOT EXISTS tournament (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                locked INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                round INTEGER NOT NULL,
                match_number INTEGER NOT NULL,
                team1_id INTEGER,
                team2_id INTEGER,
                winner_id INTEGER,
                team1_score INTEGER,
                team2_score INTEGER,
                next_match_id INTEGER,
                next_match_slot INTEGER
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


# ── Bracket helpers ──────────────────────────────────────────────────────────

def _next_power_of_two(n):
    """Return smallest power of 2 that is >= n."""
    if n <= 1:
        return 1
    return 2 ** math.ceil(math.log2(n))


def _get_round_name(r, max_round):
    """Return a human-friendly name for a given round number."""
    rounds_from_end = max_round - r
    if rounds_from_end == 0:
        return 'Final'
    if rounds_from_end == 1:
        return 'Semifinal'
    if rounds_from_end == 2:
        return 'Quarterfinal'
    return f'Round {r}'


def _get_active_tournament(conn):
    """Return the most recent tournament row, or None."""
    return conn.execute(
        'SELECT * FROM tournament ORDER BY id DESC LIMIT 1'
    ).fetchone()


def _cascade_clear_from_match(conn, match_id):
    """
    When a match's winner changes, clear that winner's placement in the next
    match and cascade any further downstream placements (if those were also
    decided from the now-invalidated result).
    """
    match = conn.execute(
        'SELECT next_match_id, next_match_slot FROM matches WHERE id=?',
        (match_id,)
    ).fetchone()

    if not match or not match['next_match_id']:
        return

    next_id = match['next_match_id']
    slot = match['next_match_slot']

    # If the next match also has a winner, cascade from there first
    next_match = conn.execute(
        'SELECT winner_id FROM matches WHERE id=?', (next_id,)
    ).fetchone()
    if next_match and next_match['winner_id']:
        _cascade_clear_from_match(conn, next_id)
        conn.execute(
            'UPDATE matches SET winner_id=NULL, team1_score=NULL, team2_score=NULL WHERE id=?',
            (next_id,)
        )

    # Clear this match's winner from the appropriate slot in the next match
    if slot == 1:
        conn.execute('UPDATE matches SET team1_id=NULL WHERE id=?', (next_id,))
    else:
        conn.execute('UPDATE matches SET team2_id=NULL WHERE id=?', (next_id,))


def _place_winner_in_next(conn, match_id, winner_id):
    """Place winner_id into the correct slot of this match's next match."""
    match = conn.execute(
        'SELECT next_match_id, next_match_slot FROM matches WHERE id=?',
        (match_id,)
    ).fetchone()
    if not match or not match['next_match_id']:
        return
    next_id = match['next_match_id']
    slot = match['next_match_slot']
    if slot == 1:
        conn.execute('UPDATE matches SET team1_id=? WHERE id=?', (winner_id, next_id))
    else:
        conn.execute('UPDATE matches SET team2_id=? WHERE id=?', (winner_id, next_id))


def generate_bracket(conn):
    """
    Generate a fresh single-elimination bracket from all current teams.
    Returns the new tournament_id, or None if fewer than 2 teams.
    """
    teams = conn.execute('SELECT id, country FROM teams ORDER BY id').fetchall()
    n = len(teams)
    if n < 2:
        return None

    team_list = list(teams)
    random.shuffle(team_list)

    p = _next_power_of_two(n)
    num_rounds = int(math.log2(p))
    num_byes = p - n

    # Create tournament record
    cur = conn.execute(
        'INSERT INTO tournament (created_at, locked) VALUES (?, 0)',
        (now_ts(),)
    )
    tournament_id = cur.lastrowid

    # Create all match rows for every round (empty at first)
    match_ids = {}  # (round, match_number) -> match_id
    for r in range(1, num_rounds + 1):
        num_matches = p // (2 ** r)
        for m in range(1, num_matches + 1):
            cur = conn.execute(
                '''INSERT INTO matches
                   (tournament_id, round, match_number,
                    team1_id, team2_id, winner_id,
                    team1_score, team2_score,
                    next_match_id, next_match_slot)
                   VALUES (?,?,?,NULL,NULL,NULL,NULL,NULL,NULL,NULL)''',
                (tournament_id, r, m)
            )
            match_ids[(r, m)] = cur.lastrowid

    # Wire up next_match_id and next_match_slot for all non-final rounds
    for r in range(1, num_rounds):
        num_matches = p // (2 ** r)
        for m in range(1, num_matches + 1):
            next_match_num = (m + 1) // 2
            slot = 1 if m % 2 == 1 else 2
            conn.execute(
                'UPDATE matches SET next_match_id=?, next_match_slot=? WHERE id=?',
                (match_ids[(r + 1, next_match_num)], slot, match_ids[(r, m)])
            )

    # Build round-1 pairings:
    #   - First num_byes teams each get a bye (1 team vs None)
    #   - Remaining teams form real matches (2 teams each)
    bye_matches = [(team_list[i], None) for i in range(num_byes)]
    real_teams = team_list[num_byes:]
    real_matches = [
        (real_teams[i * 2], real_teams[i * 2 + 1])
        for i in range(len(real_teams) // 2)
    ]
    pairings = bye_matches + real_matches

    for idx, (t1, t2) in enumerate(pairings):
        match_num = idx + 1
        t1_id = t1['id'] if t1 else None
        t2_id = t2['id'] if t2 else None
        mid = match_ids[(1, match_num)]
        conn.execute(
            'UPDATE matches SET team1_id=?, team2_id=? WHERE id=?',
            (t1_id, t2_id, mid)
        )
        # Auto-advance team that has a bye
        auto_winner = None
        if t1_id and not t2_id:
            auto_winner = t1_id
        elif t2_id and not t1_id:
            auto_winner = t2_id

        if auto_winner:
            conn.execute(
                'UPDATE matches SET winner_id=? WHERE id=?',
                (auto_winner, mid)
            )
            _place_winner_in_next(conn, mid, auto_winner)

    return tournament_id


def get_or_regenerate_bracket(conn):
    """
    Return the active tournament, auto-regenerating if the bracket is not
    locked and the team roster has changed since it was last generated.
    Returns (tournament_row, was_regenerated).
    """
    t = _get_active_tournament(conn)
    team_count = conn.execute('SELECT COUNT(*) FROM teams').fetchone()[0]

    if team_count < 2:
        return None, False

    if t is not None and t['locked']:
        return t, False

    # Count how many real teams are in the current bracket's round 1
    if t is not None:
        bracketed = conn.execute(
            '''SELECT COUNT(DISTINCT tid) FROM (
                   SELECT team1_id AS tid FROM matches
                   WHERE tournament_id=? AND round=1 AND team1_id IS NOT NULL
                   UNION
                   SELECT team2_id AS tid FROM matches
                   WHERE tournament_id=? AND round=1 AND team2_id IS NOT NULL
               )''',
            (t['id'], t['id'])
        ).fetchone()[0]
        if bracketed == team_count:
            return t, False  # roster unchanged

        # Roster changed — regenerate
        conn.execute('DELETE FROM matches WHERE tournament_id=?', (t['id'],))
        conn.execute('DELETE FROM tournament WHERE id=?', (t['id'],))

    new_tid = generate_bracket(conn)
    if new_tid is None:
        return None, False
    new_t = conn.execute('SELECT * FROM tournament WHERE id=?', (new_tid,)).fetchone()
    return new_t, True


def build_bracket_context(conn, tournament):
    """
    Build context dict for rendering bracket templates.
    Returns dict with keys: rounds, round_names, max_round, champion.
    """
    if tournament is None:
        return {'rounds': {}, 'round_names': {}, 'max_round': 0, 'champion': None}

    matches = conn.execute(
        '''SELECT m.*,
                  t1.country AS team1_name,
                  t2.country AS team2_name,
                  w.country  AS winner_name
           FROM matches m
           LEFT JOIN teams t1 ON m.team1_id  = t1.id
           LEFT JOIN teams t2 ON m.team2_id  = t2.id
           LEFT JOIN teams w  ON m.winner_id = w.id
           WHERE m.tournament_id = ?
           ORDER BY m.round, m.match_number''',
        (tournament['id'],)
    ).fetchall()

    rounds = {}
    max_round = 0
    for m in matches:
        r = m['round']
        rounds.setdefault(r, []).append(m)
        if r > max_round:
            max_round = r

    round_names = {r: _get_round_name(r, max_round) for r in rounds}
    champion = None
    if max_round and rounds.get(max_round):
        final = rounds[max_round][0]
        if final['winner_id']:
            champion = final['winner_name']

    return {
        'rounds': rounds,
        'round_names': round_names,
        'max_round': max_round,
        'champion': champion,
    }


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
        locked = False
        t = _get_active_tournament(conn)
        if t and t['locked']:
            locked = True

    if request.method == 'POST':
        if locked:
            flash('The tournament bracket is locked — new teams cannot be added until an admin resets the bracket.')
            return redirect(url_for('signup'))

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
            # Auto-regenerate bracket if not locked
            get_or_regenerate_bracket(conn)

        flash('Your team has been successfully signed up! 🎉')
        return redirect(url_for('index'))

    return render_template('signup.html', locked=locked)


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


# ── Bracket routes ────────────────────────────────────────────────────────────

@app.route('/bracket')
def bracket():
    with get_db() as conn:
        tournament, _ = get_or_regenerate_bracket(conn)
        ctx = build_bracket_context(conn, tournament)
        team_count = conn.execute('SELECT COUNT(*) FROM teams').fetchone()[0]
    return render_template(
        'bracket.html',
        tournament=tournament,
        team_count=team_count,
        **ctx,
    )


@app.route('/admin/bracket')
def admin_bracket():
    guard = admin_required()
    if guard:
        return guard

    with get_db() as conn:
        tournament, _ = get_or_regenerate_bracket(conn)
        ctx = build_bracket_context(conn, tournament)
        team_count = conn.execute('SELECT COUNT(*) FROM teams').fetchone()[0]
        # Fetch all teams for the winner-selection dropdowns
        all_teams = conn.execute('SELECT id, country FROM teams ORDER BY country').fetchall()

    return render_template(
        'admin_bracket.html',
        tournament=tournament,
        team_count=team_count,
        all_teams=all_teams,
        **ctx,
    )


@app.route('/admin/bracket/set-winner', methods=['POST'])
def admin_bracket_set_winner():
    guard = admin_required()
    if guard:
        return guard

    match_id = request.form.get('match_id', type=int)
    winner_id = request.form.get('winner_id', type=int)
    t1_score = request.form.get('team1_score', '').strip() or None
    t2_score = request.form.get('team2_score', '').strip() or None

    if not match_id or not winner_id:
        flash('Match ID and winner are required.')
        return redirect(url_for('admin_bracket'))

    with get_db() as conn:
        match = conn.execute('SELECT * FROM matches WHERE id=?', (match_id,)).fetchone()
        if not match:
            flash('Match not found.')
            return redirect(url_for('admin_bracket'))

        if winner_id not in (match['team1_id'], match['team2_id']):
            flash('Winner must be one of the teams in this match.')
            return redirect(url_for('admin_bracket'))

        # If winner is being changed, cascade-clear downstream placements
        if match['winner_id'] and match['winner_id'] != winner_id:
            _cascade_clear_from_match(conn, match_id)

        # Set the winner and optional scores
        conn.execute(
            'UPDATE matches SET winner_id=?, team1_score=?, team2_score=? WHERE id=?',
            (winner_id, t1_score, t2_score, match_id)
        )

        # Place winner in next match slot
        _place_winner_in_next(conn, match_id, winner_id)

        # Lock the tournament now that a result exists
        conn.execute(
            'UPDATE tournament SET locked=1 WHERE id=?',
            (match['tournament_id'],)
        )

    flash('Winner recorded! ✅')
    return redirect(url_for('admin_bracket'))


@app.route('/admin/bracket/reset', methods=['POST'])
def admin_bracket_reset():
    guard = admin_required()
    if guard:
        return guard

    with get_db() as conn:
        t = _get_active_tournament(conn)
        if t:
            conn.execute('DELETE FROM matches WHERE tournament_id=?', (t['id'],))
            conn.execute('DELETE FROM tournament WHERE id=?', (t['id'],))
        # Regenerate from current teams
        generate_bracket(conn)

    flash('Tournament bracket has been reset and regenerated. 🔄')
    return redirect(url_for('admin_bracket'))


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


@app.route('/export/bracket')
def export_bracket():
    guard = admin_required()
    if guard:
        return guard
    with get_db() as conn:
        t = _get_active_tournament(conn)
        if not t:
            flash('No bracket exists yet.')
            return redirect(url_for('admin_bracket'))
        rows = conn.execute(
            '''SELECT m.id, m.round, m.match_number,
                      t1.country AS team1, t2.country AS team2,
                      w.country  AS winner,
                      m.team1_score, m.team2_score
               FROM matches m
               LEFT JOIN teams t1 ON m.team1_id  = t1.id
               LEFT JOIN teams t2 ON m.team2_id  = t2.id
               LEFT JOIN teams w  ON m.winner_id = w.id
               WHERE m.tournament_id = ?
               ORDER BY m.round, m.match_number''',
            (t['id'],)
        ).fetchall()
    return _csv_response(rows, 'bracket.csv')


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

