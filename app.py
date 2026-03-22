import os
import sys
import json
import logging
import time
import threading
import datetime
import secrets
import re
import psutil
import requests
import bcrypt
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from config_manager import config, CONFIG_FILE
from server_manager import MinecraftServerManager
from backup_manager import BackupManager
from plugin_manager import PluginManager
from stats_collector import stats_collector
from translations import gettext

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
logging.basicConfig(level=logging.INFO)

# ------------------- Вспомогательная функция перевода для маршрутов -------------------
def _(text):
    lang = session.get('lang', 'en')
    return gettext(text, lang)

# ------------------- Управление пользователями -------------------
USERS_FILE = os.path.join(os.path.dirname(CONFIG_FILE), 'users.json')

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def create_user(username, password, is_admin=False):
    users = load_users()
    if username in users:
        return False
    salt = bcrypt.gensalt()
    pwd_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    users[username] = {'password_hash': pwd_hash, 'is_admin': is_admin}
    save_users(users)
    return True

def verify_user(username, password):
    users = load_users()
    if username not in users:
        return False
    user = users[username]
    return bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8'))

def is_admin(username):
    users = load_users()
    return users.get(username, {}).get('is_admin', False)

def change_password(username, new_password):
    users = load_users()
    if username not in users:
        return False
    salt = bcrypt.gensalt()
    pwd_hash = bcrypt.hashpw(new_password.encode('utf-8'), salt).decode('utf-8')
    users[username]['password_hash'] = pwd_hash
    save_users(users)
    return True

def delete_user(username):
    if username == 'admin':
        return False
    users = load_users()
    if username in users:
        del users[username]
        save_users(users)
        return True
    return False

def set_admin_status(username, is_admin):
    users = load_users()
    if username in users:
        users[username]['is_admin'] = is_admin
        save_users(users)
        return True
    return False

def migrate_admin_from_config():
    users = load_users()
    if users:
        return
    pwd_hash = config.get('ADMIN_PASSWORD_HASH')
    if pwd_hash:
        users['admin'] = {'password_hash': pwd_hash, 'is_admin': True}
        save_users(users)
        config.set('ADMIN_PASSWORD_HASH', '')
        print("Migrated admin password from config to users.json")
    else:
        create_user('admin', 'admin', is_admin=True)
        print("Created default admin user with password 'admin'. Please change it immediately.")

# ------------------- Flask-Login -------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

class User:
    def __init__(self, username, is_admin=False):
        self.username = username
        self.is_admin = is_admin
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    def get_id(self):
        return self.username

@login_manager.user_loader
def load_user(user_id):
    users = load_users()
    if user_id in users:
        return User(user_id, users[user_id].get('is_admin', False))
    return None

# ------------------- Декоратор администратора -------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ------------------- Менеджеры -------------------
server_manager = MinecraftServerManager()
backup_manager = BackupManager()
plugin_manager = PluginManager()

def require_config(f):
    def wrapper(*args, **kwargs):
        if not config.is_configured():
            return redirect(url_for('setup'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# ------------------- Контекстный процессор для шаблонов -------------------
@app.context_processor
def inject_globals():
    lang = session.get('lang', 'en')
    def _gettext(text):
        return gettext(text, lang)
    return {'_': _gettext}

# ------------------- Страницы интерфейса -------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if verify_user(username, password):
            user = User(username, is_admin(username))
            login_user(user)
            return redirect(request.args.get('next') or url_for('index'))
        else:
            return render_template('login.html', error=_('Invalid credentials')), 401
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm = request.form.get('confirm')
        if not username or not password:
            return render_template('register.html', error=_('Username and password required'))
        if password != confirm:
            return render_template('register.html', error=_('Passwords do not match'))
        if len(password) < 6:
            return render_template('register.html', error=_('Password must be at least 6 characters'))
        if create_user(username, password, is_admin=False):
            user = User(username, is_admin=False)
            login_user(user)
            return redirect(url_for('index'))
        else:
            return render_template('register.html', error=_('Username already exists'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
@require_config
def index():
    return render_template('index.html', status=server_manager.is_running())

@app.route('/console')
@login_required
@require_config
def console():
    return render_template('console.html')

@app.route('/players')
@login_required
@require_config
def players():
    return render_template('players.html', is_admin=current_user.is_admin)

@app.route('/plugins')
@login_required
@require_config
def plugins():
    return render_template('plugins.html')

@app.route('/mods')
@login_required
@require_config
def mods():
    return render_template('mods.html')

@app.route('/admin')
@login_required
@admin_required
@require_config
def admin_tools():
    return render_template('admin_tools.html')

@app.route('/backups')
@login_required
@require_config
def backups():
    return render_template('backups.html')

@app.route('/stats')
@login_required
@require_config
def stats():
    return render_template('stats.html')

@app.route('/settings')
@login_required
@admin_required
@require_config
def settings():
    return render_template('settings.html', config=config.data)

@app.route('/filemanager')
@login_required
@require_config
def filemanager():
    return render_template('filemanager.html')

# ------------------- API для сервера -------------------
@app.route('/api/status')
@login_required
@require_config
def api_status():
    return jsonify({'running': server_manager.is_running()})

@app.route('/api/system_stats')
@login_required
@require_config
def api_system_stats():
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    cpu = psutil.cpu_percent(interval=0.1)
    return jsonify({
        'cpu': cpu,
        'ram_used': mem.used,
        'ram_total': mem.total,
        'ram_percent': mem.percent,
        'disk_used': disk.used,
        'disk_total': disk.total,
        'disk_percent': disk.percent
    })

@app.route('/api/start', methods=['POST'])
@login_required
@require_config
def api_start():
    result = server_manager.start()
    send_discord_notification(f"**Сервер {'запущен' if result == 'Server started.' else 'остановлен'}**\nПользователь: {current_user.username}", color=0x4caf50 if 'started' in result else 0xf44336, title="Server Status")
    return jsonify({'message': result})

@app.route('/api/stop', methods=['POST'])
@login_required
@require_config
def api_stop():
    result = server_manager.stop()
    send_discord_notification(f"**Сервер {'запущен' if result == 'Server started.' else 'остановлен'}**\nПользователь: {current_user.username}", color=0x4caf50 if 'started' in result else 0xf44336, title="Server Status")
    return jsonify({'message': result})

@app.route('/api/reset_status', methods=['POST'])
@login_required
@require_config
def api_reset_status():
    result = server_manager.force_reset()
    return jsonify({'message': result})

# ------------------- История команд -------------------
COMMAND_HISTORY_FILE = os.path.join(os.path.dirname(CONFIG_FILE), 'command_history.json')

def log_command(command):
    try:
        history = []
        if os.path.exists(COMMAND_HISTORY_FILE):
            with open(COMMAND_HISTORY_FILE, 'r') as f:
                history = json.load(f)
        history.append({
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'command': command
        })
        if len(history) > 100:
            history = history[-100:]
        with open(COMMAND_HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except:
        pass

@app.route('/api/command', methods=['POST'])
@login_required
@require_config
def api_command():
    cmd = request.json.get('command')
    if cmd:
        server_manager.send_command(cmd)
        log_command(cmd)
        send_discord_notification(f"**Команда отправлена**\nПользователь: {current_user.username}\nКоманда: `{cmd}`", color=0x2196f3, title="Command Sent")
        return jsonify({'status': 'sent'})
    return jsonify({'error': 'No command'}), 400

@app.route('/api/command_history')
@login_required
@require_config
def api_command_history():
    try:
        if os.path.exists(COMMAND_HISTORY_FILE):
            with open(COMMAND_HISTORY_FILE, 'r') as f:
                history = json.load(f)
            return jsonify({'history': history})
    except:
        pass
    return jsonify({'history': []})

@app.route('/api/logs')
@login_required
@require_config
def api_logs():
    lines = request.args.get('lines', default=50, type=int)
    logs = server_manager.get_logs(lines)
    return jsonify({'logs': logs})

@app.route('/api/logs/updates')
@login_required
@require_config
def api_logs_updates():
    last_size = request.args.get('size', default=0, type=int)
    new_lines, new_size = server_manager.get_logs_since(last_size)
    return jsonify({'lines': new_lines, 'size': new_size})

# ------------------- SSE для логов -------------------
def stream_logs(last_size=0):
    log_file_path = os.path.join(config.get('SERVER_DIR'), "server_stdout.log")
    while not os.path.exists(log_file_path):
        time.sleep(0.5)
        yield f"data: {json.dumps({'lines': ['Waiting for log file...']})}\n\n"
    with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
        f.seek(0, os.SEEK_END)
        current_size = f.tell()
        if last_size > current_size:
            last_size = 0
            f.seek(0)
        elif last_size < current_size:
            f.seek(last_size)
            lines = f.readlines()
            if lines:
                yield f"data: {json.dumps({'lines': lines})}\n\n"
            last_size = f.tell()
        while True:
            time.sleep(0.2)
            f.seek(0, os.SEEK_END)
            new_size = f.tell()
            if new_size > last_size:
                f.seek(last_size)
                lines = f.readlines()
                if lines:
                    yield f"data: {json.dumps({'lines': lines})}\n\n"
                last_size = f.tell()
            elif new_size < last_size:
                last_size = 0
                f.seek(0)

@app.route('/api/logs/stream')
@login_required
@require_config
def api_logs_stream():
    last_size = request.args.get('size', default=0, type=int)
    return Response(stream_logs(last_size), mimetype='text/event-stream')

@app.route('/api/players')
@login_required
@require_config
def api_players():
    try:
        players = server_manager.get_players()
        return jsonify({'players': players})
    except Exception as e:
        app.logger.error(f"Players API error: {e}")
        return jsonify({'players': [], 'error': str(e)}), 500

# ------------------- API для плагинов (Modrinth + CurseForge) -------------------
MODRINTH_INSTALLED_FILE = None

def get_modrinth_installed_file():
    global MODRINTH_INSTALLED_FILE
    if MODRINTH_INSTALLED_FILE is None:
        plugins_dir = config.get('PLUGINS_DIR')
        if plugins_dir:
            MODRINTH_INSTALLED_FILE = os.path.join(plugins_dir, 'modrinth_installed.json')
        else:
            MODRINTH_INSTALLED_FILE = None
    return MODRINTH_INSTALLED_FILE

def load_modrinth_installed():
    file_path = get_modrinth_installed_file()
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_modrinth_installed(mapping):
    file_path = get_modrinth_installed_file()
    if file_path:
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                json.dump(mapping, f, indent=2)
        except:
            pass

def add_modrinth_installed(project_id, filename):
    mapping = load_modrinth_installed()
    mapping[project_id] = filename
    save_modrinth_installed(mapping)

def remove_modrinth_installed_by_filename(filename):
    mapping = load_modrinth_installed()
    for pid, fname in list(mapping.items()):
        if fname == filename:
            del mapping[pid]
            break
    save_modrinth_installed(mapping)

def curseforge_search(query, game_id=432):
    api_key = config.get('CURSEFORGE_API_KEY')
    if not api_key:
        return []
    headers = {'x-api-key': api_key, 'Accept': 'application/json'}
    url = 'https://api.curseforge.com/v1/mods/search'
    params = {
        'gameId': game_id,
        'searchFilter': query,
        'sortField': 1,
        'sortOrder': 'desc',
        'modLoaderType': 4,
        'pageSize': 20,
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get('data', [])
            simplified = []
            for item in results:
                versions = []
                for file in item.get('latestFiles', [])[:3]:
                    if file.get('gameVersion'):
                        versions.extend(file['gameVersion'])
                versions = list(set(versions))[:3]
                simplified.append({
                    'id': str(item['id']),
                    'title': item['name'],
                    'description': item.get('summary', ''),
                    'downloads': item.get('downloadCount', 0),
                    'icon_url': item.get('logo', {}).get('url', ''),
                    'versions': versions,
                    'source': 'curseforge'
                })
            return simplified
        else:
            app.logger.warning(f"CurseForge API returned {resp.status_code}")
            return []
    except Exception as e:
        app.logger.error(f"CurseForge search error: {e}")
        return []

@app.route('/api/modrinth/search')
@login_required
@require_config
def api_modrinth_search():
    query = request.args.get('q', '').strip()
    version = request.args.get('version', '').strip()
    if not query:
        return jsonify({'error': 'No query'}), 400

    def modrinth_search(facets):
        import urllib.parse
        facets_json = json.dumps(facets)
        url = f"https://api.modrinth.com/v2/search?query={urllib.parse.quote(query)}&facets={urllib.parse.quote(facets_json)}&limit=20"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return data.get('hits', [])
        except Exception as e:
            app.logger.error(f"Modrinth search error: {e}")
            raise

    modrinth_results = []
    base_facets = [["project_type:plugin"]]
    try:
        if version:
            facets_with_version = [["project_type:plugin"], [f"versions:{version}"]]
            modrinth_results = modrinth_search(facets_with_version)
            if not modrinth_results:
                modrinth_results = modrinth_search(base_facets)
        else:
            modrinth_results = modrinth_search(base_facets)
    except Exception as e:
        app.logger.warning(f"Modrinth search failed: {e}")

    unified = []
    for item in modrinth_results:
        unified.append({
            'id': item['project_id'],
            'title': item['title'],
            'description': item['description'],
            'downloads': item['downloads'],
            'icon_url': item.get('icon_url', ''),
            'versions': item.get('versions', [])[:3],
            'source': 'modrinth'
        })
    curse_results = curseforge_search(query)
    unified.extend(curse_results)
    unified.sort(key=lambda x: x['downloads'], reverse=True)
    return jsonify({'results': unified})

@app.route('/api/modrinth/download/<project_id>', methods=['POST'])
@login_required
@require_config
def api_modrinth_download(project_id):
    url = f"https://api.modrinth.com/v2/project/{project_id}/version"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        versions = resp.json()
        if not versions:
            return jsonify({'error': 'No versions found'}), 404
        latest = versions[0]
        for file in latest['files']:
            if file['filename'].endswith('.jar'):
                download_url = file['url']
                filename = file['filename']
                file_resp = requests.get(download_url, stream=True)
                file_resp.raise_for_status()
                plugins_dir = config.get('PLUGINS_DIR')
                if plugins_dir:
                    save_path = os.path.join(plugins_dir, filename)
                    with open(save_path, 'wb') as f:
                        for chunk in file_resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    add_modrinth_installed(project_id, filename)
                    return jsonify({'status': 'downloaded', 'filename': filename})
                else:
                    return jsonify({'error': 'Plugins directory not configured'}), 500
        return jsonify({'error': 'No jar file found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/curseforge/download/<mod_id>', methods=['POST'])
@login_required
@require_config
def api_curseforge_download(mod_id):
    api_key = config.get('CURSEFORGE_API_KEY')
    if not api_key:
        return jsonify({'error': 'CurseForge API key not configured'}), 400
    headers = {'x-api-key': api_key}
    url = f'https://api.curseforge.com/v1/mods/{mod_id}/files'
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return jsonify({'error': 'Failed to fetch file list'}), resp.status_code
        data = resp.json()
        files = data.get('data', [])
        if not files:
            return jsonify({'error': 'No files found'}), 404
        latest = files[0]
        file_id = latest['id']
        download_url = f'https://api.curseforge.com/v1/mods/{mod_id}/files/{file_id}/download-url'
        resp2 = requests.get(download_url, headers=headers, timeout=10)
        if resp2.status_code != 200:
            return jsonify({'error': 'Failed to get download URL'}), resp2.status_code
        download_info = resp2.json()
        url_to_file = download_info.get('data')
        if not url_to_file:
            return jsonify({'error': 'No download URL'}), 404
        file_resp = requests.get(url_to_file, stream=True)
        file_resp.raise_for_status()
        filename = latest['fileName']
        plugins_dir = config.get('PLUGINS_DIR')
        if not plugins_dir:
            return jsonify({'error': 'Plugins directory not configured'}), 500
        save_path = os.path.join(plugins_dir, filename)
        with open(save_path, 'wb') as f:
            for chunk in file_resp.iter_content(chunk_size=8192):
                f.write(chunk)
        add_modrinth_installed(f'cf_{mod_id}', filename)
        return jsonify({'status': 'downloaded', 'filename': filename})
    except Exception as e:
        app.logger.error(f"CurseForge download error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/modrinth/installed')
@login_required
@require_config
def api_modrinth_installed():
    mapping = load_modrinth_installed()
    return jsonify({'installed': list(mapping.keys())})

# ------------------- API для плагинов (локальные) -------------------
@app.route('/api/plugins')
@login_required
@require_config
def api_plugins_list():
    plugins = plugin_manager.list_plugins()
    return jsonify({'plugins': plugins})

@app.route('/api/plugins/upload', methods=['POST'])
@login_required
@require_config
def api_plugins_upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400
    if file.filename.endswith('.jar'):
        plugin_manager.upload_plugin(file)
        return jsonify({'status': 'uploaded'})
    return jsonify({'error': 'Not a jar file'}), 400

@app.route('/api/plugins/delete/<plugin_name>', methods=['DELETE'])
@login_required
@require_config
def api_plugins_delete(plugin_name):
    plugin_manager.delete_plugin(plugin_name)
    remove_modrinth_installed_by_filename(plugin_name)
    return jsonify({'status': 'deleted'})

# ------------------- API для модов -------------------
def get_mods_dir():
    server_dir = config.get('SERVER_DIR')
    if server_dir:
        return os.path.join(server_dir, 'mods')
    return None

@app.route('/api/mods')
@login_required
@require_config
def api_mods_list():
    mods_dir = get_mods_dir()
    if not mods_dir:
        return jsonify({'error': 'Server directory not configured'}), 400
    os.makedirs(mods_dir, exist_ok=True)
    mods = []
    for filename in os.listdir(mods_dir):
        if filename.endswith('.jar'):
            filepath = os.path.join(mods_dir, filename)
            stat = os.stat(filepath)
            mods.append({
                'name': filename,
                'size': stat.st_size,
                'modified': stat.st_mtime
            })
    mods.sort(key=lambda x: x['name'])
    return jsonify({'mods': mods})

@app.route('/api/mods/upload', methods=['POST'])
@login_required
@require_config
def api_mods_upload():
    mods_dir = get_mods_dir()
    if not mods_dir:
        return jsonify({'error': 'Server directory not configured'}), 400
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400
    if not file.filename.endswith('.jar'):
        return jsonify({'error': 'Not a jar file'}), 400
    os.makedirs(mods_dir, exist_ok=True)
    filename = secure_filename(file.filename)
    filepath = os.path.join(mods_dir, filename)
    file.save(filepath)
    return jsonify({'status': 'uploaded'})

@app.route('/api/mods/delete/<mod_name>', methods=['DELETE'])
@login_required
@require_config
def api_mods_delete(mod_name):
    mods_dir = get_mods_dir()
    if not mods_dir:
        return jsonify({'error': 'Server directory not configured'}), 400
    if not mod_name.endswith('.jar'):
        return jsonify({'error': 'Invalid mod name'}), 400
    filepath = os.path.join(mods_dir, mod_name)
    if os.path.exists(filepath):
        os.remove(filepath)
        return jsonify({'status': 'deleted'})
    return jsonify({'error': 'File not found'}), 404

# ------------------- API для поиска модов (Modrinth + CurseForge) -------------------
@app.route('/api/mods/search')
@login_required
@require_config
def api_mods_search():
    query = request.args.get('q', '').strip()
    version = request.args.get('version', '').strip()
    if not query:
        return jsonify({'error': 'No query'}), 400

    def modrinth_search_mods(facets):
        import urllib.parse
        facets_json = json.dumps(facets)
        url = f"https://api.modrinth.com/v2/search?query={urllib.parse.quote(query)}&facets={urllib.parse.quote(facets_json)}&limit=20"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return data.get('hits', [])
        except Exception as e:
            app.logger.error(f"Modrinth mod search error: {e}")
            raise

    modrinth_results = []
    base_facets = [["project_type:mod"]]
    try:
        if version:
            facets_with_version = [["project_type:mod"], [f"versions:{version}"]]
            modrinth_results = modrinth_search_mods(facets_with_version)
            if not modrinth_results:
                modrinth_results = modrinth_search_mods(base_facets)
        else:
            modrinth_results = modrinth_search_mods(base_facets)
    except Exception as e:
        app.logger.warning(f"Modrinth mod search failed: {e}")

    unified = []
    for item in modrinth_results:
        unified.append({
            'id': item['project_id'],
            'title': item['title'],
            'description': item['description'],
            'downloads': item['downloads'],
            'icon_url': item.get('icon_url', ''),
            'versions': item.get('versions', [])[:3],
            'source': 'modrinth'
        })

    def curseforge_search_mods(query, game_id=432):
        api_key = config.get('CURSEFORGE_API_KEY')
        if not api_key:
            return []
        headers = {'x-api-key': api_key, 'Accept': 'application/json'}
        url = 'https://api.curseforge.com/v1/mods/search'
        params = {
            'gameId': game_id,
            'searchFilter': query,
            'sortField': 1,
            'sortOrder': 'desc',
            'pageSize': 20,
        }
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get('data', [])
                simplified = []
                for item in results:
                    versions = []
                    for file in item.get('latestFiles', [])[:3]:
                        if file.get('gameVersion'):
                            versions.extend(file['gameVersion'])
                    versions = list(set(versions))[:3]
                    simplified.append({
                        'id': str(item['id']),
                        'title': item['name'],
                        'description': item.get('summary', ''),
                        'downloads': item.get('downloadCount', 0),
                        'icon_url': item.get('logo', {}).get('url', ''),
                        'versions': versions,
                        'source': 'curseforge'
                    })
                return simplified
            else:
                app.logger.warning(f"CurseForge mod API returned {resp.status_code}")
                return []
        except Exception as e:
            app.logger.error(f"CurseForge mod search error: {e}")
            return []

    curse_results = curseforge_search_mods(query)
    unified.extend(curse_results)
    unified.sort(key=lambda x: x['downloads'], reverse=True)
    return jsonify({'results': unified})

@app.route('/api/mods/download/modrinth/<project_id>', methods=['POST'])
@login_required
@require_config
def api_mods_download_modrinth(project_id):
    url = f"https://api.modrinth.com/v2/project/{project_id}/version"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        versions = resp.json()
        if not versions:
            return jsonify({'error': 'No versions found'}), 404
        latest = versions[0]
        for file in latest['files']:
            if file['filename'].endswith('.jar'):
                download_url = file['url']
                filename = file['filename']
                file_resp = requests.get(download_url, stream=True)
                file_resp.raise_for_status()
                mods_dir = get_mods_dir()
                if mods_dir:
                    save_path = os.path.join(mods_dir, filename)
                    with open(save_path, 'wb') as f:
                        for chunk in file_resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    return jsonify({'status': 'downloaded', 'filename': filename})
                else:
                    return jsonify({'error': 'Mods directory not configured'}), 500
        return jsonify({'error': 'No jar file found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/mods/download/curseforge/<mod_id>', methods=['POST'])
@login_required
@require_config
def api_mods_download_curseforge(mod_id):
    api_key = config.get('CURSEFORGE_API_KEY')
    if not api_key:
        return jsonify({'error': 'CurseForge API key not configured'}), 400
    headers = {'x-api-key': api_key}
    url = f'https://api.curseforge.com/v1/mods/{mod_id}/files'
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return jsonify({'error': 'Failed to fetch file list'}), resp.status_code
        data = resp.json()
        files = data.get('data', [])
        if not files:
            return jsonify({'error': 'No files found'}), 404
        latest = files[0]
        file_id = latest['id']
        download_url = f'https://api.curseforge.com/v1/mods/{mod_id}/files/{file_id}/download-url'
        resp2 = requests.get(download_url, headers=headers, timeout=10)
        if resp2.status_code != 200:
            return jsonify({'error': 'Failed to get download URL'}), resp2.status_code
        download_info = resp2.json()
        url_to_file = download_info.get('data')
        if not url_to_file:
            return jsonify({'error': 'No download URL'}), 404
        file_resp = requests.get(url_to_file, stream=True)
        file_resp.raise_for_status()
        filename = latest['fileName']
        mods_dir = get_mods_dir()
        if not mods_dir:
            return jsonify({'error': 'Mods directory not configured'}), 500
        save_path = os.path.join(mods_dir, filename)
        with open(save_path, 'wb') as f:
            for chunk in file_resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return jsonify({'status': 'downloaded', 'filename': filename})
    except Exception as e:
        app.logger.error(f"CurseForge mod download error: {e}")
        return jsonify({'error': str(e)}), 500

# ------------------- API для управления пользователями -------------------
@app.route('/api/users')
@login_required
@admin_required
@require_config
def api_users():
    users = load_users()
    user_list = [{'username': u, 'is_admin': info['is_admin']} for u, info in users.items()]
    user_list.sort(key=lambda x: x['username'])
    return jsonify({'users': user_list})

@app.route('/api/users/create', methods=['POST'])
@login_required
@admin_required
@require_config
def api_users_create():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'error': 'Missing username or password'}), 400
    if create_user(username, password, is_admin=False):
        return jsonify({'status': 'ok'})
    else:
        return jsonify({'error': 'Username already exists'}), 400

@app.route('/api/users/promote', methods=['POST'])
@login_required
@admin_required
@require_config
def api_users_promote():
    data = request.json
    username = data.get('username')
    if not username:
        return jsonify({'error': 'Missing username'}), 400
    set_admin_status(username, True)
    return jsonify({'status': 'ok'})

@app.route('/api/users/delete', methods=['POST'])
@login_required
@admin_required
@require_config
def api_users_delete():
    data = request.json
    username = data.get('username')
    if not username:
        return jsonify({'error': 'Missing username'}), 400
    if username == 'admin':
        return jsonify({'error': 'Cannot delete admin'}), 400
    if delete_user(username):
        return jsonify({'status': 'ok'})
    else:
        return jsonify({'error': 'User not found'}), 404

@app.route('/api/change_password', methods=['POST'])
@login_required
@require_config
def api_change_password():
    data = request.json
    old = data.get('old_password')
    new = data.get('new_password')
    if not old or not new:
        return jsonify({'error': 'Missing passwords'}), 400
    if not verify_user(current_user.username, old):
        return jsonify({'error': 'Current password is incorrect'}), 401
    if len(new) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    change_password(current_user.username, new)
    return jsonify({'status': 'ok'})

# ------------------- API для бэкапов -------------------
@app.route('/api/backups')
@login_required
@require_config
def api_backups_list():
    backups = backup_manager.list_backups()
    return jsonify({'backups': backups})

@app.route('/api/backups/create', methods=['POST'])
@login_required
@require_config
def api_backups_create():
    result = backup_manager.create_backup()
    return jsonify({'message': result})

@app.route('/api/backups/restore/<backup_name>', methods=['POST'])
@login_required
@require_config
def api_backups_restore(backup_name):
    result = backup_manager.restore_backup(backup_name)
    return jsonify({'message': result})

@app.route('/api/backups/delete/<backup_name>', methods=['DELETE'])
@login_required
@require_config
def api_backups_delete(backup_name):
    backup_manager.delete_backup(backup_name)
    return jsonify({'status': 'deleted'})

@app.route('/api/stats')
@login_required
@require_config
def api_stats():
    stats = stats_collector.get_stats()
    return jsonify(stats)

# ------------------- API для файлового менеджера -------------------
@app.route('/api/filemanager/list')
@login_required
@require_config
def api_filemanager_list():
    base_dir = config.get('SERVER_DIR')
    if not base_dir:
        return jsonify({'error': 'Server directory not configured'}), 400
    if not os.path.isdir(base_dir):
        return jsonify({'error': f'Server directory does not exist: {base_dir}'}), 400

    path = request.args.get('path', '')
    if not path:
        path = base_dir

    real_base = os.path.realpath(base_dir)
    try:
        rel_path = os.path.relpath(path, real_base) if path != real_base else '.'
        real_path = os.path.realpath(os.path.join(real_base, rel_path))
    except ValueError:
        return jsonify({'error': 'Invalid path'}), 400

    if not real_path.startswith(real_base):
        return jsonify({'error': 'Access denied'}), 403
    if not os.path.exists(real_path):
        return jsonify({'error': 'Path does not exist'}), 404

    try:
        items = []
        for entry in os.scandir(real_path):
            items.append({
                'name': entry.name,
                'path': os.path.join(real_path, entry.name),
                'is_dir': entry.is_dir(),
                'size': entry.stat().st_size if not entry.is_dir() else 0,
                'modified': entry.stat().st_mtime
            })
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return jsonify({'path': real_path, 'items': items})
    except PermissionError as e:
        return jsonify({'error': f'Permission denied: {e}'}), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/filemanager/file')
@login_required
@require_config
def api_filemanager_file():
    base_dir = config.get('SERVER_DIR')
    if not base_dir:
        return jsonify({'error': 'Server directory not configured'}), 400
    path = request.args.get('path')
    if not path:
        return jsonify({'error': 'No path specified'}), 400
    real_base = os.path.realpath(base_dir)
    real_path = os.path.realpath(path)
    if not real_path.startswith(real_base):
        return jsonify({'error': 'Access denied'}), 403
    if not os.path.isfile(real_path):
        return jsonify({'error': 'Not a file'}), 400
    size = os.path.getsize(real_path)
    if size > 1024 * 1024:
        return jsonify({'error': 'File too large to edit (max 1 MB)'}), 400
    try:
        with open(real_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'content': content})
    except UnicodeDecodeError:
        return jsonify({'error': 'Cannot edit binary file'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/filemanager/save', methods=['POST'])
@login_required
@require_config
def api_filemanager_save():
    data = request.get_json()
    path = data.get('path')
    content = data.get('content')
    if not path or content is None:
        return jsonify({'error': 'Missing path or content'}), 400
    base_dir = config.get('SERVER_DIR')
    if not base_dir:
        return jsonify({'error': 'Server directory not configured'}), 400
    real_base = os.path.realpath(base_dir)
    real_path = os.path.realpath(path)
    if not real_path.startswith(real_base):
        return jsonify({'error': 'Access denied'}), 403
    try:
        with open(real_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/filemanager/delete', methods=['POST'])
@login_required
@require_config
def api_filemanager_delete():
    data = request.get_json()
    path = data.get('path')
    is_dir = data.get('is_dir', False)
    if not path:
        return jsonify({'error': 'No path specified'}), 400
    base_dir = config.get('SERVER_DIR')
    if not base_dir:
        return jsonify({'error': 'Server directory not configured'}), 400
    real_base = os.path.realpath(base_dir)
    real_path = os.path.realpath(path)
    if not real_path.startswith(real_base):
        return jsonify({'error': 'Access denied'}), 403
    try:
        if is_dir:
            import shutil
            shutil.rmtree(real_path)
        else:
            os.remove(real_path)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/filemanager/create', methods=['POST'])
@login_required
@require_config
def api_filemanager_create():
    data = request.get_json()
    parent = data.get('path')
    name = data.get('name')
    is_dir = data.get('is_dir', False)
    if not parent or not name:
        return jsonify({'error': 'Missing parent path or name'}), 400
    base_dir = config.get('SERVER_DIR')
    if not base_dir:
        return jsonify({'error': 'Server directory not configured'}), 400
    real_base = os.path.realpath(base_dir)
    real_parent = os.path.realpath(parent)
    if not real_parent.startswith(real_base):
        return jsonify({'error': 'Access denied'}), 403
    new_path = os.path.join(real_parent, name)
    try:
        if is_dir:
            os.makedirs(new_path, exist_ok=False)
        else:
            with open(new_path, 'w') as f:
                pass
        return jsonify({'status': 'ok'})
    except FileExistsError:
        return jsonify({'error': 'File or directory already exists'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/filemanager/upload', methods=['POST'])
@login_required
@require_config
def api_filemanager_upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    target_dir = request.form.get('path')
    if not target_dir:
        return jsonify({'error': 'No target directory'}), 400
    base_dir = config.get('SERVER_DIR')
    if not base_dir:
        return jsonify({'error': 'Server directory not configured'}), 400
    real_base = os.path.realpath(base_dir)
    real_target = os.path.realpath(target_dir)
    if not real_target.startswith(real_base):
        return jsonify({'error': 'Access denied'}), 403
    try:
        filename = os.path.basename(file.filename)
        save_path = os.path.join(real_target, filename)
        file.save(save_path)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ------------------- Discord интеграция -------------------
def send_discord_notification(message, color=0x4caf50, title=None):
    webhook_url = config.get('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        return

    def _send():
        try:
            payload = {
                "embeds": [{
                    "title": title or "Minecraft Panel",
                    "description": message,
                    "color": color,
                    "timestamp": datetime.datetime.utcnow().isoformat()
                }]
            }
            requests.post(webhook_url, json=payload, timeout=5)
        except Exception as e:
            app.logger.error(f"Discord notification failed: {e}")

    threading.Thread(target=_send, daemon=True).start()

def send_discord_status():
    webhook_url = config.get('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        return

    is_running = server_manager.is_running()
    players = server_manager.get_players() if is_running else []
    player_count = len(players)
    players_list = ', '.join(players) if players else 'нет'

    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.1)

    status_emoji = "🟢" if is_running else "🔴"
    status_text = "Запущен" if is_running else "Остановлен"

    embed = {
        "title": f"{status_emoji} Статус сервера",
        "color": 0x4caf50 if is_running else 0xf44336,
        "fields": [
            {"name": "Статус", "value": status_text, "inline": True},
            {"name": "Игроки онлайн", "value": f"{player_count} / {config.get('MAX_PLAYERS', 20)}", "inline": True},
            {"name": "Список игроков", "value": players_list if players else "—", "inline": False},
            {"name": "CPU", "value": f"{cpu}%", "inline": True},
            {"name": "RAM", "value": f"{mem.percent}% ({mem.used // (1024**3)} GB / {mem.total // (1024**3)} GB)", "inline": True},
        ],
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

    try:
        requests.post(webhook_url, json={"embeds": [embed]}, timeout=5)
    except Exception as e:
        app.logger.error(f"Discord status send failed: {e}")

def discord_status_loop():
    while True:
        interval = config.get('DISCORD_STATUS_INTERVAL')
        if interval > 0:
            send_discord_status()
        time.sleep(interval * 60 if interval > 0 else 60)

def discord_log_monitor():
    last_size = 0
    last_notify = {}
    COOLDOWN = 5
    while True:
        server_dir = config.get('SERVER_DIR')
        webhook_url = config.get('DISCORD_WEBHOOK_URL')
        if not webhook_url or not server_dir:
            time.sleep(10)
            continue

        notify_join_leave = config.get('DISCORD_NOTIFY_JOIN_LEAVE')
        if not notify_join_leave:
            time.sleep(30)
            continue

        if not server_manager.is_running():
            time.sleep(5)
            continue

        log_file_path = os.path.join(server_dir, "server_stdout.log")
        if not os.path.exists(log_file_path):
            time.sleep(5)
            continue

        join_pattern = re.compile(r'(?:logged in|joined the game)')
        leave_pattern = re.compile(r'(?:left the game|disconnected|lost connection)')
        name_pattern = re.compile(r'\s([\w_]+)(?:\[|\s+joined|\s+left|\s+disconnected|\s+lost)')

        try:
            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(0, os.SEEK_END)
                current_size = f.tell()
                if current_size < last_size:
                    last_size = 0
                    f.seek(0)
                elif current_size == last_size:
                    time.sleep(1)
                    continue
                else:
                    f.seek(last_size)

                lines = f.readlines()
                last_size = f.tell()

                for line in lines:
                    line = re.sub(r'§[0-9a-fklmnor]', '', line)
                    if join_pattern.search(line):
                        match = name_pattern.search(line)
                        if match:
                            player = match.group(1)
                            send_discord_notification(f"**Игрок вошёл на сервер**\n{player}", color=0x4caf50, title="Player Join")
                    elif leave_pattern.search(line):
                        match = name_pattern.search(line)
                        if match:
                            player = match.group(1)
                            now = time.time()
                            if player not in last_notify or now - last_notify[player] > COOLDOWN:
                                send_discord_notification(f"**Игрок покинул сервер**\n{player}", color=0xf44336, title="Player Leave")
                                last_notify[player] = now
        except Exception as e:
            app.logger.error(f"Discord monitor error: {e}")
        time.sleep(1)

@app.route('/api/discord/send_status', methods=['POST'])
@login_required
@admin_required
@require_config
def api_discord_send_status():
    send_discord_status()
    return jsonify({'message': 'Status sent to Discord'})

# ------------------- Настройка -------------------
@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if request.method == 'POST':
        server_dir = request.form.get('server_dir')
        server_jar = request.form.get('server_jar')
        java_cmd = request.form.get('java_cmd')
        java_args_str = request.form.get('java_args')
        max_backups = request.form.get('max_backups', 10, type=int)

        if not os.path.isdir(server_dir):
            lang = session.get('lang', 'en')
            error_msg = gettext('Server directory does not exist.', lang)
            return render_template('setup.html', error=error_msg)

        config.set('SERVER_DIR', server_dir)
        config.set('SERVER_JAR', server_jar)
        config.set('JAVA_CMD', java_cmd)
        java_args = java_args_str.split() if java_args_str else []
        config.set('JAVA_ARGS', java_args)
        config.set('MAX_BACKUPS', max_backups)

        backup_dir = config.get('BACKUP_DIR')
        plugins_dir = config.get('PLUGINS_DIR')
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
        if plugins_dir:
            os.makedirs(plugins_dir, exist_ok=True)

        return redirect(url_for('index'))
    return render_template('setup.html')

@app.route('/api/settings', methods=['POST'])
@login_required
@admin_required
@require_config
def api_settings():
    data = request.json
    if 'SERVER_DIR' in data:
        config.set('SERVER_DIR', data['SERVER_DIR'])
    if 'SERVER_JAR' in data:
        config.set('SERVER_JAR', data['SERVER_JAR'])
    if 'JAVA_CMD' in data:
        config.set('JAVA_CMD', data['JAVA_CMD'])
    if 'JAVA_ARGS' in data:
        if isinstance(data['JAVA_ARGS'], list):
            config.set('JAVA_ARGS', data['JAVA_ARGS'])
        else:
            config.set('JAVA_ARGS', data['JAVA_ARGS'].split())
    if 'MAX_BACKUPS' in data:
        config.set('MAX_BACKUPS', int(data['MAX_BACKUPS']))
    if 'CURSEFORGE_API_KEY' in data:
        config.set('CURSEFORGE_API_KEY', data['CURSEFORGE_API_KEY'])
    if 'DISCORD_WEBHOOK_URL' in data:
        config.set('DISCORD_WEBHOOK_URL', data['DISCORD_WEBHOOK_URL'])
    if 'DISCORD_STATUS_INTERVAL' in data:
        config.set('DISCORD_STATUS_INTERVAL', int(data['DISCORD_STATUS_INTERVAL']))
    if 'DISCORD_NOTIFY_JOIN_LEAVE' in data:
        config.set('DISCORD_NOTIFY_JOIN_LEAVE', data['DISCORD_NOTIFY_JOIN_LEAVE'])
    return jsonify({'status': 'updated'})

@app.route('/set_language/<lang>')
def set_language(lang):
    if lang in ['en', 'ru']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('login'))

# ------------------- Запуск -------------------
if __name__ == '__main__':
    migrate_admin_from_config()
    threading.Thread(target=discord_status_loop, daemon=True).start()
    threading.Thread(target=discord_log_monitor, daemon=True).start()
    port = int(os.environ.get('PORT', 8081))
    app.run(debug=False, host='0.0.0.0', port=port)