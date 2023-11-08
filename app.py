import stripe
from flask import Flask, request, redirect, render_template, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import string
import random

app = Flask(__name__)
app.secret_key = '1234'
stripe.api_key = '[REDACTED]'
db_filename = 'url_shortener.db'
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


def create_db():
    conn = sqlite3.connect('url_shortener.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Create the short_urls table if it doesn't already exist
    c.execute('''
           CREATE TABLE IF NOT EXISTS short_urls (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               long_url TEXT NOT NULL,
               short_url TEXT NOT NULL UNIQUE,
               user_id INTEGER,
               click_count INTEGER DEFAULT 0,
               FOREIGN KEY (user_id) REFERENCES users(id)
           )
       ''')

    # Create the users table if it doesn't already exist
    c.execute('''
           CREATE TABLE IF NOT EXISTS users (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               username TEXT NOT NULL UNIQUE,
               password TEXT NOT NULL,
               email TEXT UNIQUE,
               is_premium INTEGER DEFAULT 0
           )
       ''')
    conn.commit()
    conn.close()


def init_db():
    with app.app_context():
        create_db()


def short_url_exists(short_url):
    conn = sqlite3.connect(db_filename)
    c = conn.cursor()
    c.execute('SELECT id FROM short_urls WHERE short_url = ?', (short_url,))
    row = c.fetchone()
    conn.close()
    return row is not None


def insert_url_mapping(long_url, user_id):
    conn = sqlite3.connect(db_filename)
    c = conn.cursor()

    # Attempt to create a unique short URL
    while True:
        short_url = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        if not short_url_exists(short_url):
            break

    c.execute('INSERT INTO short_urls (long_url, short_url, user_id) VALUES (?, ?, ?)',
              (long_url, short_url, user_id))
    conn.commit()
    conn.close()
    return short_url


def get_long_url(short_url):
    conn = sqlite3.connect(db_filename)
    c = conn.cursor()
    c.execute('SELECT long_url FROM short_urls WHERE short_url = ?', (short_url,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


@app.route('/', methods=['GET', 'POST'])
@login_required
def home():
    if request.method == 'POST':
        original_url = request.form.get('url')
        user_id = current_user.get_id()  # This assumes you have a get_id method in your user model
        short_url = insert_url_mapping(original_url, user_id)
        return render_template('home.html', short_url=short_url, long_url=original_url)
    return render_template('home.html')


@app.route('/<short_url>')
def redirect_to_long_url(short_url):
    conn = sqlite3.connect(db_filename)
    c = conn.cursor()
    c.execute('SELECT long_url, click_count FROM short_urls WHERE short_url = ?', (short_url,))
    row = c.fetchone()

    if row:
        long_url, click_count = row
        new_click_count = click_count + 1
        c.execute('UPDATE short_urls SET click_count = ? WHERE short_url = ?', (new_click_count, short_url))
        conn.commit()
        conn.close()
        return redirect(long_url)
    conn.close()
    return 'URL not found', 404


@app.route('/my_shortlinks')
@login_required
def my_shortlinks():
    user_id = current_user.get_id()
    conn = sqlite3.connect(db_filename)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM short_urls WHERE user_id = ?", (user_id,))
    shortlinks = [{
        'short_url': row['short_url'],
        'long_url': row['long_url'],
        'click_count': row['click_count']
    } for row in c.fetchall()]
    conn.close()
    return render_template('my_shortlinks.html', shortlinks=shortlinks)


@app.route('/upgrade')
@login_required
def premium_upgrade():
    return render_template('premium_upgrade.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')  # Assuming you want to collect an email address too

        # Hash the user's password
        hashed_password = generate_password_hash(password)

        conn = sqlite3.connect(db_filename)
        c = conn.cursor()

        # Insert the new user into the database
        c.execute('INSERT INTO users (username, password, email) VALUES (?, ?, ?)',
                  (username, hashed_password, email))

        conn.commit()
        conn.close()

        return redirect(url_for('login'))  # Redirect to the login page after registration
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect(db_filename)
        c = conn.cursor()

        # Fetch the user from the database
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            user_obj = User(user[0], user[1], user[2], user[3], user[4])
            login_user(user_obj)
            return redirect(url_for('home'))  # Redirect to the main page after login

        # If the login failed, reload the login page with an error message
        return render_template('login.html', error="Invalid username or password")

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))  # Redirect to the main page after logout


@app.route('/create-checkout-session', methods=['GET'])
@login_required
def create_checkout_session():
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    # TODO: replace this with the actual information of the product
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': 'Premium Subscription',
                        },
                        'unit_amount': 199,  # Price in cents
                    },
                    'quantity': 1,
                },
            ],
            mode='payment',
            success_url=url_for('success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('cancelled', _external=True),
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        return str(e)


@app.route('/success')
def success():
    user_id = current_user.get_id()
    conn = sqlite3.connect(db_filename)
    c = conn.cursor()

    # Update the user's premium status
    c.execute('UPDATE users SET is_premium = 1 WHERE id = ?', (user_id,))

    conn.commit()
    conn.close()

    # Flash a success message
    flash('Congratulations, you have been upgraded to premium!', 'success')

    # Redirect to the homepage
    return redirect(url_for('home'))


@app.route('/cancelled')
def cancelled():
    # Redirect to the homepage
    return redirect(url_for('home'))


class User(UserMixin):
    def __init__(self, id, username, password, email, is_premium):
        self.id = id
        self.username = username
        self.password = password
        self.email = email
        self.is_premium = is_premium


@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect(db_filename)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    if user:
        return User(str(user['id']), user['username'], user['password'], user['email'], user['is_premium'])
    return None


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
