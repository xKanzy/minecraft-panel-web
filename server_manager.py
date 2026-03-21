import subprocess
import os
import time
import psutil
import sys
from config_manager import config

class MinecraftServerManager:
    def __init__(self):
        self.process = None
        self.pid = None
        self.stdout_file = None
        self.load_pid()

    def load_pid(self):
        pid_file = config.get('PID_FILE')
        if pid_file and os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    self.pid = int(f.read().strip())
                if self.is_running():
                    self.process = psutil.Process(self.pid)
                else:
                    os.remove(pid_file)
                    self.pid = None
            except (ValueError, psutil.NoSuchProcess, FileNotFoundError):
                if os.path.exists(pid_file):
                    os.remove(pid_file)
                self.pid = None

    def is_running(self):
        if not self.pid:
            return False
        try:
            if not psutil.pid_exists(self.pid):
                return False
            proc = psutil.Process(self.pid)
            cmdline = ' '.join(proc.cmdline())
            server_jar = config.get('SERVER_JAR')
            # Проверяем, что это Java процесс и содержит server.jar
            if ('java' in proc.name().lower() or 'javaw' in proc.name().lower()) and server_jar in cmdline:
                return True
            else:
                pid_file = config.get('PID_FILE')
                if pid_file and os.path.exists(pid_file):
                    os.remove(pid_file)
                self.pid = None
                return False
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def start(self):
        if self.is_running():
            return "Server is already running."
        server_dir = config.get('SERVER_DIR')
        if not server_dir or not os.path.isdir(server_dir):
            return "Server directory not configured or does not exist."
        
        os.chdir(server_dir)
        stdout_path = os.path.join(server_dir, "server_stdout.log")
        self.stdout_file = open(stdout_path, "a", encoding='utf-8')
        
        # Команда запуска
        java_cmd = config.get('JAVA_CMD')
        java_args = config.get('JAVA_ARGS')
        
        # Для Windows, если java.exe не найден, ищем в PATH
        if sys.platform == 'win32' and not os.path.exists(java_cmd):
            import shutil
            java_cmd = shutil.which('java') or 'java'
        
        cmd = [java_cmd] + java_args
        
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=self.stdout_file,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        self.pid = self.process.pid
        pid_file = config.get('PID_FILE')
        if pid_file:
            with open(pid_file, 'w') as f:
                f.write(str(self.pid))
        time.sleep(2)
        return "Server started."

    def stop(self):
        if not self.is_running():
            return "Server is not running."
        self.send_command("stop")
        timeout = 60
        start_time = time.time()
        while self.is_running() and time.time() - start_time < timeout:
            time.sleep(1)
        if self.is_running():
            return self.kill()
        else:
            self.cleanup()
            return "Server stopped."

    def kill(self):
        if self.is_running():
            try:
                proc = psutil.Process(self.pid)
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except psutil.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            except:
                pass
            self.cleanup()
            return "Server killed."
        return "Server is not running."

    def send_command(self, command):
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(command + "\n")
                self.process.stdin.flush()
                return True
            except (BrokenPipeError, OSError):
                return False
        return False

    def get_logs(self, lines=50):
        server_dir = config.get('SERVER_DIR')
        if server_dir:
            stdout_log = os.path.join(server_dir, "server_stdout.log")
            if os.path.exists(stdout_log):
                try:
                    with open(stdout_log, 'r', encoding='utf-8', errors='ignore') as f:
                        logs = f.readlines()
                        return logs[-lines:] if logs else ["No logs yet."]
                except:
                    pass
        log_file = config.get('LOG_FILE')
        if log_file and os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    logs = f.readlines()
                    return logs[-lines:] if logs else ["No logs yet."]
            except:
                pass
        return ["No logs found."]

    def get_logs_since(self, last_size):
        server_dir = config.get('SERVER_DIR')
        if not server_dir:
            return [], 0
        stdout_log = os.path.join(server_dir, "server_stdout.log")
        if not os.path.exists(stdout_log):
            return [], 0
        try:
            with open(stdout_log, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(0, os.SEEK_END)
                current_size = f.tell()
                if last_size >= current_size:
                    return [], current_size
                f.seek(last_size)
                new_lines = f.readlines()
                return new_lines, current_size
        except:
            return [], 0

    def get_players(self):
        log_file = config.get('LOG_FILE')
        if not log_file or not os.path.exists(log_file):
            return []
        players = set()
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if "joined the game" in line:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "joined" and i > 0:
                                players.add(parts[i-1])
                    elif "players online:" in line:
                        if ": " in line:
                            after = line.split(": ", 1)[1]
                            for name in after.split(","):
                                players.add(name.strip())
        except:
            pass
        return list(players)

    def cleanup(self):
        pid_file = config.get('PID_FILE')
        if pid_file and os.path.exists(pid_file):
            try:
                os.remove(pid_file)
            except:
                pass
        if self.stdout_file:
            try:
                self.stdout_file.close()
            except:
                pass
        self.pid = None
        self.process = None

    def force_reset(self):
        self.cleanup()
        return "Status reset."