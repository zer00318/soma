from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from soma_hub.service import SomaHub


def make_handler(hub: SomaHub, token: str):
    class SomaHandler(BaseHTTPRequestHandler):
        server_version = "SOMAHub/0.1"

        def do_GET(self) -> None:
            if not self._authorized():
                return self._json({"error": "unauthorized"}, status=401)
            if self.path == "/health":
                return self._json({"ok": True})
            if self.path == "/status":
                return self._json(hub.status())
            if self.path == "/metadata":
                return self._json(hub.metadata())
            if self.path.startswith("/graph/profiles"):
                query = self._query_params()
                return self._json(hub.graph_profiles(label=query.get("label")))
            if self.path.startswith("/graph/relations"):
                query = self._query_params()
                return self._json(
                    hub.graph_relations(
                        label=query.get("label"),
                        relation_type=query.get("relation_type"),
                    )
                )
            if self.path == "/graph":
                return self._json(hub.graph_metadata())
            if self.path == "/entities":
                entities = hub.entities_list()
                return self._json({"entities": entities, "total": len(entities)})
            if self.path == "/dashboard":
                meta = hub.graph_metadata()
                entities = meta.get("recent_entities", [])
                relations = meta.get("recent_relations", [])
                rows = "".join(
                    f"<tr><td>{e['label']}</td><td>{e['kind']}</td>"
                    f"<td>{e['status']}</td><td>{(e['last_seen_at'] or '')[:10]}</td></tr>"
                    for e in entities
                )
                rels = "".join(
                    f"<li>{r['subject']} → {r['relation_type']} → {r.get('object','')}</li>"
                    for r in relations[:5]
                )
                html = (
                    f"<html><head><title>SOMA</title><style>"
                    f"body{{font-family:sans-serif;padding:24px;background:#0d0d0d;color:#e0e0e0}}"
                    f"h1{{color:#7DF9FF}}table{{border-collapse:collapse;width:100%}}"
                    f"td,th{{border:1px solid #333;padding:6px 10px;text-align:left}}"
                    f"th{{background:#1a1a1a}}</style></head><body>"
                    f"<h1>SOMA Hub</h1>"
                    f"<p>Entities: <b>{meta.get('entities',0)}</b> &nbsp; Relations: <b>{meta.get('relations',0)}</b></p>"
                    f"<h2>Recent entities</h2><table><tr><th>Label</th><th>Kind</th><th>Status</th><th>Last seen</th></tr>{rows}</table>"
                    f"<h2>Recent relations</h2><ul>{rels}</ul>"
                    f"</body></html>"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode())
                return
            if self.path.startswith("/search"):
                q = self._query_params().get("q", "").strip()
                if not q:
                    return self._json({"error": "q is required"}, status=400)
                return self._json(hub.search(q))
            if self.path == "/evaluate":
                return self._json(hub.benchmark())
            return self._json({"error": "not found"}, status=404)

        def do_POST(self) -> None:
            try:
                payload = self._read_json()
                if not self._authorized():
                    return self._json({"error": "unauthorized"}, status=401)
                if self.path == "/pair":
                    return self._json(
                        {
                            "ok": True,
                            "hub_name": "SOMA Local Hub",
                            "hub_version": "0.1.0",
                            "status": hub.status(),
                        }
                    )
                if self.path == "/capture/text":
                    text = str(payload.get("text", "")).strip()
                    if not text:
                        return self._json({"error": "text is required"}, status=400)
                    return self._json(hub.ingest_text(text, str(payload.get("source_type", "audio"))))
                if self.path == "/capture/extracted":
                    text = str(payload.get("text", "")).strip()
                    if not text:
                        return self._json({"error": "text is required"}, status=400)
                    return self._json(hub.ingest_extracted(payload))
                if self.path == "/capture/perception":
                    text = str(payload.get("memory_text") or payload.get("text") or "").strip()
                    if not text:
                        return self._json({"error": "memory_text or text is required"}, status=400)
                    return self._json(hub.ingest_perception(payload))
                if self.path.startswith("/entities/") and self.path.endswith("/enrich"):
                    entity_id = self.path.split("/")[2]
                    vlm_description = str(payload.get("vlm_description", "")).strip()
                    captured_at = str(payload.get("captured_at", "")).strip()
                    if not vlm_description or not captured_at:
                        return self._json({"error": "vlm_description and captured_at are required"}, status=400)
                    attrs = hub.vlm_enrich(entity_id, vlm_description, captured_at)
                    return self._json({"status": "enriched", "entity_id": entity_id, "attributes": attrs})
                if self.path == "/chat":
                    message = str(payload.get("message", "")).strip()
                    if not message:
                        return self._json({"error": "message is required"}, status=400)
                    return self._json(hub.chat(message))
                if self.path == "/persons/link":
                    encounter_label = str(payload.get("encounter_label", "")).strip()
                    real_name = str(payload.get("real_name", "")).strip()
                    if not encounter_label or not real_name:
                        return self._json({"error": "encounter_label and real_name required"}, status=400)
                    return self._json(hub.link_person_name(encounter_label, real_name))
                if self.path == "/import/whatsapp":
                    path = str(payload.get("path", "")).strip()
                    if not path:
                        return self._json({"error": "path is required"}, status=400)
                    return self._json({"imported": hub.import_whatsapp(path)})
                if self.path == "/import/ics":
                    path = str(payload.get("path", "")).strip()
                    if not path:
                        return self._json({"error": "path is required"}, status=400)
                    return self._json({"imported": hub.import_ics(path)})
                if self.path == "/import/imessage":
                    return self._json({"imported": hub.import_imessage()})
                if self.path == "/delete":
                    return self._json(hub.delete(payload))
            except Exception as exc:
                return self._json({"error": str(exc)}, status=400)
            return self._json({"error": "not found"}, status=404)

        def log_message(self, format: str, *args: Any) -> None:
            import sys, datetime
            msg = format % args
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {self.address_string()} {msg}", file=sys.stderr, flush=True)

        def _authorized(self) -> bool:
            return self.headers.get("X-SOMA-Token") == token

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw or "{}")

        def _json(self, payload: dict, status: int = 200) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-SOMA-Token")
            self.end_headers()
            self.wfile.write(data)

        def _query_params(self) -> dict[str, str]:
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(self.path)
            values = parse_qs(parsed.query)
            return {key: items[-1] for key, items in values.items() if items}

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-SOMA-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()

    return SomaHandler


def run_server(host: str, port: int, data_dir: Path, token: str) -> None:
    hub = SomaHub(data_dir)
    server = ThreadingHTTPServer((host, port), make_handler(hub, token))
    print(f"SOMA hub listening on http://{host}:{port}")
    print("Use X-SOMA-Token for local app requests.")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SOMA local hub API.")
    parser.add_argument("--host", default="0.0.0.0")  # LAN-accessible for iPhone pairing
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    token = os.environ.get("SOMA_HUB_TOKEN", "dev-token")
    run_server(args.host, args.port, Path(args.data_dir), token)


if __name__ == "__main__":
    main()
