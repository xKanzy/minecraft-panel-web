import json
import os
import sys

def get_config_path():
    """Возвращает путь к config.json в зависимости от ОС и способа запуска"""
    if getattr(sys, 'frozen', False):
        if sys.platform == 'win32':
            base = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'MinecraftPanel')
        else:
            base = os.path.join(os.path.expanduser('~'), '.config', 'minecraft_panel')
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, 'config.json')
    else:
        return os.path.join(os.path.abspath('.'), 'config.json')

CONFIG_FILE = get_config_path()

DEFAULT_CONFIG = {
    "SERVER_DIR": "",
    "SERVER_JAR": "server.jar",
    "JAVA_CMD": "java",
    "JAVA_ARGS": ["-Xmx1024M", "-Xms1024M", "-jar", "server.jar", "nogui"],
    "LOG_FILE": "",
    "PID_FILE": "",
    "BACKUP_DIR": "",
    "PLUGINS_DIR": "",
    "STATS_FILE": "",
    "STATS_INTERVAL": 10,
    "MAX_BACKUPS": 10,
    "CURSEFORGE_API_KEY": "",
    "ADMIN_PASSWORD_HASH": ""
}

class Config:
    def __init__(self):
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except:
                self.data = DEFAULT_CONFIG.copy()
        else:
            self.data = DEFAULT_CONFIG.copy()

        for key, value in DEFAULT_CONFIG.items():
            if key not in self.data:
                self.data[key] = value

        self.update_derived_paths()
        self.save()

    def save(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Could not save config: {e}")

    def update_derived_paths(self):
        if self.data["SERVER_DIR"] and os.path.isdir(self.data["SERVER_DIR"]):
            self.data["LOG_FILE"] = os.path.join(self.data["SERVER_DIR"], "logs", "latest.log")
            self.data["PID_FILE"] = os.path.join(self.data["SERVER_DIR"], "server.pid")
            self.data["BACKUP_DIR"] = os.path.join(self.data["SERVER_DIR"], "backups")
            self.data["PLUGINS_DIR"] = os.path.join(self.data["SERVER_DIR"], "plugins")
            self.data["STATS_FILE"] = os.path.join(self.data["SERVER_DIR"], "stats.json")
        else:
            self.data["LOG_FILE"] = ""
            self.data["PID_FILE"] = ""
            self.data["BACKUP_DIR"] = ""
            self.data["PLUGINS_DIR"] = ""
            self.data["STATS_FILE"] = ""

    def get(self, key):
        return self.data.get(key, DEFAULT_CONFIG.get(key))

    def set(self, key, value):
        self.data[key] = value
        if key == "SERVER_DIR":
            self.update_derived_paths()
        self.save()

    def is_configured(self):
        return bool(self.data.get("SERVER_DIR")) and os.path.isdir(self.data["SERVER_DIR"])

# Создаём глобальный экземпляр для удобного импорта
config = Config()