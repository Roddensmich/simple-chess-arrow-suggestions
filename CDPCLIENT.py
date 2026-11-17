import json
import logging
import sys
import threading
import time
import requests
import websocket

from misc_bot import JS_MASK_WEBDRIVER

log = logging.getLogger(__name__)

class CDPClient:
    def __init__(self, host="localhost", port=9222):
        self.host, self.port = host, port
        self.ws = None
        self._id = 0
        self._lock = threading.Lock()

    def connect(self, retries: int = 20, delay: float = 0.5) -> bool:
        last_err = None
        for _ in range(retries):
            try:
                tabs = requests.get(f"http://{self.host}:{self.port}/json", timeout=3).json()
                target = next((t for t in tabs if "chess.com" in t.get("url", "")), None)
                if not target:
                    last_err = "no chess.com tab"
                    time.sleep(delay)
                    continue
                self.ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=5)
                break
            except Exception as e:
                last_err = repr(e)
                time.sleep(delay)
        else:
            log.error("CDP connect failed: %s", last_err)
            return False

        try:
            self._call("Page.enable")
            self._call("Runtime.evaluate", {"expression": JS_MASK_WEBDRIVER})
            self._call("Page.addScriptToEvaluateOnNewDocument", {"source": JS_MASK_WEBDRIVER})
        except Exception as e:
            log.error("CDP handshake failed: %s", e)
            return False
        return True

    def _call(self, method, params=None) -> dict:
        with self._lock:
            if not self.ws: return {}
            self._id += 1
            try:
                self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
                for _ in range(200):
                    self.ws.settimeout(2.0) # Prevent infinite blocking
                    data = json.loads(self.ws.recv())
                    if data.get("id") == self._id: return data.get("result", {})
            except Exception:
                return {}
            return {}

    def eval_js(self, expr: str):
        r = self._call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return r.get("result", {}).get("value")

    def close(self):
        if self.ws: self.ws.close()