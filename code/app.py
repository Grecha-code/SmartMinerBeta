from flask import Flask, render_template, redirect, url_for
from werkzeug.exceptions import HTTPException


app = Flask(__name__)


@app.route('/')
def reg():
    try:
        with open('user_data.json', 'r') as file:
            content = file.read()
            return redirect(url_for('safety'))
    except FileNotFoundError:
        return render_template('registration.html')


@app.route('/safety')
def safety():
    return render_template('safety.html')


@app.errorhandler(HTTPException)
def handle_error(error):
    return render_template('error.html'), error.code


if  __name__ == "__main__":
    app.run(debug=True)

