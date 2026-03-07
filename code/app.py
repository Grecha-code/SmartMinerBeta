from flask import Flask, render_template, redirect, url_for, request
from werkzeug.exceptions import HTTPException
from dotenv import load_dotenv
import psycopg2
import sqlite3
import hashlib
import os

load_dotenv()
app = Flask(__name__)
users_data = os.getenv("users_data")


def hashing(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def get_users_data():
    try:
        conn = psycopg2.connect(users_data)
        cursor = conn.cursor()

        conn.commit()

        cursor.execute("SELECT * FROM users")
        rows = cursor.fetchall()

        return rows

    except Exception as error:
        print(f"Ошибка работы с бд: {error}")
        return []

    finally:
        if conn:
            cursor.close()
            conn.close()


def check_user_data(login, password):
    with psycopg2.connect(users_data) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM users WHERE login = %s AND password = %s LIMIT 1", (login, password))
            return True if cursor.fetchone() else False


@app.route('/')
def login_if_file_is_here():
    try:
        with open('user_data.db', 'r') as file:
            file.read()
            return redirect(url_for('safety'))
    except FileNotFoundError:
        return render_template('registration.html')


@app.route('/', methods=['GET', 'POST'])
def registration():
    if request.method == 'POST':
        login = request.form.get('login')
        password = hashing(request.form.get('password'))
        print(password)

        if check_user_data(login, password):
            conn = sqlite3.connect('user_data.db')
            cursor = conn.cursor()
            data = (login, password)

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    login TEXT NOT NULL,
                    password TEXT NOT NULL,
                    rights TEXT NOT NULL,
                    id INTEGER PRIMARY KEY AUTOINCREMENT
                )
            ''')
            cursor.execute("INSERT INTO users (login, password) VALUES (?, ?)", data)

            conn.commit()
            conn.close()

            return redirect(url_for('safety'))

        return render_template('registration.html')

    return None


@app.route('/safety')
def safety():
    return render_template('safety.html')


@app.errorhandler(HTTPException)
def handle_error(error):
    return render_template('error.html'), error.code


if  __name__ == "__main__":
    app.run(debug=True)
