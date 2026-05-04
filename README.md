# 🍺 Juneteenth at Gibby's

A fun event website for the annual **Juneteenth at Gibby's** celebration featuring:
- 🎉 RSVP collection
- 🏆 Dynamic single-elimination cornhole tournament bracket
- 🙌 Volunteer "bring items" signup
- 📸 Photo gallery with uploads
- 💵 Team entry fee display ($20/team) and Venmo donation support

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python / Flask |
| Database | SQLite (via Python `sqlite3`) |
| Frontend | HTML5, CSS3 (no JS framework) |
| Server | Gunicorn (production) |

---

## Quick Start (Local Development)

### Prerequisites
- Python 3.9+
- `pip`

### 1. Clone the repo

```bash
git clone https://github.com/Flock-Gib/Beer-Olympics.git
cd Beer-Olympics
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_SECRET_KEY` | `change-me-in-production` | Flask session secret — **change this in production** |
| `ADMIN_USERNAME` | `admin` | Admin dashboard username |
| `ADMIN_PASSWORD` | `Flock1234!` | Admin dashboard password — **change this in production** |
| `EVENT_PASSWORD` | `juneteenth2025` | Password attendees use to register teams |
| `FLASK_ENV` | `development` | Set to `production` on live server |

### 5. Run the development server

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

---

## Data & Storage

| What | Where |
|------|-------|
| SQLite database | `data/beer_olympics.db` (auto-created on first run) |
| Uploaded photos | `static/uploads/` (auto-created on first run) |

Both locations are excluded from git via `.gitignore`.

### Database tables

| Table | Description |
|-------|-------------|
| `teams` | Team sign-up records |
| `rsvp` | General RSVP records |
| `volunteer` | Volunteer "bring items" signups |
| `photos` | Photo upload metadata |
| `tournament` | Current bracket version and locked flag |
| `matches` | Individual match records with seeds, scores, and winners |

---

## Tournament Bracket

### How it works

The bracket is **single-elimination** and **auto-generates dynamically**:

1. **Auto-generation** — The bracket appears as soon as ≥ 2 teams sign up and updates automatically as more teams join (no page refresh needed on public `/bracket`).
2. **Any team count** — Works with any number of teams ≥ 2. Byes are automatically added to pad to the next power of two and are handled by auto-advancing the real team.
3. **Lock on first result** — The moment an admin records the first match winner, the bracket is **locked**. New teams can no longer be auto-inserted (this prevents changing matchups mid-tournament). A clear message is shown on the signup page.
4. **Admin reset** — The admin can click **"Reset & Regenerate"** in the bracket management panel to clear all results, unlock the bracket, and regenerate it from the current team list.

### Round naming

Round names are determined automatically based on bracket size:

| Rounds from end | Label |
|----------------|-------|
| 0 | Final |
| 1 | Semifinal |
| 2 | Quarterfinal |
| 3+ | Round N |

---

## Admin Dashboard

Navigate to `/admin` and log in with your `ADMIN_USERNAME` / `ADMIN_PASSWORD` credentials.

The dashboard shows:
- All RSVPs (with status: attending / not attending / maybe)
- All volunteer signups (with item category & description)
- All team registrations
- All uploaded photos (with thumbnails)

### Bracket management (admin only)

Visit `/admin/bracket` to:
- View the current bracket with all match states
- **Set a winner** for any match with both teams present (optionally enter scores)
- **Change a winner** — downstream placements are automatically cleared and recalculated
- **Reset & Regenerate** — clears all results, unlocks the bracket, and rebuilds from the current team list

### CSV Exports (admin-only)

| Endpoint | Data |
|----------|------|
| `/export/rsvp` | All RSVPs as CSV |
| `/export/volunteers` | All volunteer signups as CSV |
| `/export/teams` | All team signups as CSV |
| `/export/bracket` | All bracket matches with scores and winners as CSV |

---

## Pages & Routes

| Route | Description |
|-------|-------------|
| `/` | Home page with countdown |
| `/bracket` | Public tournament bracket (read-only, mobile-friendly) |
| `/rsvp` | General RSVP form |
| `/signup` | Team registration form (open while bracket is unlocked) |
| `/volunteer` | Volunteer "bring items" form |
| `/gallery` | Photo gallery + upload |
| `/rules` | Official cornhole rules |
| `/event` | Event details |
| `/venmo` | Payment info |
| `/admin` | Admin login |
| `/dashboard` | Admin dashboard (protected) |
| `/admin/bracket` | Admin bracket management (protected) |

---

## Photo Uploads

- Accepted formats: **JPG, JPEG, PNG, WEBP, GIF, HEIC**
- Maximum file size: **16 MB**
- Filenames are sanitized and prefixed with a UUID to prevent conflicts
- Files are stored in `static/uploads/`

---

## Production Deployment (Render / Heroku)

The `procfile` is already configured for Gunicorn:

```
web: gunicorn app:app
```

Set all environment variables in your hosting provider's dashboard (not in a committed `.env` file).

---

## License

© 2025 Juneteenth at Gibby's. All rights reserved.

---

## Team Entry &amp; Donations

| Type | Amount | Where to Pay |
|------|--------|-------------|
| **Team Entry** | **$20 per team** (2 players) | Venmo [@Gibson-StJohn](https://venmo.com/Gibson-StJohn) |
| **Supply Donation** | $5 / $10 / $20 (suggested) | Venmo [@Gibson-StJohn](https://venmo.com/Gibson-StJohn) |

Teams must pay and complete registration by **June 16th** to secure a spot.
Supply donations (ice, cups, charcoal, etc.) are welcome from anyone — players and non-players alike!

