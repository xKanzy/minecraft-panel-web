import os
import shutil
import zipfile
import datetime
from config_manager import config

class BackupManager:
    def __init__(self):
        self.backup_dir = config.get('BACKUP_DIR')
        self.max_backups = config.get('MAX_BACKUPS')
        self.server_dir = config.get('SERVER_DIR')
        if self.backup_dir:
            os.makedirs(self.backup_dir, exist_ok=True)

    def create_backup(self):
        if not self.backup_dir or not self.server_dir:
            return "Backup directory or server directory not configured"
        world_path = os.path.join(self.server_dir, "world")
        if not os.path.exists(world_path):
            return "World folder not found. Is the server running?"

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}.zip"
        backup_path = os.path.join(self.backup_dir, backup_name)

        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(world_path):
                    dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__']]
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, self.server_dir)
                        zipf.write(file_path, arcname)
            self._cleanup_old_backups()
            return f"Backup created: {backup_name}"
        except Exception as e:
            return f"Error creating backup: {e}"

    def list_backups(self):
        if not self.backup_dir or not os.path.exists(self.backup_dir):
            return []
        backups = []
        for filename in os.listdir(self.backup_dir):
            if filename.endswith('.zip'):
                filepath = os.path.join(self.backup_dir, filename)
                stat = os.stat(filepath)
                backups.append({
                    'name': filename,
                    'size': stat.st_size,
                    'modified': datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
        backups.sort(key=lambda x: x['name'], reverse=True)
        return backups

    def restore_backup(self, backup_name):
        if not self.backup_dir or not self.server_dir:
            return "Backup directory or server directory not configured"
        backup_path = os.path.join(self.backup_dir, backup_name)
        if not os.path.exists(backup_path):
            return "Backup file not found."

        world_path = os.path.join(self.server_dir, "world")
        temp_dir = os.path.join(self.server_dir, "world_restore_temp")
        try:
            if os.path.exists(world_path):
                shutil.rmtree(world_path)

            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall(temp_dir)
            extracted_world = os.path.join(temp_dir, "world")
            if os.path.exists(extracted_world):
                shutil.move(extracted_world, world_path)
            else:
                shutil.move(temp_dir, world_path)
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            return f"Restored from {backup_name}"
        except Exception as e:
            return f"Error restoring backup: {e}"

    def delete_backup(self, backup_name):
        if not self.backup_dir:
            return False
        backup_path = os.path.join(self.backup_dir, backup_name)
        if os.path.exists(backup_path):
            os.remove(backup_path)
            return True
        return False

    def _cleanup_old_backups(self):
        if not self.backup_dir:
            return
        backups = self.list_backups()
        if len(backups) > self.max_backups:
            for backup in backups[self.max_backups:]:
                self.delete_backup(backup['name'])