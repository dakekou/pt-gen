# -*- coding: utf-8 -*-
"""简单文件缓存（结果 + 海报缓存）"""
import json
import os
import threading
import time


class FileCache:
    def __init__(self, path, ttl=86400):
        self.path = path
        self.ttl = ttl
        self._lock = threading.Lock()
        self._data = {}
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            self._data = {}

    def get(self, key):
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            if time.time() - item.get("ts", 0) > self.ttl:
                return None
            return item.get("value")

    def set(self, key, value):
        with self._lock:
            self._data[key] = {"ts": time.time(), "value": value}
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False)
                os.replace(tmp, self.path)
            except Exception:
                pass
