# TRACE Native Live Test Report

Mode: full
Generated: 2026-06-04T22:54:00.936Z
Log: /Users/zer00/Library/Application Support/TRACE/trace_native_text.ndjson

## Gate Summary

- PASS: Runtime dependencies
- PASS: Visual memory
- PASS: Detector memory
- PASS: OCR sign/board memory
- PASS: Speech memory
- PASS: GPS/location hint
- PASS: Context snapshot
- PASS: Context digest
- PASS: No raw media

## Counts

- Log entries: 509
- Memory entries: 132
- Context snapshots: 176
- Context digests: 18
- Source counts: {"native_vision":102,"native_yolo_detector":29,"native_speech":1}
- Raw media files: 0

## OCR Evidence

- OCR memory records: 40
- Accepted OCR samples: none
- Rejected OCR samples: none

## Speech Evidence

- Speech memory records: 1
- EVENT | nearby speech | transcript: "Trace, test, Benson." | GPS 48.25588, 11.60994, accuracy ~35m | likely

## Detector Evidence

- Detector memory records: 29
- Recent detector statuses: Detector warming up; Detector ready; Detector frame submitted; Detector tracks: 1, events: 0; Detector tracks: 1, events: 1; Detector tracks: 3, events: 0; Detector tracks: 2, events: 0; Detector tracks: 2, events: 2

## Location And Context

- Recent location hints: GPS unavailable; GPS 48.25588, 11.60994, accuracy ~35m
- Latest context fact count: 60
- Latest digest active facts: 11
- Latest digest stable facts: 7
- Latest digest provisional facts: 4
- Latest digest stale-but-remembered facts: 8
- Stable digest examples:
  - OBJECT | headphones | image-level visual classification | visible scene; GPS 48.25588, 11.60994, accuracy ~35m | likely (seen 252x, age 0s)
  - OBJECT | eyeglasses | image-level visual classification | visible scene; GPS 48.25588, 11.60994, accuracy ~35m | likely (seen 258x, age 0s)
  - OBJECT | visible person | human figure detected | middle frame, center, overlapping/near visible person; GPS 48.25588, 11.60994, accuracy ~35m | likely (seen 247x, age 0s)
  - OBJECT | visible person | person tracked by local detector; mostly gray upper-body clothing | detector stream; GPS 48.25588, 11.60994, accuracy ~35m | likely | tracked for 10 detector frames (seen 25x, age 15s)
  - OBJECT | visible person | person detected by local tracker; mostly gray upper-body clothing | detector stream; GPS 48.25588, 11.60994, accuracy ~35m | likely (seen 5x, age 15s)

## Raw Media Audit

- PASS: no raw audio/video/image files found in TRACE storage.

