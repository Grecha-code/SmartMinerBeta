from flask import Flask, render_template, redirect, url_for, request, make_response, session
from http.client import HTTPException
from dotenv import load_dotenv
import psycopg2
import hashlib
import os
import g4f
import json
import re
import random

load_dotenv()
app = Flask(__name__)
app.secret_key = os.urandom(24)
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

            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='test_passed';")
            if not cursor.fetchone():
                cursor.execute(
                    "ALTER TABLE users ADD COLUMN test_passed BOOLEAN DEFAULT FALSE, ADD COLUMN test_score INTEGER DEFAULT 0;")
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
                exists = bool(cursor.fetchone())

                if not exists:
                    cursor.execute("INSERT INTO users (login, password, rights) VALUES (%s, %s, %s)",
                                   (login, password, rights[0]))
                    conn.commit()
                    return True
                return True
    except Exception as e:
        print(e)
        return False


def generate_safety_module():
    prompt = """
    Сгенерируй короткий обучающий модуль по технике безопасности для шахтеров.
    Ответь ТОЛЬКО валидным JSON форматом, без markdown разметки и лишнего текста.
    Структура строго такая:
    {
        "title": "Название темы",
        "theory": "Текст теории (3-4 предложения)",
        "questions": [
            {"q": "Вопрос 1", "options": ["Вариант 1", "Вариант 2", "Вариант 3"], "correct": 0},
            {"q": "Вопрос 2", "options": ["Вариант 1", "Вариант 2", "Вариант 3"], "correct": 1},
            {"q": "Вопрос 3", "options": ["Вариант 1", "Вариант 2", "Вариант 3"], "correct": 2},
            {"q": "Вопрос 4", "options": ["Вариант 1", "Вариант 2", "Вариант 3"], "correct": 0},
            {"q": "Вопрос 5", "options": ["Вариант 1", "Вариант 2", "Вариант 3"], "correct": 1}
        ]
    }
    """
    response = g4f.ChatCompletion.create(
        model=g4f.models.gpt_4,
        messages=[{"role": "user", "content": prompt}]
    )
    cleaned = re.sub(r'```json\n|```', '', response).strip()
    return json.loads(cleaned)


@app.route('/', methods=['GET', 'POST'])
def registration():
    if request.cookies.get('user_login'):
        return redirect(url_for('safety'))

    if request.method == 'POST':
        login = request.form.get('login')
        password = hashing(request.form.get('miner_pass'))

        if check_user_data(login, password):
            response = make_response(redirect(url_for('safety')))
            response.set_cookie('user_login', login, max_age=90 * 24 * 60 * 60)
            return response
        return render_template('registration.html')
    return render_template('registration.html')


@app.route('/safety')
def safety():
    login = request.cookies.get('user_login')
    if not login:
        return redirect(url_for('registration'))

    test_passed = False
    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT test_passed FROM users WHERE login = %s", (login,))
                res = cursor.fetchone()
                if res and res[0]:
                    test_passed = True
    except Exception:
        pass

    if not test_passed and 'safety_module' not in session:
        session['safety_module'] = generate_safety_module()

    module = session.get('safety_module')
    return render_template('safety.html', module=module, test_passed=test_passed, show_nav=True)


@app.route('/test')
def test():
    if not request.cookies.get('user_login'):
        return redirect(url_for('registration'))

    module = session.get('safety_module')
    if not module:
        return redirect(url_for('safety'))

    return render_template('test.html', module=module, show_nav=True)


@app.route('/submit_test', methods=['POST'])
def submit_test():
    login = request.cookies.get('user_login')
    if not login:
        return redirect(url_for('registration'))

    module = session.get('safety_module')
    if not module:
        return redirect(url_for('safety'))

    score = 0
    questions = module.get('questions', [])

    for i, q in enumerate(questions):
        user_ans = request.form.get(f'q{i}')
        if user_ans is not None and int(user_ans) == q['correct']:
            score += 1

    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE users SET test_passed = TRUE, test_score = %s WHERE login = %s", (score, login))
        conn.commit()
    except Exception:
        pass

    session.pop('safety_module', None)
    return redirect(url_for('safety'))


@app.route('/statistics')
def statistics():
    login = request.cookies.get('user_login')
    if not login:
        return redirect(url_for('registration'))

    score, rank, total_users = 0, 0, 0
    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT test_score FROM users WHERE login = %s", (login,))
                res = cursor.fetchone()
                if res: score = res[0]

                cursor.execute("SELECT COUNT(*) FROM users WHERE test_score > %s", (score,))
                higher_scores = cursor.fetchone()[0]
                rank = higher_scores + 1

                cursor.execute("SELECT COUNT(*) FROM users WHERE test_passed = TRUE")
                total_users = cursor.fetchone()[0]
    except Exception:
        pass

    return render_template('statistics.html', score=score, rank=rank, total_users=total_users, show_nav=True)


@app.route('/profile')
def profile():
    login = request.cookies.get('user_login')
    if not login: return redirect(url_for('registration'))

    avatar_colors = ["863F3F", "3F6886", "5F3F86", "3F8662", "86683F"]
    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, login, rights FROM users WHERE login = %s", (login,))
                user_info = cursor.fetchone()
                if not user_info: return render_template("error.html")
                return render_template('profile.html', user=user_info, avatar_color=random.choice(avatar_colors),
                                       show_nav=True)
    except Exception:
        return render_template("error.html")


@app.route('/admin_panel', methods=['GET', 'POST'])
def admin_panel():
    login = request.cookies.get('user_login')
    if not login: return redirect(url_for('registration'))

    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:

                cursor.execute("SELECT rights FROM users WHERE login = %s", (login,))
                rights_res = cursor.fetchone()
                if not rights_res or rights_res[0] != 'Admin':
                    return redirect(url_for('safety'))

                if request.method == 'POST':
                    new_login = request.form.get('new_login')
                    new_pass = hashing(request.form.get('new_password'))

                    cursor.execute("INSERT INTO users (login, password, rights) VALUES (%s, %s, %s)",
                                   (new_login, new_pass, "User"))
                    conn.commit()

                cursor.execute("SELECT id, login, rights, test_score, test_passed FROM users ORDER BY test_score DESC")
                all_users = cursor.fetchall()

        return render_template('admin_panel.html', users=all_users, show_nav=True)
    except Exception:
        return render_template("error.html")


@app.errorhandler(HTTPException)
def handle_error(error):
    return render_template('error.html'), error.code


if __name__ == "__main__":
    app.run(debug=True)