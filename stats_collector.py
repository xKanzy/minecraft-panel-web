import psutil
import time
import threading
import json
import os
import sys
from config_manager import config

def fallback_path():
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.abspath('.')
    return os.path.join(base, 'stats_fallback.json')

class StatsCollector:
    def __init__(self):
        self.stats_file = config.get('STATS_FILE')
        self.interval = config.get('STATS_INTERVAL')
        self.running = False
        self.thread = None
        self.stats = []
        self.fallback = False
        self.load_stats()
        self.start_collection()

    def load_stats(self):
        if self.stats_file and os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r') as f:
                    self.stats = json.load(f)
                return
            except:
                pass
        fall = fallback_path()
        if os.path.exists(fall):
            try:
                with open(fall, 'r') as f:
                    self.stats = json.load(f)
                self.fallback = True
            except:
                self.stats = []
        if len(self.stats) > 1000:
            self.stats = self.stats[-1000:]

    def save_stats(self):
        target = fallback_path() if self.fallback else self.stats_file
        if not target:
            return
        try:
            with open(target, 'w') as f:
                json.dump(self.stats[-500:], f)
        except PermissionError:
            if not self.fallback and self.stats_file:
                self.fallback = True
                try:
                    with open(fallback_path(), 'w') as f:
                        json.dump(self.stats[-500:], f)
                except:
                    pass

    def collect(self):
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        timestamp = time.time()
        self.stats.append({
            'timestamp': timestamp,
            'cpu': cpu,
            'ram': mem
        })
        self.save_stats()

    def start_collection(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def _run(self):
        while self.running:
            self.collect()
            time.sleep(self.interval)

    def stop_collection(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

    def get_stats(self):
        return self.stats[-60:]

stats_collector = StatsCollector()