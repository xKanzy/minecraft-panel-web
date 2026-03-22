import os
from werkzeug.utils import secure_filename
from config_manager import config

class PluginManager:
    def __init__(self):
        self.plugins_dir = config.get('PLUGINS_DIR')
        if self.plugins_dir:
            os.makedirs(self.plugins_dir, exist_ok=True)

    def list_plugins(self):
        if not self.plugins_dir or not os.path.exists(self.plugins_dir):
            return []
        plugins = []
        try:
            for filename in os.listdir(self.plugins_dir):
                if filename.endswith('.jar'):
                    filepath = os.path.join(self.plugins_dir, filename)
                    stat = os.stat(filepath)
                    plugins.append({
                        'name': filename,
                        'size': stat.st_size,
                        'modified': stat.st_mtime
                    })
        except:
            pass
        return plugins

    def upload_plugin(self, file):
        if not self.plugins_dir:
            return "Plugins directory not configured"
        filename = secure_filename(file.filename)
        if not filename.endswith('.jar'):
            return "Invalid file type"
        filepath = os.path.join(self.plugins_dir, filename)
        try:
            file.save(filepath)
            return "Uploaded"
        except:
            return "Upload failed"

    def delete_plugin(self, plugin_name):
        if not self.plugins_dir:
            return False
        plugin_path = os.path.join(self.plugins_dir, plugin_name)
        if os.path.exists(plugin_path) and plugin_name.endswith('.jar'):
            try:
                os.remove(plugin_path)
                return True
            except:
                pass
        return False