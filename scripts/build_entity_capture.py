#!/usr/bin/env python3
"""Sprint 2 — ENTITY-CENTRIC capture: bind attributes to the RIGHT entity AT CAPTURE.

The mis-attribution that no downstream gate could fix (Sprint 1) is born HERE, in the
caption: "a person in green, a person in pink, a backpack reading North Face" already
mixes the entities — WHO wore what is lost the instant the pixels become one prose blob.

So this stage does NOT emit prose. Per salient keyframe it makes ONE Qwen2.5-VL call that
returns STRUCTURED JSON: each person a SELF-CONTAINED record (its own clothing/accessories/
holding/position), each logo bound to ITS object (backpack vs shirt), and a self-view flag for
when the wearer's own body/hands are in frame. The binding happens INSIDE the model's look,
while the pixels still say who-wore-what — that is the whole move.

Output: one NDJSON row per keyframe, checkpointed (resume-safe), mirroring
build_keyframe_memory.py exactly (same model, slow image processor, frame globbing, downscale,
pick_keyframes dedup). Per-frame schema:

  {t, frame,
   persons: [{appearance, clothing:{top,bottom,colors:[...]},
              accessories:[...], holding:[...], position}],
   text_objects: [{object, logo_or_text}],
   is_self_view: bool,
   self_attributes: {...},          # wearer's own body/hands/worn items when is_self_view
   raw: "<model text>",             # kept for audit / re-parse
   parse_ok: bool}                  # False => degraded-but-valid empty record

The VLM call goes through an INJECTABLE caption_entities(image_path, vlm) so tests pass a STUB
vlm (a function image_path -> canned model text). The real vlm is a (model, processor) closure
built by load_entity_vlm(); we never load it in tests.

This file does NOT call ollama and its --selftest is CPU-only (no model load).

  Benchmark on the real GPU (Chief runs this, NOT the agent):
      .venv/bin/python scripts/build_entity_capture.py \
          --frames-dir data/walks/day_in_life_20260618/work/run_frames \
          --out data/walks/day_in_life_20260618/memory/entity_capture.json --limit 2
  CPU self-test (safe, no model):
      .venv/bin/python scripts/build_entity_capture.py --selftest
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import re
import sys
import time

MODEL = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"

# Entity-centric prompt. We DEMAND JSON-only and spell out the exact schema so the parser has a
# stable target. The key instruction is "one record per person, attributes attached to THAT
# person" + "a logo belongs to the object it is printed on" — that is what kills mis-attribution.
ENTITY_PROMPT = (
    "Look at this image and extract every DISTINCT person and every object that has text/a logo. "
    "Return ONLY a JSON object, no prose, no markdown fences. Use exactly this shape:\n"
    "{\n"
    '  "persons": [\n'
    "    {\n"
    '      "appearance": "<short distinguishing description: build, hair, age cues>",\n'
    '      "clothing": {"top": "<garment>", "bottom": "<garment>", "colors": ["<color>", ...]},\n'
    '      "accessories": ["<hat, bag, glasses, watch, ...>"],\n'
    '      "holding": ["<things in this person\'s hands>"],\n'
    '      "position": "left" | "center" | "right"\n'
    "    }\n"
    "  ],\n"
    '  "text_objects": [\n'
    '    {"object": "<the thing the text is ON: backpack, shirt, sign, screen>", '
    '"logo_or_text": "<the visible text/brand>"}\n'
    "  ],\n"
    '  "is_self_view": true | false,\n'
    '  "self_attributes": {"holding": ["..."], "clothing": ["..."], "body": ["hands", ...]}\n'
    "}\n"
    "RULES: (1) Emit ONE record per person; attach each garment/accessory/held item to the "
    "person it actually belongs to — never merge two people. (2) A logo or word belongs to the "
    "SINGLE object it is printed on (a 'North Face' backpack is text_objects, NOT a person's "
    "clothing). (3) is_self_view is true ONLY when the camera-wearer's OWN hands/body/lap are "
    "visible (first-person); put the wearer's own items in self_attributes, NOT in persons. "
    "(4) If you are unsure of a value, omit the field rather than guess. (5) Empty arrays are fine."
)

# Fields we guarantee exist on every emitted record (degrade-safe contract for downstream re-ID).
_PERSON_KEYS = ("appearance", "clothing", "accessories", "holding", "position")


# --------------------------------------------------------------------------- frame helpers
# (mirrors build_keyframe_memory.py)
def time_of(path: str) -> float:
    m = re.search(r"_(\d+\.\d+)s", os.path.basename(path or ""))
    return float(m.group(1)) if m else 0.0


def downscale(path, max_dim=1280):
    """Resize once to a temp file (4K is slow and leaks detail the model invents)."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = min(1.0, max_dim / max(w, h))
    if s < 1.0:
        im = im.resize((int(w * s), int(h * s)))
    tmp = "/tmp/_ec_%d.jpg" % (abs(hash(path)) % 10_000_000)
    im.save(tmp, quality=90)
    return tmp


# --------------------------------------------------------------------------- model load
# Mirror build_keyframe_memory.py: the transformers-4.49 slow-image-processor fix is REQUIRED
# (mlx-vlm can't feed the fast Qwen2-VL processor -> "Only PyTorch tensors supported").
def load_entity_vlm():
    """Return an injectable vlm: a function image_path -> raw model text (JSON string).

    Building the closure here keeps the heavy mlx import out of import-time and lets the runner
    pass `vlm` straight into caption_entities(). Tests pass a STUB instead and never call this.
    """
    from mlx_vlm import load
    from transformers import AutoImageProcessor
    model, processor = load(MODEL)
    processor.image_processor = AutoImageProcessor.from_pretrained(MODEL, use_fast=False)

    cfg = {"v": None}

    def vlm(image_path, max_tokens=512):
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template
        from mlx_vlm.utils import load_config
        if cfg["v"] is None:
            cfg["v"] = load_config(MODEL)
        prompt = apply_chat_template(processor, cfg["v"], ENTITY_PROMPT, num_images=1)
        try:
            out = generate(model, processor, prompt, [image_path], max_tokens=max_tokens,
                           temperature=0.0, verbose=False)
        except TypeError:
            out = generate(model, processor, prompt, image=[image_path], max_tokens=max_tokens,
                           verbose=False)
        return (out.text if hasattr(out, "text") else str(out)).strip()

    return vlm


# --------------------------------------------------------------------------- parsing
def _extract_json_blob(text: str):
    """Pull the first balanced top-level {...} out of arbitrary model text.

    Handles ```json fences, leading prose, and trailing commentary. Brace-counts while skipping
    string contents so braces inside values don't end the object early. Returns a dict or None.
    """
    if not text:
        return None
    s = text.strip()
    # strip a leading ```json / ``` fence if present
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                blob = s[start:i + 1]
                try:
                    return json.loads(blob)
                except Exception:
                    # last-ditch: drop trailing commas, retry
                    try:
                        return json.loads(re.sub(r",\s*([}\]])", r"\1", blob))
                    except Exception:
                        return None
    return None


def _as_list(x):
    """Coerce to a list of non-empty strings. Accepts list, scalar, or comma string."""
    if x is None:
        return []
    if isinstance(x, list):
        return [str(v).strip() for v in x if str(v).strip()]
    if isinstance(x, str):
        return [p.strip() for p in re.split(r"\s*,\s*", x) if p.strip()]
    return [str(x).strip()] if str(x).strip() else []


def _norm_position(x):
    s = (str(x or "")).strip().lower()
    for p in ("left", "center", "centre", "right"):
        if p in s:
            return "center" if p == "centre" else p
    return ""


def _norm_person(p):
    """Normalize one person dict into the guaranteed self-contained schema."""
    if not isinstance(p, dict):
        return None
    clo = p.get("clothing") if isinstance(p.get("clothing"), dict) else {}
    clothing = {
        "top": str(clo.get("top", "")).strip(),
        "bottom": str(clo.get("bottom", "")).strip(),
        "colors": _as_list(clo.get("colors") or clo.get("color")),
    }
    person = {
        "appearance": str(p.get("appearance", "")).strip(),
        "clothing": clothing,
        "accessories": _as_list(p.get("accessories")),
        "holding": _as_list(p.get("holding")),
        "position": _norm_position(p.get("position")),
    }
    # drop a record that carries no signal at all (all-empty hallucination filler)
    if (not person["appearance"] and not clothing["top"] and not clothing["bottom"]
            and not clothing["colors"] and not person["accessories"]
            and not person["holding"]):
        return None
    return person


def _norm_text_object(o):
    if not isinstance(o, dict):
        return None
    obj = str(o.get("object", "")).strip()
    txt = str(o.get("logo_or_text", o.get("text", ""))).strip()
    if not txt:
        return None
    return {"object": obj, "logo_or_text": txt}


def _empty_record():
    return {
        "persons": [],
        "text_objects": [],
        "is_self_view": False,
        "self_attributes": {},
    }


def parse_entities(raw_text: str) -> dict:
    """Parse model text -> validated entity record. NEVER raises; degrades to an empty record.

    Returns a dict with parse_ok flag. A malformed/empty model reply yields a valid empty record
    (parse_ok=False) so the pipeline keeps moving and downstream sees a well-typed row.
    """
    rec = _empty_record()
    rec["parse_ok"] = False
    data = _extract_json_blob(raw_text)
    if not isinstance(data, dict):
        return rec

    persons = []
    for p in (data.get("persons") or []):
        np = _norm_person(p)
        if np:
            persons.append(np)
    rec["persons"] = persons

    tobjs = []
    for o in (data.get("text_objects") or []):
        no = _norm_text_object(o)
        if no:
            tobjs.append(no)
    rec["text_objects"] = tobjs

    rec["is_self_view"] = bool(data.get("is_self_view", False))
    sa = data.get("self_attributes")
    if isinstance(sa, dict):
        rec["self_attributes"] = {
            "holding": _as_list(sa.get("holding")),
            "clothing": _as_list(sa.get("clothing")),
            "body": _as_list(sa.get("body")),
        }
    elif sa:  # model returned a list/string of self cues
        rec["self_attributes"] = {"body": _as_list(sa)}
    else:
        rec["self_attributes"] = {}

    rec["parse_ok"] = True
    return rec


# --------------------------------------------------------------------------- capture (injectable)
def caption_entities(image_path, vlm) -> dict:
    """ONE structured extraction for ONE keyframe via the injectable `vlm`.

    `vlm` is image_path -> raw model text (a JSON string in the happy path). In production it is
    load_entity_vlm()'s closure; in tests it is a stub returning canned text. We keep the raw text
    on the record for audit and never let a bad reply crash the run.
    """
    try:
        raw = vlm(image_path)
    except Exception as e:  # a model/decoding failure must not kill the whole pass
        rec = _empty_record()
        rec["parse_ok"] = False
        rec["raw"] = ""
        rec["error"] = str(e)
        return rec
    rec = parse_entities(raw)
    rec["raw"] = raw if isinstance(raw, str) else str(raw)
    return rec


# --------------------------------------------------------------------------- runner
def run(frames_dir, out, dedup_thresh, cap, limit, vlm):
    """Glob -> dedup keyframes -> per-frame structured capture, NDJSON-checkpointed."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from describe_walk import pick_keyframes
    from post_capture_identity import checkpoint_rows, job_run_id
    frames = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")), key=time_of)
    keys = pick_keyframes(frames, dedup_thresh, cap)
    if limit:
        keys = keys[:limit]
    print(f"{len(frames)} frames -> {len(keys)} distinct keyframes", file=sys.stderr, flush=True)

    memory_dir = os.path.dirname(os.path.abspath(out))
    run_id = job_run_id(
        memory_dir, "entity_capture", 2, MODEL, ENTITY_PROMPT,
        {"dedup_thresh": dedup_thresh, "cap": cap, "limit": limit}, keys)

    ckpt = out + ".ckpt.ndjson"
    done = checkpoint_rows(ckpt, run_id)
    if os.path.exists(ckpt):
        print(f"resume: {len(done)} done", file=sys.stderr, flush=True)

    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    fh = open(ckpt, "a")
    memory, times = [], []
    for i, f in enumerate(keys, 1):
        if f in done:
            memory.append(done[f])
            continue
        try:
            small = downscale(f)
            t0 = time.time()
            rec = caption_entities(small, vlm)
            times.append(time.time() - t0)
            os.remove(small)
        except Exception as e:
            print(f"  err {f}: {e}", file=sys.stderr, flush=True)
            continue
        rec["t"] = time_of(f)
        rec["frame"] = f
        rec["_run_id"] = run_id
        memory.append(rec)
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        np = len(rec.get("persons", []))
        nto = len(rec.get("text_objects", []))
        print(f"[{i}/{len(keys)}] {time_of(f):.1f}s  {times[-1]:.1f}s  "
              f"persons={np} text_objs={nto} self={rec.get('is_self_view')} "
              f"ok={rec.get('parse_ok')}", file=sys.stderr, flush=True)
    fh.close()
    memory.sort(key=lambda r: r.get("t", 0.0))
    json.dump(memory, open(out, "w"), indent=2, ensure_ascii=False)
    if times:
        print(f"\nBENCHMARK entity capture avg {sum(times)/len(times):.1f}s/frame",
              file=sys.stderr)
    print(f"WROTE {len(memory)} entity-capture records to {out}")
    return 0


# --------------------------------------------------------------------------- CPU self-test
def _selftest() -> int:
    """CPU-only: feed the parser canned model output (good + malformed) via a STUB vlm.

    Asserts the happy path binds attributes to the right person/object, and that every malformed
    case degrades to a valid, well-typed record without raising. No model is loaded.
    """
    fails = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    # ---- 1. happy path: two distinct people + a logo bound to a backpack, JSON-only ----
    good = json.dumps({
        "persons": [
            {"appearance": "guy with short hair",
             "clothing": {"top": "green tee", "bottom": "black shorts", "colors": ["green", "black"]},
             "accessories": ["watch"], "holding": ["phone"], "position": "left"},
            {"appearance": "woman",
             "clothing": {"top": "pink shirt that reads Breakfast Club", "bottom": "jeans",
                          "colors": ["pink"]},
             "accessories": [], "holding": [], "position": "right"},
        ],
        "text_objects": [{"object": "backpack", "logo_or_text": "North Face"}],
        "is_self_view": False,
        "self_attributes": {},
    })
    r = caption_entities("img_a", lambda p: good)
    check("good.parse_ok", r["parse_ok"] is True)
    check("good.two_persons", len(r["persons"]) == 2)
    p0, p1 = r["persons"]
    check("good.person0_green_black", p0["clothing"]["top"] == "green tee"
          and p0["clothing"]["bottom"] == "black shorts")
    check("good.person1_pink_not_mixed", "pink" in p1["clothing"]["colors"]
          and "green" not in p1["clothing"]["colors"])
    check("good.attrs_not_crossed", "watch" in p0["accessories"] and not p1["accessories"])
    check("good.logo_bound_to_backpack",
          r["text_objects"] == [{"object": "backpack", "logo_or_text": "North Face"}])
    check("good.raw_kept", r["raw"] == good)

    # ---- 2. JSON wrapped in a ```json fence + leading prose (very common model behavior) ----
    fenced = ("Here is the JSON:\n```json\n"
              + json.dumps({"persons": [{"appearance": "kid", "position": "center"}],
                            "text_objects": [], "is_self_view": True,
                            "self_attributes": {"body": ["hands"], "holding": ["mug"]}})
              + "\n```\nLet me know if you need more.")
    r = caption_entities("img_b", lambda p: fenced)
    check("fenced.parse_ok", r["parse_ok"] is True)
    check("fenced.person_kept", len(r["persons"]) == 1 and r["persons"][0]["position"] == "center")
    check("fenced.self_view", r["is_self_view"] is True)
    check("fenced.self_attrs", r["self_attributes"].get("body") == ["hands"]
          and r["self_attributes"].get("holding") == ["mug"])

    # ---- 3. schema looseness: colors as a comma-string, holding as a scalar, missing fields ----
    loose = json.dumps({
        "persons": [{"appearance": "runner",
                     "clothing": {"top": "jacket", "colors": "red, white"},
                     "holding": "water bottle"}],
        "text_objects": [{"object": "sign", "text": "EXIT"}],  # 'text' alias instead of logo_or_text
    })
    r = caption_entities("img_c", lambda p: loose)
    check("loose.parse_ok", r["parse_ok"] is True)
    check("loose.colors_split", r["persons"][0]["clothing"]["colors"] == ["red", "white"])
    check("loose.holding_listified", r["persons"][0]["holding"] == ["water bottle"])
    check("loose.bottom_defaulted", r["persons"][0]["clothing"]["bottom"] == "")
    check("loose.text_alias", r["text_objects"] == [{"object": "sign", "logo_or_text": "EXIT"}])
    check("loose.position_blank_ok", r["persons"][0]["position"] == "")

    # ---- 4. malformed: not JSON at all -> degrade to valid empty record, no raise ----
    r = caption_entities("img_d", lambda p: "I cannot read this blurry image, sorry.")
    check("garbage.no_raise_valid", isinstance(r, dict))
    check("garbage.parse_ok_false", r["parse_ok"] is False)
    check("garbage.empty_persons", r["persons"] == [] and r["text_objects"] == [])
    check("garbage.self_view_false", r["is_self_view"] is False)

    # ---- 5. malformed: truncated / broken JSON (unbalanced braces) -> empty, no raise ----
    r = caption_entities("img_e", lambda p: '{"persons": [{"appearance": "man", "clothing": {')
    check("truncated.parse_ok_false", r["parse_ok"] is False)
    check("truncated.empty", r["persons"] == [])

    # ---- 6. empty / null replies ----
    for nm, val in (("emptystr", ""), ("none", None)):
        r = caption_entities("img_f", lambda p, v=val: v)
        check(f"{nm}.no_raise", isinstance(r, dict) and r["parse_ok"] is False)

    # ---- 7. all-empty filler person is dropped (anti-hallucination), trailing comma tolerated ----
    filler = ('{"persons": [{"appearance": "", "clothing": {"top":"","bottom":"","colors":[]}, '
              '"accessories": [], "holding": []},'
              '{"appearance":"real guy","position":"left"},],'  # trailing comma + a real one
              ' "text_objects": [], "is_self_view": false}')
    r = caption_entities("img_g", lambda p: filler)
    check("filler.dropped_empty_kept_real",
          len(r["persons"]) == 1 and r["persons"][0]["appearance"] == "real guy")

    # ---- 8. vlm itself raises -> caught, valid record with error ----
    def boom(p):
        raise RuntimeError("model decode failed")
    r = caption_entities("img_h", boom)
    check("vlm_raise.caught", r["parse_ok"] is False and r.get("error") == "model decode failed")

    # ---- 9. parser is total: never raises across a fuzz of junk inputs ----
    junk = ["{", "}", "[]", "{]", '{"persons": "not a list"}', '{"persons": [42, null, "x"]}',
            "null", "true", "12345", "{}", '{"is_self_view": "yes"}']
    ok = True
    for j in junk:
        try:
            rr = parse_entities(j)
            ok = ok and isinstance(rr, dict) and "persons" in rr
        except Exception:
            ok = False
    check("fuzz.total_no_raise", ok)
    # 'yes' string self_view coerces truthy bool, not a crash
    check("fuzz.self_view_coerced", parse_entities('{"is_self_view": "yes"}')["is_self_view"] is True)

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 0 if not fails else 1


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="Entity-centric structured capture per keyframe.")
    ap.add_argument("--frames-dir",
                    default="data/walks/day_in_life_20260618/work/run_frames")
    ap.add_argument("--out",
                    default="data/walks/day_in_life_20260618/memory/entity_capture.json")
    ap.add_argument("--dedup-thresh", type=float, default=14.0)
    ap.add_argument("--cap", type=int, default=120)
    ap.add_argument("--limit", type=int, default=0, help="benchmark: only N keyframes")
    ap.add_argument("--selftest", action="store_true",
                    help="CPU-only parser test with a stub vlm (no model load)")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    print("loading Qwen2.5-VL (entity-centric)...", file=sys.stderr, flush=True)
    vlm = load_entity_vlm()
    return run(args.frames_dir, args.out, args.dedup_thresh, args.cap, args.limit, vlm)


if __name__ == "__main__":
    sys.exit(main())
