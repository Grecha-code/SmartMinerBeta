from flask import Flask, render_template, redirect, url_for, request, make_response
from http.client import HTTPException
from dotenv import load_dotenv
import psycopg2
import hashlib
import os

load_dotenv()
app = Flask(__name__)
users_data = os.getenv("users_data")
rights = ["User", "Admin"]


def hashing(password):
    if password is None:
        password = ""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def init_db():
    conn = None
    try:
        conn = psycopg2.connect(users_data)
        with conn.cursor() as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    login TEXT NOT NULL,
                    password TEXT NOT NULL,
                    rights TEXT NOT NULL
                )
            ''')
        conn.commit()
    except Exception:
        pass
    finally:
        if conn:
            conn.close()


def check_user_data(login, password):
    init_db()
    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM users WHERE login = %s AND password = %s LIMIT 1", (login, password))
                return bool(cursor.fetchone())
    except Exception:
        return False


@app.route('/', methods=['GET', 'POST'])
def registration():
    if request.cookies.get('user_login'):
        return redirect(url_for('safety'))

    if request.method == 'POST':
        login = request.form.get('login')
        password = hashing(request.form.get('password'))

        if check_user_data(login, password):
            response = make_response(redirect(url_for('safety')))
            response.set_cookie('user_login', login, max_age=90*24*60*60)
            return response

        return render_template('registration.html')

    return render_template('registration.html')


@app.route('/safety')
def safety():
    return render_template('safety.html')


@app.route('/profile')
def profile():
    init_db()
    login = request.cookies.get('user_login')

    if not login:
        return redirect(url_for('registration'))

    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, login, rights FROM users WHERE login = %s", (login,))
                user_info = cursor.fetchone()

                if not user_info:
                    return render_template("error.html")

                return render_template('profile.html', user=user_info)
    except Exception:
        return render_template("error.html")


@app.route('/test')
def test():
    try:
        return render_template('test.html')
    except Exception:
        return ""


@app.errorhandler(HTTPException)
def handle_error(error):
    return render_template('error.html'), error.code


if __name__ == "__main__":
    app.run(debug=True)