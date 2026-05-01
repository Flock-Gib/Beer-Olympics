# 🍺 Gibs Juneteenth Beer Olympics

A fun event website for the annual Gibs Juneteenth Beer Olympics featuring:
- 🎉 RSVP collection
- 🏆 Team registration
- 🙌 Volunteer "bring items" signup
- 📸 Photo gallery with uploads

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

---

## Admin Dashboard

Navigate to `/admin` and log in with your `ADMIN_USERNAME` / `ADMIN_PASSWORD` credentials.

The dashboard shows:
- All RSVPs (with status: attending / not attending / maybe)
- All volunteer signups (with item category & description)
- All team registrations
- All uploaded photos (with thumbnails)

### CSV Exports (admin-only)

| Endpoint | Data |
|----------|------|
| `/export/rsvp` | All RSVPs as CSV |
| `/export/volunteers` | All volunteer signups as CSV |
| `/export/teams` | All team signups as CSV |

---

## Pages & Routes

| Route | Description |
|-------|-------------|
| `/` | Home page with countdown |
| `/rsvp` | General RSVP form |
| `/signup` | Team registration form |
| `/volunteer` | Volunteer "bring items" form |
| `/gallery` | Photo gallery + upload |
| `/event` | Event details |
| `/venmo` | Payment info |
| `/admin` | Admin login |
| `/dashboard` | Admin dashboard (protected) |

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

© 2025 Gibs Juneteenth Beer Olympics. All rights reserved.
