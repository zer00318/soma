# SOMA Native FastVLM

This is the native iOS/macOS direction for SOMA, forked from Apple `ml-fastvlm/app`.

Current state:

- Apple FastVLM camera + MLX app scaffold is present.
- FastVLM 0.5B native model is downloaded into `FastVLM/model`.
- The default prompt has been changed from visual Q&A to SOMA object/event memory.
- Continuous mode appends accepted `OBJECT | ...` and `EVENT | ...` records to an on-screen memory timeline.
- Raw camera frames are streamed in memory by `AVCaptureVideoDataOutput`; the app source does not write image/video files.

## Ontology

```text
OBJECT | visible entity or body/object attribute | concrete attributes | relation/location if visible | certainty
EVENT | object/person involved | action/change/state | relation/location if visible | certainty
```

## Build/Run Requirement

Full Xcode is required.

This machine currently has only Apple Command Line Tools:

```text
xcodebuild requires Xcode, but active developer directory is /Library/Developer/CommandLineTools
```

Once Xcode is installed:

1. Open `FastVLM.xcodeproj`.
2. Select the `FastVLM App` scheme.
3. Select either an iPhone/iPad target or `My Mac (Designed for iPad)` / macOS target if offered.
4. Build and run.
5. Grant camera permission.
6. Use continuous mode and test wearable POV object/event capture.

## What To Test

Use chest/head-height POV and perform simple object events:

- put an object on a desk
- pick it up
- move it next to another object
- show readable text
- walk past signs or room features

Expected output:

```text
OBJECT | black headphones | over-ear headphones | worn by visible person | likely
OBJECT | wall sign | text includes "Max-Planck-Campus" | above person | likely
EVENT | camera wearer/person | standing under transit sign | indoor station area | likely
```

Bad output:

- generic prose captions
- unsupported guesses
- categories outside `OBJECT` and `EVENT`
- no timestamped records after a stable frame

## Why This Exists

The browser WebGPU prototype proved camera access but stalled during or after inference on this Mac/browser combination. This native fork is the proper Apple Silicon path because Apple’s sample app runs FastVLM through MLX/Core ML rather than browser WebGPU.
