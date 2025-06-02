from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import datetime

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_secret_key_here')

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '/etc/secrets/creds.json')  # Updated for Render
creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
client = gspread.authorize(creds)
sheet_signup = client.open("Gibs Juneteenth Beer Olympics Signups").sheet1
sheet_volunteer = client.open("Gibs Juneteenth Beer Olympics Volunteers").sheet1
sheet_rsvp = client.open("Gibs Juneteenth Beer Olympics General RSVPs").sheet1

# Admin credentials (from .env)
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'Flock1234!')

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    existing_rows = len(sheet_signup.get_all_values()) - 1
    if existing_rows >= 16:
        return "Signup is closed! All 16 team slots are filled."

    if request.method == 'POST':
        password = request.form.get('password')
        if password != 'juneteenth2025':
            flash('Incorrect password. Please try again.')
            return redirect(url_for('signup'))

        country = request.form['country']
        captain_name = request.form['captain_name']
        captain_email = request.form['captain_email']
        teammate_name = request.form['teammate_name']
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        sheet_signup.append_row([timestamp, country, captain_name, teammate_name, captain_email])
        flash('Your team has been successfully signed up!')
        return redirect(url_for('index'))

    return render_template('signup.html')

@app.route('/rsvp', methods=['POST'])
def rsvp():
    name = request.form['guest_name']
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet_rsvp.append_row([timestamp, name])
    flash(f'Thank you, {name}! Your RSVP has been received.')
    return redirect(url_for('index'))

@app.route('/volunteer', methods=['GET', 'POST'])
def volunteer():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        contribution = request.form['contribution']
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        sheet_volunteer.append_row([timestamp, name, email, phone, contribution])
        flash('Thank you for signing up as a volunteer!')
        return redirect(url_for('index'))

    return render_template('volunteer.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin'] = True
            flash('Welcome, Admin!')
            return redirect(url_for('dashboard'))
        else:
            flash('Incorrect login. Try again.')
            return redirect(url_for('admin'))
    return render_template('admin.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('admin'):
        flash('Please log in as admin.')
        return redirect(url_for('admin'))

    signup_data = sheet_signup.get_all_values()
    volunteer_data = sheet_volunteer.get_all_values()
    rsvp_data = sheet_rsvp.get_all_values()

    return render_template('dashboard.html', signup_data=signup_data, volunteer_data=volunteer_data, rsvp_data=rsvp_data)

@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash('You have been logged out.')
    return redirect(url_for('index'))

@app.route('/venmo')
def venmo():
    return render_template('venmo.html')

@app.route('/event')
def event():
    return render_template('event.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

