#!/usr/bin/env python3
"""TRACE demo dashboard — visual relational graph + chat recall.

Read-only, localhost-only pitch surface over the live hub DB:
  left   interactive force-directed memory graph (click nodes to inspect)
  right  selected-entity facts with provenance + "Ask TRACE" chat

    python3 scripts/trace_demo_dashboard.py            # http://localhost:8777
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soma_hub.crypto import EncryptedTextCodec
from soma_hub.graph import RelationalMemoryGraph
from soma_hub.recall import RecallFirewall
from soma_hub.storage import MemoryStore

DB = ROOT / "data" / "soma_hub.sqlite3"
PORT = 8777

_codec = EncryptedTextCodec.from_env_or_file(DB.parent)
_graph = RelationalMemoryGraph(DB, _codec)
_recall = RecallFirewall(MemoryStore(DB, _codec), _graph)

_HIDDEN_ATTRS = {"recent_messages"}  # raw message arcs stay out of the demo UI


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def _norm_label(label: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/ -]+", " ", label.lower())).strip()


def _trust_value(value) -> str:
    trust = str(value or "trusted").strip().lower()
    return "rejected" if trust == "rejected" else "trusted"


def _name_source(value) -> str:
    return str(value or "").strip() or "unknown"


def _int_or_default(value, default: int = 1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float_or_default(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _footprint_or_empty(value) -> list[list[float]]:
    if not isinstance(value, list):
        return []
    footprint = []
    for point in value[:24]:
        if not isinstance(point, list) or len(point) < 2:
            continue
        try:
            x = float(point[0])
            z = float(point[1])
        except (TypeError, ValueError):
            continue
        if math.isfinite(x) and math.isfinite(z):
            footprint.append([x, z])
    return footprint


def _json_dict(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_offline_walk(metadata: dict, pose: dict | None = None) -> bool:
    if str(metadata.get("capture_mode") or "") == "offline_walk":
        return True
    if str(metadata.get("source") or metadata.get("provider") or "") == "offline_walk":
        return True
    return bool(pose and str(pose.get("source") or "") == "offline_walk")


def _objects_from_spatial_metadata(metadata: dict, captured_at: str) -> list[dict]:
    objects = []
    for idx, word in enumerate(metadata.get("spatial_words") or []):
        try:
            x = float(word.get("x"))
            y = float(word.get("y"))
            z = float(word.get("z"))
        except (TypeError, ValueError, AttributeError):
            continue
        label = str(word.get("label") or "").strip()
        if not label:
            continue
        objects.append({
            "id": f"live:{captured_at}:{idx}:{label}",
            "label": label,
            "kind": str(word.get("kind") or "object"),
            "x": x,
            "y": y,
            "z": z,
            "w": _float_or_default(word.get("w") or word.get("width")),
            "h": _float_or_default(word.get("h") or word.get("height")),
            "footprint": _footprint_or_empty(word.get("footprint")),
            "heightM": _float_or_default(word.get("heightM") or word.get("height_m")),
            "support_plane": word.get("support_plane") if word.get("support_plane") is not None else None,
            "strength": _int_or_default(word.get("strength") or word.get("sightings"), 1),
            "verified": bool(word.get("verified")),
            "relabeled_from": word.get("relabeled_from") if isinstance(word.get("relabeled_from"), list) else [],
            "position_spread": _float_or_default(word.get("position_spread")),
            "position_confidence": str(word.get("position_confidence") or "low"),
            "source": "live",
            "trust": _trust_value(word.get("trust") or metadata.get("trust")),
            "name_source": _name_source(word.get("name_source") or metadata.get("name_source")),
            "depth_mode": str(word.get("depth_mode") or ""),
            "build": str(metadata.get("build") or ""),
        })
    return objects


def _db_spatial_pose_object(row: sqlite3.Row) -> dict | None:
    try:
        pose = json.loads(row["attribute_value"] or "{}")
        x = float(pose.get("x"))
        y = float(pose.get("y"))
        z = float(pose.get("z"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    metadata = _json_dict(row["metadata_json"])
    source = "offline" if _is_offline_walk(metadata, pose) else "db"
    label = str(row["label"] or "").strip()
    if not label:
        return None
    return {
        "id": f"db:{row['entity_id']}",
        "label": label,
        "kind": str(row["kind"] or "object"),
        "x": x,
        "y": y,
        "z": z,
        "w": _float_or_default(pose.get("w")),
        "h": _float_or_default(pose.get("h")),
        "footprint": _footprint_or_empty(pose.get("footprint")),
        "heightM": _float_or_default(pose.get("heightM") or pose.get("height_m")),
        "support_plane": pose.get("support_plane") if pose.get("support_plane") is not None else None,
        "strength": _int_or_default(pose.get("sightings"), 1),
        "verified": bool(pose.get("verified")),
        "relabeled_from": pose.get("relabeled_from") if isinstance(pose.get("relabeled_from"), list) else [],
        "position_spread": _float_or_default(pose.get("position_spread")),
        "position_confidence": str(pose.get("position_confidence") or "low"),
        "source": source,
        "trust": _trust_value(pose.get("trust") or metadata.get("trust")),
        "name_source": _name_source(pose.get("name_source") or metadata.get("name_source")),
        "depth_mode": str(pose.get("depth_mode") or metadata.get("depth_mode") or ""),
        "offline_inventory": metadata.get("offline_inventory") if isinstance(metadata.get("offline_inventory"), dict) else None,
        "build": str(pose.get("build") or ""),
    }


def _offline_inventory_object(row: sqlite3.Row) -> dict | None:
    metadata = _json_dict(row["metadata_json"])
    inventory = metadata.get("offline_inventory")
    if not isinstance(inventory, dict):
        return None
    label = str(inventory.get("label") or row["label"] or "").strip()
    if not label:
        return None
    evidence = inventory.get("frame_evidence") if isinstance(inventory.get("frame_evidence"), list) else []
    return {
        "id": f"offline:{row['entity_id']}",
        "label": label,
        "kind": str(row["kind"] or "object"),
        "x": None,
        "y": None,
        "z": None,
        "w": 0,
        "h": 0,
        "footprint": [],
        "heightM": 0,
        "support_plane": None,
        "strength": _int_or_default(inventory.get("count"), 1),
        "verified": False,
        "relabeled_from": [],
        "position_spread": 0,
        "position_confidence": "positionless",
        "source": "offline",
        "trust": _trust_value(inventory.get("trust") or metadata.get("trust")),
        "name_source": _name_source(inventory.get("name_source") or metadata.get("name_source")),
        "depth_mode": str(inventory.get("depth_mode") or metadata.get("depth_mode") or "none"),
        "offline_inventory": {
            "label": label,
            "count": _int_or_default(inventory.get("count"), 1),
            "frame_evidence": [str(path) for path in evidence],
            "trust": _trust_value(inventory.get("trust") or metadata.get("trust")),
            "name_source": _name_source(inventory.get("name_source") or metadata.get("name_source")),
        },
        "build": str(metadata.get("build") or ""),
    }


def api_graph() -> dict:
    with _conn() as conn:
        entities = conn.execute(
            """SELECT id, kind, label, status, observation_count, last_seen_at
               FROM graph_entities WHERE status != 'archived'
               AND TRIM(label) != '' ORDER BY last_seen_at DESC LIMIT 400"""
        ).fetchall()
        ids = {e["id"] for e in entities}
        relations = conn.execute(
            """SELECT subject_entity_id AS s, object_entity_id AS o, relation_type AS t,
                      place_id, confidence
               FROM graph_relations WHERE status != 'archived'"""
        ).fetchall()
        places = {
            p["id"]: p["name"]
            for p in conn.execute("SELECT id, name FROM graph_places").fetchall()
        }
        counts = {
            r["entity_id"]: r["v"]
            for r in conn.execute(
                """SELECT entity_id, attribute_value AS v FROM graph_attributes
                   WHERE attribute_key='message_count'"""
            ).fetchall()
        }

    nodes = [
        {
            "id": e["id"],
            "label": e["label"],
            "kind": e["kind"],
            "weight": int(counts.get(e["id"], 0) or 0) or e["observation_count"],
        }
        for e in entities
    ]
    node_ids = {n["id"] for n in nodes}
    edges = []
    used_places = set()
    for r in relations:
        if r["s"] in ids and r["o"] and r["o"] in ids:
            edges.append({"source": r["s"], "target": r["o"], "type": r["t"]})
        elif r["s"] in ids and r["place_id"] and r["place_id"] in places:
            pid = f"place:{r['place_id']}"
            if pid not in used_places:
                used_places.add(pid)
                nodes.append({"id": pid, "label": places[r["place_id"]] or "place",
                              "kind": "place", "weight": 2})
            edges.append({"source": r["s"], "target": pid, "type": r["t"]})
    # de-dup edges
    seen = set()
    edges = [e for e in edges if not (k := (e["source"], e["target"], e["type"])) in seen and not seen.add(k)]
    return {"nodes": nodes, "edges": edges}


def api_profile(entity_id: str) -> dict:
    real_id = entity_id.split("place:")[-1] if entity_id.startswith("place:") else entity_id
    with _conn() as conn:
        if entity_id.startswith("place:"):
            row = conn.execute("SELECT name AS label FROM graph_places WHERE id=?", (real_id,)).fetchone()
            return {"label": row["label"] if row else "place", "kind": "place", "facts": []}
        ent = conn.execute(
            "SELECT label, kind, first_seen_at, last_seen_at, confidence FROM graph_entities WHERE id=?",
            (entity_id,),
        ).fetchone()
        attrs = conn.execute(
            """SELECT attribute_key, attribute_value, source, last_seen_at, confidence
               FROM graph_attributes WHERE entity_id=? AND status != 'archived'
               ORDER BY last_seen_at DESC LIMIT 40""",
            (entity_id,),
        ).fetchall()
    facts = []
    for a in attrs:
        if a["attribute_key"] in _HIDDEN_ATTRS:
            continue
        value = str(a["attribute_value"])
        if len(value) > 220:
            value = value[:220] + "…"
        facts.append({
            "key": a["attribute_key"], "value": value, "source": a["source"],
            "observed": (a["last_seen_at"] or "")[:16], "confidence": a["confidence"],
        })
    return {
        "label": ent["label"] if ent else "?",
        "kind": ent["kind"] if ent else "?",
        "first_seen": (ent["first_seen_at"] or "")[:16] if ent else "",
        "last_seen": (ent["last_seen_at"] or "")[:16] if ent else "",
        "facts": facts,
    }


def api_world() -> dict:
    """Durable spatial word map, overlaid with the latest live phone snapshot."""
    with _conn() as conn:
        pose_rows = conn.execute(
            """SELECT e.id AS entity_id, e.label, e.kind, a.attribute_value,
                      a.last_seen_at, a.metadata_json
               FROM graph_attributes a
               JOIN graph_entities e ON e.id = a.entity_id
               WHERE a.attribute_key = 'spatial_pose'
                 AND a.status != 'archived'
                 AND e.status != 'archived'
               ORDER BY a.last_seen_at DESC LIMIT 200"""
        ).fetchall()
        db_objects = []
        db_captured_at = ""
        db_scanner_output = ""
        db_word_source = ""
        for row in pose_rows:
            obj = _db_spatial_pose_object(row)
            if not obj:
                continue
            db_objects.append(obj)
            if not db_captured_at:
                db_captured_at = (row["last_seen_at"] or "")[:19]
                try:
                    row_meta = json.loads(row["metadata_json"] or "{}")
                except json.JSONDecodeError:
                    row_meta = {}
                db_scanner_output = str(row_meta.get("scanner_output") or row_meta.get("fastvlm_output") or "")
                db_word_source = str(row_meta.get("word_source") or row_meta.get("provider") or "spatial_pose")

        live_objects = []
        captured_at = ""
        scanner_output = ""
        word_source = ""
        live_rows = conn.execute(
            """SELECT captured_at, metadata_json
               FROM graph_observations
               ORDER BY captured_at DESC LIMIT 200"""
        ).fetchall()
        for row in live_rows:
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except json.JSONDecodeError:
                continue
            if metadata.get("capture_mode") != "spatial_word_map":
                continue
            captured_at = (row["captured_at"] or "")[:19]
            scanner_output = str(metadata.get("scanner_output") or metadata.get("fastvlm_output") or "")
            word_source = str(metadata.get("word_source") or metadata.get("provider") or "spatial word scanner")
            live_objects = _objects_from_spatial_metadata(metadata, captured_at)
            break

        merged: dict[str, dict] = {}
        order: list[str] = []
        for obj in db_objects:
            key = _norm_label(str(obj.get("label") or ""))
            if not key:
                continue
            if key not in merged:
                order.append(key)
            merged[key] = obj
        for obj in live_objects:
            key = _norm_label(str(obj.get("label") or ""))
            if not key:
                continue
            if _trust_value(obj.get("trust")) == "rejected" and key in merged:
                continue
            if key not in merged:
                order.append(key)
            merged[key] = obj

        offline_rows = conn.execute(
            """SELECT id AS entity_id, label, kind, metadata_json
               FROM graph_entities
               WHERE status != 'archived'
                 AND metadata_json LIKE '%offline_inventory%'
               ORDER BY last_seen_at DESC"""
        ).fetchall()
        offline_positionless = []
        for row in offline_rows:
            obj = _offline_inventory_object(row)
            if not obj:
                continue
            key = _norm_label(str(obj.get("label") or ""))
            if not key or key in merged:
                continue
            offline_positionless.append(obj)
            order.append(key)
            merged[key] = obj
        objects = [merged[key] for key in order]
        positioned_objects = [
            obj for obj in objects
            if all(isinstance(obj.get(axis), (int, float)) and math.isfinite(float(obj.get(axis))) for axis in ("x", "y", "z"))
        ]
        offline_objects = [obj for obj in objects if obj.get("source") == "offline"]
        trusted_objects = [obj for obj in objects if _trust_value(obj.get("trust")) == "trusted"]
        rejected_objects = [obj for obj in objects if _trust_value(obj.get("trust")) == "rejected"]
        if not captured_at:
            captured_at = db_captured_at
            scanner_output = db_scanner_output
            word_source = db_word_source

        place_row = conn.execute("SELECT name FROM graph_places LIMIT 1").fetchone()
        stats = {
            "entities": conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0],
            "observations": conn.execute("SELECT COUNT(*) FROM graph_observations").fetchone()[0],
            "spatial_entities": len(positioned_objects),
            "world_objects": len(objects),
            "durable_spatial_entities": len(db_objects),
            "live_spatial_entities": len(live_objects),
            "offline_entities": len(offline_objects),
            "offline_positionless_entities": len(offline_positionless),
            "trusted_entities": len(trusted_objects),
            "rejected_entities": len(rejected_objects),
        }
    return {
        "place": (place_row["name"] if place_row else "your room"),
        "captured_at": captured_at,
        "has_spatial": bool(positioned_objects),
        "scanner_output": scanner_output[:700],
        "word_source": word_source,
        "objects": objects,
        "stats": stats,
    }


def api_answer(question: str) -> dict:
    result = _recall.answer(question)
    return {
        "answer": result.get("answer", ""),
        "intent": result.get("intent", ""),
        "confidence": result.get("confidence"),
        "citations": result.get("citations", [])[:8],
    }


WORLD_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>TRACE — spatial word map</title>
<style>
  :root { --bg:#0b1020; --panel:#121a30; --line:#1f2b4d; --text:#e8edf8; --dim:#8593b8; --accent:#7aa2ff; --object:#f6ad55; --plane:#68d391; --hypothesis:#9aa7c7; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family:ui-sans-serif,-apple-system,sans-serif; overflow:hidden; }
  header { position:fixed; top:0; left:0; right:0; height:56px; display:flex; align-items:center; gap:14px; padding:0 18px;
    background:rgba(11,16,32,.94); border-bottom:1px solid var(--line); z-index:2; }
  h1 { font-size:15px; letter-spacing:.18em; margin:0; }
  #status { color:var(--dim); font-size:12px; }
  #status strong { color:var(--plane); font-weight:600; }
  #stats { margin-left:auto; color:var(--dim); font-size:12px; }
  canvas { position:fixed; inset:56px 0 0 0; width:100vw; height:calc(100vh - 56px); display:block; touch-action:none; cursor:grab; }
  #empty { position:fixed; inset:56px 0 0 0; display:none; place-items:center; text-align:center; color:var(--dim); padding:24px; }
  #empty b { color:var(--text); font-weight:700; }
  #raw { position:fixed; left:14px; right:14px; bottom:12px; min-height:22px; color:var(--dim); font:12px ui-monospace,monospace;
    background:rgba(11,16,32,.84); border:1px solid var(--line); border-radius:8px; padding:7px 9px; z-index:2; }
  a.back { color:var(--accent); font-size:12px; text-decoration:none; border:1px solid var(--line); border-radius:8px; padding:4px 10px; }
</style></head><body>
<header>
  <h1>SPATIAL WORD MAP</h1>
  <a class="back" href="/">graph view</a>
  <div id="status">waiting for phone spatial snapshot</div>
  <div id="stats"></div>
</header>
<canvas id="world"></canvas>
<div id="empty"><div><b>No FastVLM spatial words have reached the hub yet.</b><br/>
Open Spatial mode on the iPhone, point at objects, and this map will refresh automatically.<br/>
This page no longer invents positions.</div></div>
<div id="raw">scanner waiting</div>
<script>
const cv = document.getElementById('world'), ctx = cv.getContext('2d');
let world = {objects: [], has_spatial:false, stats:{}};
let view = {zoom:1, panX:0, panY:0, orbit:0};
let expanded = new Set(), lastClusters = [];
const pointers = new Map();
let lastGesture = null, moved = false;

function resize(){
  cv.width = cv.clientWidth * devicePixelRatio;
  cv.height = cv.clientHeight * devicePixelRatio;
  draw();
}
addEventListener('resize', resize);

async function loadWorld(){
  try {
    world = await fetch('/api/world', {cache:'no-store'}).then(r => r.json());
    document.getElementById('status').innerHTML = world.has_spatial
      ? `<strong>${world.objects.length}</strong> real spatial words · ${verifiedCount(world.objects || [])} verified · ${world.word_source || 'scanner'} · last ${world.captured_at || 'now'}`
      : 'waiting for phone spatial snapshot';
    document.getElementById('raw').textContent = world.scanner_output
      ? `scanner: ${world.scanner_output}`
      : 'scanner waiting';
    const s = world.stats || {};
    document.getElementById('stats').textContent = `${s.observations ?? 0} observations · ${s.entities ?? 0} entities`;
  } catch {
    document.getElementById('status').textContent = 'world API unavailable';
  }
  draw();
}

function verifiedCount(objects){ return objects.filter(o => o.kind !== 'object' || o.verified).length; }
function mapOrigin(w, h){ return {x:w/2 + view.panX, y:h*.76 + view.panY}; }
function mapRange(objects){
  return Math.max(1.2, ...objects.map(o => Math.max(Math.abs(o.x || 0), Math.abs(o.y || 0), Math.abs(o.z || 0))));
}
function mapScale(objects, w, h){
  return Math.min(w, h) * .34 * view.zoom / mapRange(objects);
}
function projectVec(v, objects, w, h){
  const o = mapOrigin(w, h);
  const scale = mapScale(objects, w, h);
  const rawRight = Number(v.x) || 0;
  const rawZ = Number(v.z) || 0;
  const right = rawRight * Math.cos(view.orbit) - rawZ * Math.sin(view.orbit);
  const forward = -(rawRight * Math.sin(view.orbit) + rawZ * Math.cos(view.orbit));
  const up = Number(v.y) || 0;
  return {
    x: o.x + (right - forward * .42) * scale,
    y: o.y + (-forward * .58 - up * .95) * scale,
    depth: forward,
    scale: Math.max(.82, Math.min(1.1, 1 - forward * .035))
  };
}
function projectGround(right, forward, objects, w, h){
  return projectVec({x:right, y:0, z:-forward}, objects, w, h);
}
function roundRect(x,y,w,h,r){
  ctx.beginPath(); ctx.moveTo(x+r,y); ctx.arcTo(x+w,y,x+w,y+h,r); ctx.arcTo(x+w,y+h,x,y+h,r);
  ctx.arcTo(x,y+h,x,y,r); ctx.arcTo(x,y,x+w,y,r); ctx.closePath();
}
function fontSize(o){
  if(o.kind === 'plane') return 15;
  const extent = Math.max(Number(o.w) || 0, Number(o.h) || 0);
  return extent > 0 ? Math.max(16, Math.min(32, 16 + extent * 12)) : 20;
}
function labelMetrics(o, x, y, projectionScale=1){
  const isPlane = o.kind === 'plane';
  const px = fontSize(o) * projectionScale;
  const italic = o.kind === 'object' && !o.verified ? 'italic ' : '';
  ctx.font = `${italic}${isPlane || !o.verified ? 500 : 700} ${px}px ui-sans-serif, -apple-system, sans-serif`;
  const text = o.label;
  const padX = 9, padY = 6, tw = ctx.measureText(text).width;
  const bw = tw + padX * 2, bh = Math.max(isPlane ? 25 : 32, px + padY * 2);
  return {text, px, bw, bh, bounds:{x:x-bw/2, y:y-bh/2, w:bw, h:bh}};
}
function label(o, x, y, projectionScale=1){
  const isPlane = o.kind === 'plane';
  const m = labelMetrics(o, x, y, projectionScale);
  const verified = o.kind !== 'object' || o.verified;
  ctx.globalAlpha = verified ? 1 : .58;
  roundRect(x - m.bw/2, y - m.bh/2, m.bw, m.bh, 7);
  ctx.fillStyle = isPlane ? 'rgba(104,211,145,.12)' : (verified ? 'rgba(246,173,85,.16)' : 'rgba(154,167,199,.12)');
  ctx.fill();
  ctx.strokeStyle = isPlane ? 'rgba(104,211,145,.55)' : (verified ? 'rgba(246,173,85,.75)' : 'rgba(154,167,199,.55)');
  ctx.setLineDash(verified ? [] : [4, 4]);
  ctx.lineWidth = isPlane ? 1 : (verified ? 1.5 : 1);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = '#e8edf8';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(m.text, x, y + 1);
  ctx.globalAlpha = 1;
}
function intersects(a, b, pad=6){
  return !(a.x + a.w + pad < b.x || b.x + b.w + pad < a.x || a.y + a.h + pad < b.y || b.y + b.h + pad < a.y);
}
function priority(item){
  const o = item.o;
  return (o.kind === 'object' ? 10000 : 2000) + Math.min(Number(o.strength) || 1, 12) * 140 + (o.verified ? 600 : 0) - Math.abs(item.p.depth) * 22;
}
function makeCluster(items){
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity, depth = 0;
  for(const item of items){
    x1 = Math.min(x1, item.bounds.x); y1 = Math.min(y1, item.bounds.y);
    x2 = Math.max(x2, item.bounds.x + item.bounds.w); y2 = Math.max(y2, item.bounds.y + item.bounds.h);
    depth += item.p.depth;
  }
  const ids = items.map(i => i.o.id).sort().join('.');
  return {id:ids, items:items.sort((a,b) => priority(b) - priority(a)), x:(x1+x2)/2, y:(y1+y2)/2, bounds:{x:x1,y:y1,w:x2-x1,h:y2-y1}, depth:depth/items.length};
}
function cluster(items){
  const clusters = [];
  for(const item of items.sort((a,b) => priority(b) - priority(a))){
    const idx = clusters.findIndex(c => intersects(c.bounds, item.bounds, 8));
    if(idx >= 0) clusters[idx] = makeCluster([...clusters[idx].items, item]);
    else clusters.push(makeCluster([item]));
  }
  return clusters;
}
function chip(cluster){
  const text = `${cluster.items.length} words here`;
  ctx.font = '600 12px ui-monospace, monospace';
  const bw = ctx.measureText(text).width + 22, bh = 28;
  const x = cluster.x, y = cluster.y;
  roundRect(x - bw/2, y - bh/2, bw, bh, 14);
  ctx.fillStyle = 'rgba(18,26,48,.86)'; ctx.fill();
  ctx.strokeStyle = 'rgba(122,162,255,.65)'; ctx.lineWidth = 1.2; ctx.stroke();
  ctx.fillStyle = '#e8edf8'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(text, x, y + 1);
  cluster.chipBounds = {x:x-bw/2, y:y-bh/2, w:bw, h:bh};
}
function fanPoint(i, n, center){
  const angle = i / n * Math.PI * 2;
  const r = 36 + Math.min(42, n * 4);
  return {x:center.x + Math.cos(angle) * r, y:center.y + Math.sin(angle) * r};
}
function draw(){
  const w = cv.clientWidth, h = cv.clientHeight;
  ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  ctx.clearRect(0,0,w,h);
  const objects = (world.objects || []).filter(o => Number.isFinite(o.x) && Number.isFinite(o.z));
  document.getElementById('empty').style.display = objects.length ? 'none' : 'grid';
  const range = mapRange(objects);
  ctx.strokeStyle = 'rgba(122,162,255,.08)';
  ctx.lineWidth = 1;
  for(let m = -range; m <= range + .001; m += .5){
    let a = projectGround(-range, m, objects, w, h), b = projectGround(range, m, objects, w, h);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    a = projectGround(m, -range, objects, w, h); b = projectGround(m, range, objects, w, h);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }
  ctx.strokeStyle = 'rgba(122,162,255,.22)';
  const left = projectGround(-range, 0, objects, w, h), right = projectGround(range, 0, objects, w, h);
  const near = projectGround(0, -range, objects, w, h), far = projectGround(0, range, objects, w, h);
  const originPoint = projectVec({x:0,y:0,z:0}, objects, w, h), up = projectVec({x:0,y:1,z:0}, objects, w, h);
  ctx.beginPath(); ctx.moveTo(left.x,left.y); ctx.lineTo(right.x,right.y); ctx.moveTo(near.x,near.y); ctx.lineTo(far.x,far.y); ctx.moveTo(originPoint.x,originPoint.y); ctx.lineTo(up.x,up.y); ctx.stroke();
  ctx.fillStyle = '#7aa2ff'; ctx.beginPath(); ctx.arc(originPoint.x,originPoint.y,6,0,Math.PI*2); ctx.fill();
  ctx.fillStyle = '#8593b8'; ctx.font = '12px ui-monospace, monospace'; ctx.textAlign = 'center'; ctx.fillText('you', originPoint.x, originPoint.y + 22);
  const items = objects.map(o => {
    const p = projectVec(o, objects, w, h);
    return {o, p, bounds: labelMetrics(o, p.x, p.y, p.scale).bounds};
  });
  lastClusters = [];
  for(const c of cluster(items).sort((a,b) => b.depth - a.depth)){
    if(c.items.length === 1) {
      const item = c.items[0]; label(item.o, item.p.x, item.p.y, item.p.scale);
    } else if(expanded.has(c.id)) {
      c.items.forEach((item, i) => {
        const p = fanPoint(i, c.items.length, c);
        label(item.o, p.x, p.y, item.p.scale);
      });
    } else {
      chip(c); lastClusters.push(c);
    }
  }
  ctx.fillStyle = '#8593b8'; ctx.font = '12px ui-monospace, monospace'; ctx.textAlign = 'left';
  ctx.fillText(`${objects.length} words · ${lastClusters.length} clusters · zoom ${view.zoom.toFixed(1)}x`, 14, h - 16);
}

function pointIn(rect, x, y){ return x >= rect.x && x <= rect.x + rect.w && y >= rect.y && y <= rect.y + rect.h; }
function distance(a,b){ return Math.hypot(a.x-b.x, a.y-b.y); }
function midpoint(a,b){ return {x:(a.x+b.x)/2, y:(a.y+b.y)/2}; }
cv.addEventListener('wheel', e => {
  e.preventDefault();
  view.zoom = Math.max(.35, Math.min(5, view.zoom * (e.deltaY < 0 ? 1.12 : .89)));
  draw();
}, {passive:false});
cv.addEventListener('pointerdown', e => {
  cv.setPointerCapture(e.pointerId);
  pointers.set(e.pointerId, {x:e.offsetX, y:e.offsetY});
  moved = false;
  const pts = [...pointers.values()];
  lastGesture = pts.length >= 2 ? {mid:midpoint(pts[0], pts[1]), dist:distance(pts[0], pts[1])} : {x:e.offsetX, y:e.offsetY};
});
cv.addEventListener('pointermove', e => {
  if(!pointers.has(e.pointerId)) return;
  const prev = pointers.get(e.pointerId);
  pointers.set(e.pointerId, {x:e.offsetX, y:e.offsetY});
  const pts = [...pointers.values()];
  if(pts.length >= 2){
    const mid = midpoint(pts[0], pts[1]), dist = distance(pts[0], pts[1]);
    if(lastGesture?.mid){
      view.panX += mid.x - lastGesture.mid.x; view.panY += mid.y - lastGesture.mid.y;
      if(lastGesture.dist > 0) view.zoom = Math.max(.35, Math.min(5, view.zoom * dist / lastGesture.dist));
    }
    lastGesture = {mid, dist}; moved = true; draw();
  } else if(pts.length === 1 && lastGesture){
    const dx = e.offsetX - prev.x;
    view.orbit += dx * .006;
    if(Math.abs(e.offsetX - lastGesture.x) + Math.abs(e.offsetY - lastGesture.y) > 5) moved = true;
    draw();
  }
});
cv.addEventListener('pointerup', e => {
  if(!moved){
    const hit = lastClusters.find(c => c.chipBounds && pointIn(c.chipBounds, e.offsetX, e.offsetY));
    if(hit){ expanded.has(hit.id) ? expanded.delete(hit.id) : expanded.add(hit.id); }
  }
  pointers.delete(e.pointerId); lastGesture = null; draw();
});
cv.addEventListener('pointercancel', e => { pointers.delete(e.pointerId); lastGesture = null; });
cv.addEventListener('dblclick', () => { view = {zoom:1, panX:0, panY:0, orbit:0}; expanded.clear(); draw(); });

resize();
loadWorld();
setInterval(loadWorld, 2000);
</script></body></html>"""

HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>TRACE — your life, structured</title>
<style>
  :root { --bg:#0b1020; --panel:#121a30; --line:#1f2b4d; --text:#e8edf8; --dim:#8593b8;
          --person:#4fd1c5; --object:#f6ad55; --place:#68d391; --accent:#7aa2ff; }
  * { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--text);
      font-family:ui-sans-serif,-apple-system,'SF Pro Text',sans-serif; height:100vh; overflow:hidden; }
  header { position:fixed; top:0; left:0; right:0; height:52px; display:flex; align-items:center;
      gap:14px; padding:0 18px; background:linear-gradient(180deg,rgba(11,16,32,.95),rgba(11,16,32,.7));
      z-index:5; border-bottom:1px solid var(--line); }
  header h1 { font-size:17px; margin:0; letter-spacing:.18em; font-weight:700; }
  header h1 span { color:var(--accent); }
  header .sub { color:var(--dim); font-size:12px; }
  #legend { margin-left:auto; display:flex; gap:14px; font-size:12px; color:var(--dim); }
  .dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:5px; }
  #wrap { display:flex; height:100vh; padding-top:52px; }
  #canvasBox { flex:1; position:relative; }
  canvas { width:100%; height:100%; display:block; cursor:grab; }
  #search { position:absolute; top:12px; left:12px; background:var(--panel); border:1px solid var(--line);
      color:var(--text); border-radius:10px; padding:8px 12px; width:230px; font-size:13px; outline:none; }
  #side { width:390px; min-width:330px; border-left:1px solid var(--line); display:flex;
      flex-direction:column; background:var(--panel); min-height:0; overflow:hidden; }
  #profile { flex:1.1; min-height:0; overflow-y:auto; padding:16px; border-bottom:1px solid var(--line); }
  #profile h2 { margin:0 0 2px; font-size:17px; }
  #profile .kind { color:var(--dim); font-size:12px; text-transform:uppercase; letter-spacing:.1em; }
  .fact { margin:10px 0; padding:10px 12px; background:rgba(255,255,255,.03); border:1px solid var(--line);
      border-radius:10px; }
  .fact .k { color:var(--accent); font-size:11px; text-transform:uppercase; letter-spacing:.08em; }
  .fact .v { font-size:13.5px; margin:4px 0; line-height:1.45; }
  .meta { color:var(--dim); font-size:11px; }
  #chat { flex:1; min-height:0; display:flex; flex-direction:column; }
  #chatlog { flex:1; min-height:0; overflow-y:auto; padding:14px; display:flex; flex-direction:column; gap:10px; }
  .msg { max-width:92%; padding:10px 13px; border-radius:14px; font-size:13.5px; line-height:1.5; }
  .me { align-self:flex-end; background:var(--accent); color:#0b1020; border-bottom-right-radius:4px; }
  .trace { align-self:flex-start; background:rgba(255,255,255,.05); border:1px solid var(--line);
      border-bottom-left-radius:4px; }
  .cites { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
  .chip { font-size:10.5px; color:var(--dim); border:1px solid var(--line); border-radius:99px;
      padding:2px 9px; }
  .confbar { height:3px; border-radius:2px; background:var(--line); margin-top:8px; overflow:hidden; }
  .confbar i { display:block; height:100%; background:var(--person); }
  #askrow { display:flex; gap:8px; padding:12px; border-top:1px solid var(--line); flex-shrink:0; }
  #ask { flex:1; background:var(--bg); border:1px solid var(--line); color:var(--text);
      border-radius:10px; padding:10px 13px; font-size:13.5px; outline:none; }
  #send { background:var(--accent); border:0; color:#0b1020; font-weight:700; border-radius:10px;
      padding:0 16px; cursor:pointer; }
  .hint { color:var(--dim); font-size:12px; padding:0 14px 10px; flex-shrink:0; }
</style></head><body>
<header><h1>T R A C E <span>·</span></h1><div class="sub">a second memory — local, structured, yours</div>
  <a href="/world" style="color:var(--accent);font-size:12px;text-decoration:none;border:1px solid var(--line);border-radius:8px;padding:4px 10px;">world view →</a>
  <div id="legend">
    <span><i class="dot" style="background:var(--person)"></i>people</span>
    <span><i class="dot" style="background:var(--object)"></i>objects</span>
    <span><i class="dot" style="background:var(--place)"></i>places</span>
  </div></header>
<div id="wrap">
  <div id="canvasBox"><input id="search" placeholder="find someone or something…"/><canvas id="cv"></canvas></div>
  <div id="side">
    <div id="profile"><h2>Your memory graph</h2><div class="kind">click any node to inspect</div>
      <div class="meta" style="margin-top:10px" id="stats"></div></div>
    <div id="chat"><div id="chatlog"></div>
      <div class="hint">try: “who is …” · “what are my commitments” · “when did I last talk to …”</div>
      <div id="askrow"><input id="ask" placeholder="Ask TRACE about your life…"/><button id="send">Ask</button></div>
    </div>
  </div>
</div>
<script>
const colors = { person:'#4fd1c5', object:'#f6ad55', place:'#68d391' };
let nodes = [], edges = [], byId = {}, hover = null, selected = null, dragging = null;
let panX = 0, panY = 0, zoom = 1, query = '';
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');

function resize(){ cv.width = cv.clientWidth * devicePixelRatio; cv.height = cv.clientHeight * devicePixelRatio; }
window.addEventListener('resize', resize);

fetch('/api/graph').then(r => r.json()).then(g => {
  nodes = g.nodes.map(n => ({...n,
    x: (Math.sin(hash(n.id)) * .5 + .5) * 900 - 450,
    y: (Math.cos(hash(n.id) * 1.7) * .5 + .5) * 700 - 350,
    vx: 0, vy: 0,
    r: 4 + Math.min(14, Math.sqrt(n.weight || 1) * 1.6)}));
  nodes.forEach(n => byId[n.id] = n);
  edges = g.edges.filter(e => byId[e.source] && byId[e.target]);
  document.getElementById('stats').textContent =
    nodes.length + ' entities · ' + edges.length + ' relations · built from your messages and camera';
  resize(); tick();
});
function hash(s){ let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0; return h; }

function tick(){
  // forces
  for (let i = 0; i < nodes.length; i++){
    const a = nodes[i];
    for (let j = i + 1; j < nodes.length; j++){
      const b = nodes[j];
      let dx = a.x - b.x, dy = a.y - b.y;
      let d2 = dx * dx + dy * dy + 40;
      const f = 1600 / d2;
      const d = Math.sqrt(d2);
      dx /= d; dy /= d;
      a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
    }
    a.vx -= a.x * 0.0018; a.vy -= a.y * 0.0018; // gravity to center
  }
  for (const e of edges){
    const a = byId[e.source], b = byId[e.target];
    let dx = b.x - a.x, dy = b.y - a.y;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const f = (d - 90) * 0.004;
    dx /= d; dy /= d;
    a.vx += dx * f * d * .01; a.vy += dy * f * d * .01;
    b.vx -= dx * f * d * .01; b.vy -= dy * f * d * .01;
  }
  for (const n of nodes){
    if (n === dragging) { n.vx = n.vy = 0; continue; }
    n.vx *= .85; n.vy *= .85; n.x += n.vx; n.y += n.vy;
  }
  draw();
  requestAnimationFrame(tick);
}

function draw(){
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  ctx.clearRect(0, 0, cv.clientWidth, cv.clientHeight);
  ctx.translate(cv.clientWidth / 2 + panX, cv.clientHeight / 2 + panY);
  ctx.scale(zoom, zoom);
  ctx.strokeStyle = 'rgba(122,162,255,.16)'; ctx.lineWidth = 1;
  for (const e of edges){
    const a = byId[e.source], b = byId[e.target];
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  }
  for (const n of nodes){
    const dim = query && !n.label.toLowerCase().includes(query);
    const c = colors[n.kind] || '#a0aec0';
    ctx.globalAlpha = dim ? .12 : 1;
    if (n === selected || n === hover){
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 6, 0, 7); ctx.fillStyle = c + '33'; ctx.fill();
    }
    ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 7); ctx.fillStyle = c; ctx.fill();
    if (!dim && (n.r > 7 || n === hover || n === selected || zoom > 1.5)){
      ctx.fillStyle = 'rgba(232,237,248,.92)'; ctx.font = '11px ui-sans-serif';
      ctx.fillText(n.label.slice(0, 26), n.x + n.r + 4, n.y + 4);
    }
    ctx.globalAlpha = 1;
  }
}

function pick(mx, my){
  const x = (mx - cv.clientWidth / 2 - panX) / zoom, y = (my - cv.clientHeight / 2 - panY) / zoom;
  return nodes.find(n => (n.x - x) ** 2 + (n.y - y) ** 2 < (n.r + 4) ** 2);
}
let panStart = null;
cv.addEventListener('mousedown', e => {
  const n = pick(e.offsetX, e.offsetY);
  if (n) dragging = n; else panStart = {x: e.offsetX - panX, y: e.offsetY - panY};
});
cv.addEventListener('mousemove', e => {
  if (dragging){
    dragging.x = (e.offsetX - cv.clientWidth / 2 - panX) / zoom;
    dragging.y = (e.offsetY - cv.clientHeight / 2 - panY) / zoom;
  } else if (panStart){ panX = e.offsetX - panStart.x; panY = e.offsetY - panStart.y; }
  else hover = pick(e.offsetX, e.offsetY);
});
window.addEventListener('mouseup', e => {
  if (dragging && Math.abs(dragging.vx) < 9){ select(dragging); }
  dragging = null; panStart = null;
});
cv.addEventListener('wheel', e => { e.preventDefault(); zoom = Math.min(4, Math.max(.3, zoom * (e.deltaY < 0 ? 1.1 : .9))); }, {passive: false});
document.getElementById('search').addEventListener('input', e => query = e.target.value.toLowerCase());

function select(n){
  selected = n;
  fetch('/api/profile?id=' + encodeURIComponent(n.id)).then(r => r.json()).then(p => {
    const el = document.getElementById('profile');
    let html = `<h2>${esc(p.label)}</h2><div class="kind">${esc(p.kind)} · first seen ${esc(p.first_seen || '?')} · last ${esc(p.last_seen || '?')}</div>`;
    for (const f of p.facts){
      html += `<div class="fact"><div class="k">${esc(f.key)}</div><div class="v">${esc(f.value)}</div>
        <div class="meta">${esc(f.source)} · ${esc(f.observed)} · conf ${(f.confidence ?? 0).toFixed(2)}</div></div>`;
    }
    if (!p.facts.length) html += '<div class="meta" style="margin-top:12px">no stored facts yet — keep the camera on it</div>';
    el.innerHTML = html;
  });
}
function esc(s){ return String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

const log = document.getElementById('chatlog');
function addMsg(text, cls){ const d = document.createElement('div'); d.className = 'msg ' + cls; d.textContent = text; log.appendChild(d); log.scrollTop = 1e9; return d; }
function ask(){
  const q = document.getElementById('ask').value.trim();
  if (!q) return;
  document.getElementById('ask').value = '';
  addMsg(q, 'me');
  const pending = addMsg('…', 'trace');
  fetch('/api/answer?q=' + encodeURIComponent(q)).then(r => r.json()).then(a => {
    pending.textContent = a.answer || 'No answer.';
    if (a.citations && a.citations.length){
      const c = document.createElement('div'); c.className = 'cites';
      for (const cit of a.citations){
        if ((cit.confidence ?? 0) === 0) continue;
        const chip = document.createElement('span'); chip.className = 'chip';
        chip.textContent = `${cit.source || 'memory'} · ${(cit.captured_at || '').slice(0, 10)} · ${(cit.confidence ?? 0).toFixed(2)}`;
        c.appendChild(chip);
      }
      pending.appendChild(c);
    }
    if (a.confidence != null){
      const bar = document.createElement('div'); bar.className = 'confbar';
      const fill = document.createElement('i'); fill.style.width = Math.round(a.confidence * 100) + '%';
      bar.appendChild(fill); pending.appendChild(bar);
    }
  }).catch(() => pending.textContent = 'recall error');
}
document.getElementById('send').onclick = ask;
document.getElementById('ask').addEventListener('keydown', e => { if (e.key === 'Enter') ask(); });
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def _json(self, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        try:
            if url.path == "/":
                body = HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif url.path == "/world":
                body = WORLD_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif url.path == "/world3d":
                # Navigable three.js word-world (qwen-written page, lead-wired
                # route). Falls back to a pointer at /world if the file is gone.
                page = Path(__file__).resolve().parent / "world3d.html"
                try:
                    body = page.read_bytes()
                except OSError:
                    body = b'<html><body style="background:#111;color:#eee">world3d.html missing - use <a href="/world">/world</a></body></html>'
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif url.path == "/api/world":
                self._json(api_world())
            elif url.path == "/api/graph":
                self._json(api_graph())
            elif url.path == "/api/profile":
                entity_id = parse_qs(url.query).get("id", [""])[0]
                self._json(api_profile(entity_id))
            elif url.path == "/api/answer":
                q = parse_qs(url.query).get("q", [""])[0]
                self._json(api_answer(q))
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as exc:  # demo surface: report, never crash
            self._json({"error": str(exc)[:300]})


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"TRACE demo dashboard: http://localhost:{PORT}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
