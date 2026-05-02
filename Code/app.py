from flask import Flask, render_template, redirect, url_for, request, session, make_response
from werkzeug.exceptions import HTTPException
from dotenv import load_dotenv
import psycopg2
import hashlib
import os
import g4f
import json
import re
from datetime import date
import secrets
import webview
from threading import Thread
import random
import string
from captcha.image import ImageCaptcha

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or secrets.token_hex(32)
users_data = os.getenv("users_data")


def hashing(password):
    if password is None:
        password = ""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def generate_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']


def validate_csrf_token():
    token = session.get('csrf_token')
    form_token = request.form.get('csrf_token')
    if not token or not form_token:
        return False
    return secrets.compare_digest(token, form_token)


@app.context_processor
def inject_globals():
    return dict(csrf_token=generate_csrf_token())


@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response


def init_db():
    conn = None
    try:
        conn = psycopg2.connect(users_data)
        with conn.cursor() as cursor:
            cursor.execute('''
                            CREATE TABLE IF NOT EXISTS users (
                                id SERIAL PRIMARY KEY,
                                login TEXT NOT NULL UNIQUE,
                                password TEXT NOT NULL,
                                rights TEXT NOT NULL,
                                full_name TEXT,
                                test_score INTEGER DEFAULT 0,
                                total_questions INTEGER DEFAULT 0,
                                test_passed BOOLEAN DEFAULT FALSE,
                                last_test_date DATE
                            )
                        ''')
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='full_name';")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE users ADD COLUMN full_name TEXT;")
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='total_questions';")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE users ADD COLUMN total_questions INTEGER DEFAULT 0;")
        conn.commit()
    except Exception:
        pass
    finally:
        if conn: conn.close()


def check_user_data(login, password):
    init_db()
    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM users WHERE login = %s AND password = %s LIMIT 1", (login, password))
                return bool(cursor.fetchone())
    except Exception:
        return False


def generate_safety_module():
    prompt = """
    Сгенерируй короткий обучающий модуль по технике безопасности для шахтеров.
    Ответь ТОЛЬКО валидным JSON форматом, без markdown разметки и лишнего текста.
    Теория должна включать в себя текст, необходимый для прохождения теста. Теория и 
    ответы в тесте не должны быть слишком очевидными, а также не должна быть такой,
    как-будто шахтер видит её впервые. Создай все так, что это не простой тест из
    интернета, а оригинальный и действительно полезный.
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
    try:
        response = g4f.ChatCompletion.create(
            model=g4f.models.gpt_4,
            messages=[{"role": "user", "content": prompt}]
        )
        cleaned = re.sub(r'```json\n|```', '', response).strip()
        return json.loads(cleaned)
    except Exception:
        return {
            "title": "Базовые правила (Резервный модуль)",
            "theory": "Всегда проверяйте уровень метана перед началом забоя. Ношение каски и самоспасателя — обязательно на всех участках шахты. При задымлении немедленно надевайте самоспасатель и двигайтесь к выходу.",
            "questions": [
                {"q": "Что нужно проверить перед забоем?", "options": ["Давление", "Уровень метана", "Температуру"], "correct": 1},
                {"q": "Какая экипировка обязательна?", "options": ["Каска и самоспасатель", "Только перчатки", "Очки"], "correct": 0},
                {"q": "Что делать при задымлении?", "options": ["Искать очаг", "Надеть самоспасатель и выйти", "Ждать"], "correct": 1},
                {"q": "Можно ли включать технику при сломанной вентиляции?", "options": ["Да", "Только на 5 минут", "Категорически нет"], "correct": 2},
                {"q": "Как реагировать на обрушение крепи?", "options": ["Отойти на безопасное расстояние", "Подпереть руками", "Подойти ближе"], "correct": 0}
            ]
        }


@app.route('/captcha_image')
def captcha_image():
    image = ImageCaptcha(width=280, height=90)
    captcha_text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    session['captcha_text'] = captcha_text
    data = image.generate(captcha_text)
    response = make_response(data.getvalue())
    response.headers.set('Content-Type', 'image/png')
    response.headers.set('Cache-Control', 'no-cache, no-store, must-revalidate')
    return response


@app.route('/', methods=['GET', 'POST'])
def registration():
    if session.get('user_login'):
        return redirect(url_for('safety'))

    if request.method == 'POST':
        if not validate_csrf_token():
            return render_template('registration.html', error="Ошибка проверки безопасности")

        login = request.form.get('login', '')[:64]
        password = hashing(request.form.get('password', '')[:256])
        user_captcha = request.form.get('captcha_input', '').upper()
        correct_captcha = session.get('captcha_text', '')
        agreement = request.form.get('agreement')

        if not user_captcha or user_captcha != correct_captcha:
            return render_template('registration.html', error="Неверный код с картинки")

        if not agreement:
            return render_template('registration.html', error="Необходимо принять соглашение")

        if check_user_data(login, password):
            session.pop('captcha_text', None)
            session.clear()
            session['user_login'] = login
            return redirect(url_for('safety'))

        return render_template('registration.html', error="Ошибка доступа или неверные данные")

    return render_template('registration.html')


@app.route('/agreement')
def agreement():
    return render_template('agreement.html')


@app.route('/safety')
def safety():
    login = session.get('user_login')
    if not login:
        return redirect(url_for('registration'))

    test_passed = False
    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT test_passed, last_test_date FROM users WHERE login = %s", (login,))
                res = cursor.fetchone()
                if res:
                    db_passed, last_date = res
                    if db_passed and last_date != date.today():
                        cursor.execute("UPDATE users SET test_passed = FALSE WHERE login = %s", (login,))
                        conn.commit()
                        test_passed = False
                        session.pop('safety_module', None)
                    else:
                        test_passed = db_passed
    except Exception:
        pass

    if not test_passed and 'safety_module' not in session:
        session['safety_module'] = generate_safety_module()

    module = session.get('safety_module')
    return render_template('safety.html', module=module, test_passed=test_passed, show_nav=True)


@app.route('/test')
def test():
    if not session.get('user_login'):
        return redirect(url_for('registration'))
    module = session.get('safety_module')
    if not module:
        return redirect(url_for('safety'))
    return render_template('test.html', module=module, show_nav=True)


@app.route('/submit_test', methods=['POST'])
def submit_test():
    login = session.get('user_login')
    module = session.get('safety_module')
    if not login or not module:
        return redirect(url_for('safety'))
    if not validate_csrf_token():
        return redirect(url_for('safety'))

    questions = module.get('questions', [])
    score = 0
    total_q = len(questions)

    for i, q in enumerate(questions):
        user_ans = request.form.get(f'q{i}')
        if user_ans is not None:
            try:
                if int(user_ans) == q['correct']:
                    score += 1
            except (ValueError, TypeError):
                pass

    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE users
                    SET test_passed = TRUE,
                        last_test_date = CURRENT_DATE,
                        test_score = test_score + %s,
                        total_questions = total_questions + %s
                    WHERE login = %s
                """, (score, total_q, login))
    except Exception:
        pass

    session.pop('safety_module', None)
    return redirect(url_for('safety'))


@app.route('/statistics')
def statistics():
    login = session.get('user_login')
    if not login: return redirect(url_for('registration'))
    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT test_score FROM users WHERE login = %s", (login,))
                score_res = cursor.fetchone()
                score = score_res[0] if score_res else 0

                cursor.execute("SELECT COUNT(*) FROM users WHERE test_score > %s", (score,))
                rank_res = cursor.fetchone()
                rank = rank_res[0] + 1 if rank_res else 1

                cursor.execute("SELECT COUNT(*) FROM users WHERE test_passed = TRUE")
                total_res = cursor.fetchone()
                total_users = total_res[0] if total_res else 0

                cursor.execute("SELECT full_name, login, test_score FROM users ORDER BY test_score DESC LIMIT 10")
                leaders = cursor.fetchall()

        return render_template('statistics.html', score=score, rank=rank, leaders=leaders,
                               total_users=total_users, show_nav=True)
    except Exception:
        return render_template("error.html")


@app.route('/profile')
def profile():
    login = session.get('user_login')
    if not login: return redirect(url_for('registration'))
    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, login, rights, full_name, test_score, total_questions FROM users WHERE login = %s",
                    (login,))
                user_info = cursor.fetchone()
                score = user_info[4]
                total = user_info[5]
                percent = round((score / total * 100), 1) if total > 0 else 0
                return render_template('profile.html', user=user_info, percent=percent, avatar_color="863F3F")
    except Exception:
        return render_template("error.html")


@app.route('/delete_account', methods=['POST'])
def delete_account():
    login = session.get('user_login')
    if not login:
        return redirect(url_for('registration'))
    if not validate_csrf_token():
        return redirect(url_for('profile'))
    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM users WHERE login = %s", (login,))
        session.clear()
        return redirect(url_for('registration'))
    except Exception:
        return render_template("error.html")


@app.route('/admin_panel', methods=['GET', 'POST'])
def admin_panel():
    login = session.get('user_login')
    if not login or not session.get('admin_confirmed'):
        return redirect(url_for('admin_auth'))
    try:
        with psycopg2.connect(users_data) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT rights FROM users WHERE login = %s", (login,))
                user_rights = cursor.fetchone()
                if not user_rights or user_rights[0] != 'Admin':
                    return redirect(url_for('safety'))

                if request.method == 'POST':
                    if not validate_csrf_token():
                        return redirect(url_for('admin_panel'))
                    new_login = request.form.get('new_login', '')[:64]
                    new_pass = hashing(request.form.get('new_password', '')[:256])
                    new_role = request.form.get('new_role')
                    new_fio = request.form.get('new_fio', '')[:128]
                    if new_role not in ('Рабочий', 'Admin'):
                        new_role = 'Рабочий'
                    if new_login and new_fio:
                        cursor.execute(
                            "INSERT INTO users (login, password, rights, full_name) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                            (new_login, new_pass, new_role, new_fio)
                        )
                        conn.commit()

                cursor.execute(
                    "SELECT id, login, full_name, rights, test_score, total_questions FROM users ORDER BY id DESC")
                raw_users = cursor.fetchall()
                users_list = []
                for u in raw_users:
                    percent = round((u[4] / u[5] * 100), 1) if u[5] > 0 else 0
                    users_list.append({'id': u[0], 'login': u[1], 'fio': u[2], 'role': u[3], 'percent': percent})

        return render_template('admin_panel.html', users=users_list, show_nav=True)
    except Exception:
        return render_template("error.html")


@app.route('/admin_auth', methods=['GET', 'POST'])
def admin_auth():
    login = session.get('user_login')
    if not login: return redirect(url_for('registration'))
    if request.method == 'POST':
        if not validate_csrf_token():
            return render_template('admin_auth.html', error="Ошибка проверки безопасности")
        password = hashing(request.form.get('admin_pass', '')[:256])
        if check_user_data(login, password):
            session['admin_confirmed'] = True
            return redirect(url_for('admin_panel'))
        return render_template('admin_auth.html', error="Неверный пароль администратора")
    return render_template('admin_auth.html')


@app.errorhandler(HTTPException)
def handle_error(error):
    return render_template('error.html'), error.code


def run_flask():
    app.run(port=5000)


if __name__ == "__main__":
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    webview.create_window('SmartMiner', 'http://127.0.0.1:5000')
    webview.start()
