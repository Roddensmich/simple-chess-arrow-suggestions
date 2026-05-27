import json
import logging
import sys

log = logging.getLogger(__name__)
import threading
import time
import requests # type: ignore
import websocket # type: ignore

from misc_bot import JS_MASK_WEBDRIVER


class CDPClient:
    def __init__(self, host="localhost", port=9222):
        self.host = host
        self.port = port
        self.ws = None
        self._id = 0
        self._lock = threading.Lock()

    def connect(self) -> bool:
        try:
            tabs = requests.get(f"http://{self.host}:{self.port}/json", timeout=5).json()
        except Exception as e:
            log.error("Cannot reach browser on port %d — %s", self.port, e)
            sys.exit(1)
        target = next((t for t in tabs if "chess.com" in t.get("url", "") and t.get("type") == "page"), None)
        if not target:
            log.error("WHY I CANNOT FIND CHESS.COM??")
            sys.exit(1)
        try:
            self.ws = websocket.create_connection(
                target["webSocketDebuggerUrl"], timeout=10)
        except Exception as e:
            log.error("WebSocket error: %s", e)
            sys.exit(1)
        self._call("Page.enable")
        self._call("Runtime.evaluate", {"expression": JS_MASK_WEBDRIVER, "returnByValue": False})
        self._call("Page.addScriptToEvaluateOnNewDocument", {"source": JS_MASK_WEBDRIVER})
        return True

    def disconnect(self):
        try:
            if self.ws: self.ws.close()
        except Exception:
            pass
        self.ws = None

    def reconnect(self) -> bool:
        self.disconnect()
        time.sleep(0.8)
        return self.connect()

    def _call(self, method, params=None) -> dict:
        with self._lock:
            self._id += 1
            self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
            for _ in range(200):
                data = json.loads(self.ws.recv())
                if data.get("id") == self._id:
                    return data.get("result", {})
            log.error("_call: no matching response after 200 messages for %s", method)
            return {}

    def eval_js(self, expr: str):
        r = self._call("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": False})
        if r.get("exceptionDetails"):
            raise RuntimeError(r["exceptionDetails"])
        return r.get("result", {}).get("value")

    def close(self):
        if self.ws: self.ws.close()