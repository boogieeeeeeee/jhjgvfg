from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)
app.secret_key = 'slaptas_zebra_secure_session_key'

TIMEZONE = pytz.timezone('America/New_York')
SITE_PASSWORD = "SilentWhisperEchoes!"
REDO_CODE = "29472942398433892"
OWNER_BYPASS_CODE = "493724"

ACTIVE_USERS = {}


def get_site_status():
    now = datetime.now(TIMEZONE)
    day = now.weekday()
    current_time_str = now.strftime("%H:%M")

    if day >= 5:
        return "shutdown", current_time_str

    current_minutes = now.hour * 60 + now.minute
    open_minutes = 6 * 60 + 50
    close_minutes = 14 * 60 + 30

    warn1_minutes = 13 * 60 + 30
    warn2_minutes = 14 * 60 + 10

    if current_minutes < open_minutes or current_minutes >= close_minutes:
        return "shutdown", current_time_str

    if current_minutes >= warn2_minutes:
        return "warning_two", current_time_str
    elif current_minutes >= warn1_minutes:
        return "warning_one", current_time_str

    return "open", current_time_str


@app.before_request
def check_time_and_lockout():
    if request.path.startswith('/static') or request.path in [url_for('system_status'), url_for('owner_login'),
                                                              url_for('live_players'), url_for('heartbeat')]:
        return

    if session.get('owner_override'):
        return

    status, _ = get_site_status()

    if status == "shutdown":
        if request.path != url_for('shutdown'):
            return redirect(url_for('shutdown'))
        return

    if session.get('permanently_disabled') and request.path not in [url_for('locked_out'), url_for('shutdown')]:
        return redirect(url_for('locked_out'))

    if not session.get('authenticated') and request.path not in [url_for('password_gate'), url_for('locked_out'),
                                                                 url_for('shutdown')]:
        return redirect(url_for('password_gate'))


@app.route('/system-status')
def system_status():
    status, time_str = get_site_status()
    return jsonify({"status": status, "current_time": time_str})


@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent', 'unknown')
    user_id = f"{user_ip}_{user_agent}"

    ACTIVE_USERS[user_id] = datetime.now()
    return jsonify({"status": "acknowledged"})


@app.route('/player-count')
def live_players():
    now = datetime.now()
    cutoff_time = now - timedelta(seconds=12)

    expired_sessions = [uid for uid, last_seen in ACTIVE_USERS.items() if last_seen < cutoff_time]
    for uid in expired_sessions:
        del ACTIVE_USERS[uid]

    return jsonify({"count": len(ACTIVE_USERS)})


@app.route('/owner-bypass', methods=['POST'])
def owner_login():
    entered_code = request.form.get('bypass_code')
    if entered_code == OWNER_BYPASS_CODE:
        session['owner_override'] = True
        session['authenticated'] = True
        return redirect(url_for('homepage'))
    return redirect(url_for('shutdown', error="Invalid Override Code"))


@app.route('/')
def homepage():
    return render_template('homepage.html')


@app.route('/gateway', methods=['GET', 'POST'])
def password_gate():
    if session.get('authenticated'):
        return redirect(url_for('homepage'))

    if 'attempts_left' not in session:
        session['attempts_left'] = 1

    error = None
    if request.method == 'POST':
        entered_password = request.form.get('password')

        if entered_password == SITE_PASSWORD:
            session['authenticated'] = True
            session['attempts_left'] = 1
            return redirect(url_for('homepage'))
        else:
            session['attempts_left'] -= 1
            if session['attempts_left'] <= 0:
                session['permanently_disabled'] = True
                return redirect(url_for('locked_out'))
            else:
                error = f"Incorrect password. Tries remaining: {session['attempts_left']}"

    return render_template('password.html', error=error)


@app.route('/recovery', methods=['GET', 'POST'])
def locked_out():
    if not session.get('permanently_disabled'):
        return redirect(url_for('password_gate'))

    error = None
    if request.method == 'POST':
        entered_code = request.form.get('redo_code')
        if entered_code == REDO_CODE:
            session['permanently_disabled'] = False
            session['attempts_left'] = 3
            return redirect(url_for('password_gate'))
        else:
            error = "Invalid Redo Token."

    return render_template('locked_out.html', error=error)


@app.route('/maintenance')
def shutdown():
    status, _ = get_site_status()
    if status != "shutdown" and not session.get('owner_override'):
        return redirect(url_for('password_gate'))

    error = request.args.get('error')
    return render_template('shutdown.html', error=error)


if __name__ == '__main__':
    import os

    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
