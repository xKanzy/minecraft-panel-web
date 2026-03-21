import os
import sys
import json
import logging
import psutil
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from config_manager import config
from server_manager import MinecraftServerManager
from backup_manager import BackupManager
from plugin_manager import PluginManager
from stats_collector import stats_collector
from translations import gettext

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
logging.basicConfig(level=logging.INFO)

# Инициализация менеджеров
server_manager = MinecraftServerManager()
backup_manager = BackupManager()
plugin_manager = PluginManager()

# Контекстный процессор для переводов
@app.context_processor
def inject_globals():
    lang = session.get('lang', 'en')
    def _gettext(text):
        return gettext(text, lang)
    return {'_': _gettext}

def require_config(f):
    def wrapper(*args, **kwargs):
        if not config.is_configured():
            return redirect(url_for('setup'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# ------------------- Страницы интерфейса -------------------
@app.route('/')
@require_config
def index():
    return render_template('index.html', status=server_manager.is_running())

@app.route('/console')
@require_config
def console():
    return render_template('console.html')

@app.route('/players')
@require_config
def players():
    return render_template('players.html')

@app.route('/plugins')
@require_config
def plugins():
    return render_template('plugins.html')

@app.route('/modrinth')
@require_config
def modrinth():
    return render_template('modrinth.html')

@app.route('/backups')
@require_config
def backups():
    return render_template('backups.html')

@app.route('/stats')
@require_config
def stats():
    return render_template('stats.html')

@app.route('/settings')
@require_config
def settings():
    return render_template('settings.html', config=config.data)

# ------------------- API -------------------
@app.route('/api/status')
@require_config
def api_status():
    return jsonify({'running': server_manager.is_running()})

@app.route('/api/system_stats')
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
@require_config
def api_start():
    result = server_manager.start()
    return jsonify({'message': result})

@app.route('/api/stop', methods=['POST'])
@require_config
def api_stop():
    result = server_manager.stop()
    return jsonify({'message': result})

@app.route('/api/reset_status', methods=['POST'])
@require_config
def api_reset_status():
    result = server_manager.force_reset()
    return jsonify({'message': result})

@app.route('/api/command', methods=['POST'])
@require_config
def api_command():
    cmd = request.json.get('command')
    if cmd:
        server_manager.send_command(cmd)
        return jsonify({'status': 'sent'})
    return jsonify({'error': 'No command'}), 400

@app.route('/api/logs')
@require_config
def api_logs():
    lines = request.args.get('lines', default=50, type=int)
    logs = server_manager.get_logs(lines)
    return jsonify({'logs': logs})

@app.route('/api/logs/updates')
@require_config
def api_logs_updates():
    last_size = request.args.get('size', default=0, type=int)
    new_lines, new_size = server_manager.get_logs_since(last_size)
    return jsonify({'lines': new_lines, 'size': new_size})

@app.route('/api/players')
@require_config
def api_players():
    players = server_manager.get_players()
    return jsonify({'players': players})

@app.route('/api/plugins')
@require_config
def api_plugins_list():
    plugins = plugin_manager.list_plugins()
    return jsonify({'plugins': plugins})

@app.route('/api/plugins/upload', methods=['POST'])
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
@require_config
def api_plugins_delete(plugin_name):
    plugin_manager.delete_plugin(plugin_name)
    # Удаляем запись из modrinth_installed.json, если есть
    try:
        from app import remove_modrinth_installed_by_filename
        remove_modrinth_installed_by_filename(plugin_name)
    except:
        pass
    return jsonify({'status': 'deleted'})

# --- Modrinth API ---
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

@app.route('/api/modrinth/search')
@require_config
def api_modrinth_search():
    query = request.args.get('q', '').strip()
    version = request.args.get('version', '').strip()
    if not query:
        return jsonify({'error': 'No query'}), 400

    def search_modrinth(facets):
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

    base_facets = [["project_type:plugin"]]
    try:
        if version:
            facets_with_version = [["project_type:plugin"], [f"versions:{version}"]]
            results = search_modrinth(facets_with_version)
            if not results:
                results = search_modrinth(base_facets)
        else:
            results = search_modrinth(base_facets)
    except Exception as e:
        return jsonify({'error': f'Search failed: {str(e)}'}), 500

    simplified = []
    for item in results:
        simplified.append({
            'id': item['project_id'],
            'slug': item['slug'],
            'title': item['title'],
            'description': item['description'],
            'downloads': item['downloads'],
            'icon_url': item.get('icon_url', ''),
            'versions': item.get('versions', [])[:3]
        })
    return jsonify({'results': simplified})

@app.route('/api/modrinth/download/<project_id>', methods=['POST'])
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

@app.route('/api/modrinth/installed')
@require_config
def api_modrinth_installed():
    mapping = load_modrinth_installed()
    return jsonify({'installed': list(mapping.keys())})

# --- Backups ---
@app.route('/api/backups')
@require_config
def api_backups_list():
    backups = backup_manager.list_backups()
    return jsonify({'backups': backups})

@app.route('/api/backups/create', methods=['POST'])
@require_config
def api_backups_create():
    result = backup_manager.create_backup()
    return jsonify({'message': result})

@app.route('/api/backups/restore/<backup_name>', methods=['POST'])
@require_config
def api_backups_restore(backup_name):
    result = backup_manager.restore_backup(backup_name)
    return jsonify({'message': result})

@app.route('/api/backups/delete/<backup_name>', methods=['DELETE'])
@require_config
def api_backups_delete(backup_name):
    backup_manager.delete_backup(backup_name)
    return jsonify({'status': 'deleted'})

@app.route('/api/stats')
@require_config
def api_stats():
    stats = stats_collector.get_stats()
    return jsonify(stats)

# ------------------- Настройка (setup) -------------------
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

        # Создаём необходимые папки
        backup_dir = config.get('BACKUP_DIR')
        plugins_dir = config.get('PLUGINS_DIR')
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
        if plugins_dir:
            os.makedirs(plugins_dir, exist_ok=True)

        return redirect(url_for('index'))
    return render_template('setup.html')

@app.route('/api/settings', methods=['POST'])
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
    return jsonify({'status': 'updated'})

@app.route('/set_language/<lang>')
def set_language(lang):
    if lang in ['en', 'ru']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))

# ------------------- Запуск -------------------
import socket

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]

if __name__ == '__main__':
    port = int(os.environ.get('PORT', find_free_port()))
    app.run(debug=False, host='0.0.0.0', port=port)
