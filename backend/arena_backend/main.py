from __future__ import annotations

import json
import sys
import threading
from typing import Any

from .application import BackendApplication


class JsonLineTransport:
    def __init__(self):
        self._output_lock = threading.Lock()

    def send(self, message: dict[str, Any]) -> None:
        line = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        with self._output_lock:
            sys.stdout.write(line + "\n")
            try:
                sys.stdout.flush()
            except OSError:
                sys.stderr.write(f"[transport] flush failed for: {line[:200]}\n")
                sys.stderr.flush()

    def event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.send({"kind": "event", "type": event_type, "payload": payload})


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    transport = JsonLineTransport()
    application = BackendApplication(transport.event)
    transport.event("backend_ready", {"protocolVersion": 1})
    try:
        for raw_line in sys.stdin:
            if not raw_line.strip():
                continue
            request_id: str | None = None
            try:
                request = json.loads(raw_line)
                request_id = str(request.get("id", ""))
                result = application.execute(str(request["type"]), request.get("payload", {}))
                transport.send({"kind": "response", "id": request_id, "ok": True, "result": result})
            except Exception as exc:
                transport.send({"kind": "response", "id": request_id, "ok": False, "error": {"code": type(exc).__name__, "message": str(exc)}})
    finally:
        application.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
