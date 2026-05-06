from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_file, abort
)
import os
import uuid
import datetime
import csv
import io
import math
import random
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect as sa_inspect

# ── Event constants ──────────────────────────────────────────────────────────
EVENT_NAME  = "Juneteenth at Gibby's"
EVENT_MONTH = 6   # June
EVENT_DAY   = 19  # Juneteenth


def compute_event_year(today=None):
    """Return the active event year.

    Rolls over to next calendar year the day after EVENT_DAY (June 19), so
    June 20 onward the "active" year becomes current_year + 1.
    """
    if today is None:
        today = datetime.datetime.now().date()
    year = today.year
    candidate = datetime.date(year, EVENT_MONTH, EVENT_DAY)
    if today > candidate:
        year += 1
    return year


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
# Normalize Render-style postgres:// URLs to postgresql:// for SQLAlchemy
_raw_db_url = os.getenv('DATABASE_URL', '')
if _raw_db_url.startswith('postgres://'):
    _raw_db_url = _raw_db_url.replace('postgres://', 'postgresql://', 1)
if not _raw_db_url:
    _db_dir = os.path.join(app.root_path, 'data')
    os.makedirs(_db_dir, exist_ok=True)
    _raw_db_url = 'sqlite:///' + os.path.join(_db_dir, 'beer_olympics.db')

app.config['SQLALCHEMY_DATABASE_URI'] = _raw_db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ── Models ───────────────────────────────────────────────────────────────────

class Team(db.Model):
    __tablename__ = 'teams'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.Text, nullable=False)
    country = db.Column(db.Text, nullable=False)
    captain_name = db.Column(db.Text, nullable=False)
    captain_email = db.Column(db.Text)
    teammate_name = db.Column(db.Text, nullable=False)
    event_year = db.Column(db.Integer)


class RSVP(db.Model):
    __tablename__ = 'rsvp'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.Text, nullable=False)
    name = db.Column(db.Text, nullable=False)
    email = db.Column(db.Text)
    status = db.Column(db.Text, nullable=False, server_default='attending')
    guests = db.Column(db.Integer, server_default='0')
    notes = db.Column(db.Text)
    event_year = db.Column(db.Integer)


class Volunteer(db.Model):
    __tablename__ = 'volunteer'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.Text, nullable=False)
    name = db.Column(db.Text, nullable=False)
    email = db.Column(db.Text)
    phone = db.Column(db.Text)
    category = db.Column(db.Text)
    item_description = db.Column(db.Text, nullable=False)
    quantity = db.Column(db.Text)
    notes = db.Column(db.Text)
    event_year = db.Column(db.Integer)


class Photo(db.Model):
    __tablename__ = 'photos'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.Text, nullable=False)
    uploader_name = db.Column(db.Text)
    caption = db.Column(db.Text)
    filename = db.Column(db.Text, nullable=False)
    event_year = db.Column(db.Integer)


class Tournament(db.Model):
    __tablename__ = 'tournament'
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.Text, nullable=False)
    locked = db.Column(db.Integer, nullable=False, server_default='0')


class Match(db.Model):
    __tablename__ = 'matches'
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, nullable=False)
    round = db.Column(db.Integer, nullable=False)
    match_number = db.Column(db.Integer, nullable=False)
    team1_id = db.Column(db.Integer)
    team2_id = db.Column(db.Integer)
    winner_id = db.Column(db.Integer)
    team1_score = db.Column(db.Integer)
    team2_score = db.Column(db.Integer)
    next_match_id = db.Column(db.Integer)
    next_match_slot = db.Column(db.Integer)


def init_db():
    db.create_all()


_ALLOWED_EVENT_YEAR_TABLES = frozenset({'teams', 'rsvp', 'volunteer', 'photos'})


def _migrate_event_year():
    """Add event_year column to legacy tables if missing and backfill existing rows.

    Needed for SQLite local-dev databases that pre-date the event_year column.
    On a fresh Postgres DB created via create_all() this is a no-op.
    """
    insp = sa_inspect(db.engine)
    year = compute_event_year()
    with db.engine.connect() as conn:
        for table in _ALLOWED_EVENT_YEAR_TABLES:
            if not insp.has_table(table):
                continue
            col_names = [c['name'] for c in insp.get_columns(table)]
            if 'event_year' not in col_names:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN event_year INTEGER'))
            conn.execute(
                text(f'UPDATE {table} SET event_year = :year WHERE event_year IS NULL'),
                {'year': year},
            )
        conn.commit()


with app.app_context():
    init_db()
    _migrate_event_year()

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


def _get_active_tournament():
    """Return the most recent tournament row, or None."""
    return db.session.execute(
        db.select(Tournament).order_by(Tournament.id.desc())
    ).scalars().first()


def _cascade_clear_from_match(match_id):
    """
    When a match's winner changes, clear that winner's placement in the next
    match and cascade any further downstream placements (if those were also
    decided from the now-invalidated result).
    """
    match = db.session.get(Match, match_id)

    if not match or not match.next_match_id:
        return

    next_id = match.next_match_id
    slot = match.next_match_slot

    # If the next match also has a winner, cascade from there first
    next_match = db.session.get(Match, next_id)
    if next_match and next_match.winner_id:
        _cascade_clear_from_match(next_id)
        next_match.winner_id = None
        next_match.team1_score = None
        next_match.team2_score = None

    # Clear this match's winner from the appropriate slot in the next match
    if slot == 1:
        next_match.team1_id = None
    else:
        next_match.team2_id = None


def _place_winner_in_next(match_id, winner_id):
    """Place winner_id into the correct slot of this match's next match."""
    match = db.session.get(Match, match_id)
    if not match or not match.next_match_id:
        return
    next_match = db.session.get(Match, match.next_match_id)
    if not next_match:
        return
    if match.next_match_slot == 1:
        next_match.team1_id = winner_id
    else:
        next_match.team2_id = winner_id


def generate_bracket(event_year=None):
    """
    Generate a fresh single-elimination bracket from all current teams.
    Returns the new tournament_id, or None if fewer than 2 teams.
    """
    if event_year is None:
        event_year = compute_event_year()
    teams = db.session.execute(
        db.select(Team).filter_by(event_year=event_year).order_by(Team.id)
    ).scalars().all()
    n = len(teams)
    if n < 2:
        return None

    team_list = list(teams)
    random.shuffle(team_list)

    p = _next_power_of_two(n)
    num_rounds = int(math.log2(p))
    num_byes = p - n

    # Create tournament record
    tournament = Tournament(created_at=now_ts(), locked=0)
    db.session.add(tournament)
    db.session.flush()  # obtain tournament.id before creating matches
    tournament_id = tournament.id

    # Create all match rows for every round (empty at first)
    match_ids = {}  # (round, match_number) -> match_id
    for r in range(1, num_rounds + 1):
        num_matches = p // (2 ** r)
        for m in range(1, num_matches + 1):
            new_match = Match(
                tournament_id=tournament_id,
                round=r,
                match_number=m,
            )
            db.session.add(new_match)
            db.session.flush()  # obtain new_match.id
            match_ids[(r, m)] = new_match.id

    # Wire up next_match_id and next_match_slot for all non-final rounds
    for r in range(1, num_rounds):
        num_matches = p // (2 ** r)
        for m in range(1, num_matches + 1):
            next_match_num = (m + 1) // 2
            slot = 1 if m % 2 == 1 else 2
            match_obj = db.session.get(Match, match_ids[(r, m)])
            match_obj.next_match_id = match_ids[(r + 1, next_match_num)]
            match_obj.next_match_slot = slot

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
        t1_id = t1.id if t1 else None
        t2_id = t2.id if t2 else None
        mid = match_ids[(1, match_num)]
        match_obj = db.session.get(Match, mid)
        match_obj.team1_id = t1_id
        match_obj.team2_id = t2_id
        # Auto-advance team that has a bye
        auto_winner = None
        if t1_id and not t2_id:
            auto_winner = t1_id
        elif t2_id and not t1_id:
            auto_winner = t2_id

        if auto_winner:
            match_obj.winner_id = auto_winner
            _place_winner_in_next(mid, auto_winner)

    return tournament_id


def get_or_regenerate_bracket(event_year=None):
    """
    Return the active tournament, auto-regenerating if the bracket is not
    locked and the team roster has changed since it was last generated.
    Returns (tournament_row, was_regenerated).
    """
    if event_year is None:
        event_year = compute_event_year()
    t = _get_active_tournament()
    team_count = db.session.query(Team).filter_by(event_year=event_year).count()

    if team_count < 2:
        return None, False

    if t is not None and t.locked:
        return t, False

    # Count how many real teams are in the current bracket's round 1
    if t is not None:
        bracketed = db.session.execute(text(
            '''SELECT COUNT(DISTINCT team_id) FROM (
                   SELECT team1_id AS team_id FROM matches
                   WHERE tournament_id=:tid AND round=1 AND team1_id IS NOT NULL
                   UNION
                   SELECT team2_id AS team_id FROM matches
                   WHERE tournament_id=:tid AND round=1 AND team2_id IS NOT NULL
               ) subq'''
        ), {'tid': t.id}).scalar()
        if bracketed == team_count:
            return t, False  # roster unchanged

        # Roster changed — regenerate
        db.session.execute(
            text('DELETE FROM matches WHERE tournament_id = :tid'), {'tid': t.id}
        )
        db.session.delete(t)
        db.session.flush()

    new_tid = generate_bracket(event_year)
    if new_tid is None:
        return None, False
    new_t = db.session.get(Tournament, new_tid)
    return new_t, True


def build_bracket_context(tournament):
    """
    Build context dict for rendering bracket templates.
    Returns dict with keys: rounds, round_names, max_round, champion.
    """
    if tournament is None:
        return {'rounds': {}, 'round_names': {}, 'max_round': 0, 'champion': None}

    matches = db.session.execute(text(
        '''SELECT m.*,
                  t1.country AS team1_name,
                  t2.country AS team2_name,
                  w.country  AS winner_name
           FROM matches m
           LEFT JOIN teams t1 ON m.team1_id  = t1.id
           LEFT JOIN teams t2 ON m.team2_id  = t2.id
           LEFT JOIN teams w  ON m.winner_id = w.id
           WHERE m.tournament_id = :tid
           ORDER BY m.round, m.match_number'''
    ), {'tid': tournament.id}).fetchall()

    rounds = {}
    max_round = 0
    for m in matches:
        r = m.round
        rounds.setdefault(r, []).append(m)
        if r > max_round:
            max_round = r

    round_names = {r: _get_round_name(r, max_round) for r in rounds}
    champion = None
    if max_round and rounds.get(max_round):
        final = rounds[max_round][0]
        if final.winner_id:
            champion = final.winner_name

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
    today = datetime.datetime.now().date()
    year = compute_event_year(today)
    event_date_str = datetime.date(year, EVENT_MONTH, EVENT_DAY).strftime('%B %-d, %Y')
    return dict(
        current_year=today.year,
        event_year=year,
        event_date_str=event_date_str,
        event_name=EVENT_NAME,
    )


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    locked = False
    t = _get_active_tournament()
    if t and t.locked:
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

        team = Team(
            timestamp=now_ts(),
            country=country,
            captain_name=captain_name,
            captain_email=captain_email,
            teammate_name=teammate_name,
            event_year=compute_event_year(),
        )
        db.session.add(team)
        # Auto-regenerate bracket if not locked
        get_or_regenerate_bracket()
        db.session.commit()

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

        rsvp_entry = RSVP(
            timestamp=now_ts(),
            name=name,
            email=email,
            status=status,
            guests=guests,
            notes=notes,
            event_year=compute_event_year(),
        )
        db.session.add(rsvp_entry)
        db.session.commit()
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

        vol = Volunteer(
            timestamp=now_ts(),
            name=name,
            email=email,
            phone=phone,
            category=category,
            item_description=item_description,
            quantity=quantity,
            notes=notes,
            event_year=compute_event_year(),
        )
        db.session.add(vol)
        db.session.commit()
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

        photo = Photo(
            timestamp=now_ts(),
            uploader_name=uploader_name,
            caption=caption,
            filename=unique_name,
            event_year=compute_event_year(),
        )
        db.session.add(photo)
        db.session.commit()
        flash('Photo uploaded successfully! 📸')
        return redirect(url_for('gallery'))

    photos = db.session.execute(
        db.select(Photo)
        .filter_by(event_year=compute_event_year())
        .order_by(Photo.id.desc())
    ).scalars().all()

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

    selected_year = request.args.get('year', type=int, default=compute_event_year())

    teams = db.session.execute(
        db.select(Team).filter_by(event_year=selected_year).order_by(Team.id)
    ).scalars().all()
    rsvps = db.session.execute(
        db.select(RSVP).filter_by(event_year=selected_year).order_by(RSVP.id)
    ).scalars().all()
    volunteers = db.session.execute(
        db.select(Volunteer).filter_by(event_year=selected_year).order_by(Volunteer.id)
    ).scalars().all()
    photos = db.session.execute(
        db.select(Photo).filter_by(event_year=selected_year).order_by(Photo.id.desc())
    ).scalars().all()

    return render_template(
        'dashboard.html',
        teams=teams,
        rsvps=rsvps,
        volunteers=volunteers,
        photos=photos,
        selected_year=selected_year,
    )


@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash('You have been logged out.')
    return redirect(url_for('index'))


# ── Bracket routes ────────────────────────────────────────────────────────────

@app.route('/bracket')
def bracket():
    tournament, was_regenerated = get_or_regenerate_bracket()
    if was_regenerated:
        db.session.commit()
    ctx = build_bracket_context(tournament)
    team_count = db.session.query(Team).filter_by(event_year=compute_event_year()).count()
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

    tournament, was_regenerated = get_or_regenerate_bracket()
    if was_regenerated:
        db.session.commit()
    ctx = build_bracket_context(tournament)
    team_count = db.session.query(Team).filter_by(event_year=compute_event_year()).count()
    # Fetch all teams for the winner-selection dropdowns
    all_teams = db.session.execute(
        db.select(Team)
        .filter_by(event_year=compute_event_year())
        .order_by(Team.country)
    ).scalars().all()

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

    match = db.session.get(Match, match_id)
    if not match:
        flash('Match not found.')
        return redirect(url_for('admin_bracket'))

    if winner_id not in (match.team1_id, match.team2_id):
        flash('Winner must be one of the teams in this match.')
        return redirect(url_for('admin_bracket'))

    # If winner is being changed, cascade-clear downstream placements
    if match.winner_id and match.winner_id != winner_id:
        _cascade_clear_from_match(match_id)

    # Set the winner and optional scores
    match.winner_id = winner_id
    match.team1_score = t1_score
    match.team2_score = t2_score

    # Place winner in next match slot
    _place_winner_in_next(match_id, winner_id)

    # Lock the tournament now that a result exists
    tournament = db.session.get(Tournament, match.tournament_id)
    if tournament:
        tournament.locked = 1

    db.session.commit()
    flash('Winner recorded! ✅')
    return redirect(url_for('admin_bracket'))


@app.route('/admin/bracket/reset', methods=['POST'])
def admin_bracket_reset():
    guard = admin_required()
    if guard:
        return guard

    t = _get_active_tournament()
    if t:
        db.session.execute(
            text('DELETE FROM matches WHERE tournament_id = :tid'), {'tid': t.id}
        )
        db.session.delete(t)
        db.session.flush()
    # Regenerate from current teams
    generate_bracket()
    db.session.commit()

    flash('Tournament bracket has been reset and regenerated. 🔄')
    return redirect(url_for('admin_bracket'))


# ── CSV exports (admin-protected) ────────────────────────────────────────────

def _model_to_dict(instance):
    """Convert a SQLAlchemy ORM model instance to an ordered dict."""
    return {c.key: getattr(instance, c.key)
            for c in sa_inspect(instance).mapper.column_attrs}


def _csv_response(rows, filename):
    if not rows:
        flash('No data to export.')
        return redirect(url_for('dashboard'))
    si = io.StringIO()
    writer = csv.writer(si)
    # rows may be ORM model instances or SQLAlchemy Row objects (text queries)
    if hasattr(rows[0], '_mapping'):
        # Row objects returned by db.session.execute(text(...))
        writer.writerow(rows[0]._mapping.keys())
        for row in rows:
            writer.writerow(list(row._mapping.values()))
    else:
        # ORM model instances
        dicts = [_model_to_dict(r) for r in rows]
        writer.writerow(dicts[0].keys())
        for d in dicts:
            writer.writerow(list(d.values()))
    output = io.BytesIO(si.getvalue().encode('utf-8'))
    output.seek(0)
    return send_file(output, mimetype='text/csv',
                     as_attachment=True, download_name=filename)


@app.route('/export/rsvp')
def export_rsvp():
    guard = admin_required()
    if guard:
        return guard
    selected_year = request.args.get('year', type=int, default=compute_event_year())
    rows = db.session.execute(
        db.select(RSVP).filter_by(event_year=selected_year).order_by(RSVP.id)
    ).scalars().all()
    return _csv_response(rows, f'rsvp_{selected_year}.csv')


@app.route('/export/volunteers')
def export_volunteers():
    guard = admin_required()
    if guard:
        return guard
    selected_year = request.args.get('year', type=int, default=compute_event_year())
    rows = db.session.execute(
        db.select(Volunteer).filter_by(event_year=selected_year).order_by(Volunteer.id)
    ).scalars().all()
    return _csv_response(rows, f'volunteers_{selected_year}.csv')


@app.route('/export/teams')
def export_teams():
    guard = admin_required()
    if guard:
        return guard
    selected_year = request.args.get('year', type=int, default=compute_event_year())
    rows = db.session.execute(
        db.select(Team).filter_by(event_year=selected_year).order_by(Team.id)
    ).scalars().all()
    return _csv_response(rows, f'teams_{selected_year}.csv')


@app.route('/export/bracket')
def export_bracket():
    guard = admin_required()
    if guard:
        return guard
    t = _get_active_tournament()
    if not t:
        flash('No bracket exists yet.')
        return redirect(url_for('admin_bracket'))
    rows = db.session.execute(text(
        '''SELECT m.id, m.round, m.match_number,
                  t1.country AS team1, t2.country AS team2,
                  w.country  AS winner,
                  m.team1_score, m.team2_score
           FROM matches m
           LEFT JOIN teams t1 ON m.team1_id  = t1.id
           LEFT JOIN teams t2 ON m.team2_id  = t2.id
           LEFT JOIN teams w  ON m.winner_id = w.id
           WHERE m.tournament_id = :tid
           ORDER BY m.round, m.match_number'''
    ), {'tid': t.id}).fetchall()
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

