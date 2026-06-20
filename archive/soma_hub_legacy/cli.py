from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from soma_hub.api import run_server
from soma_hub.evaluation import run_default_evaluation
from soma_hub.graph_audit import GraphAuditor, audit_to_dict
from soma_hub.live_audio import LiveAudioBridge, macos_live_transcript_command, selected_audio_engine
from soma_hub.platform_audio import audio_engine_profiles, live_audio_status
from soma_hub.service import SomaHub
from soma_hub.stream_ingest import TranscriptStreamIngestor


def main() -> None:
    parser = argparse.ArgumentParser(description="SOMA local hub")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run local hub API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--data-dir", default="data")
    serve.add_argument("--token", default="dev-token")

    ingest = sub.add_parser("ingest", help="Ingest extracted text")
    ingest.add_argument("text")
    ingest.add_argument("--data-dir", default="data")

    chat = sub.add_parser("chat", help="Ask the purpose-limited assistant")
    chat.add_argument("message")
    chat.add_argument("--data-dir", default="data")

    stream_stdin = sub.add_parser("stream-stdin", help="Ingest a continuous transcript stream from stdin")
    stream_stdin.add_argument("--data-dir", default="data")
    stream_stdin.add_argument("--provider", default="continuous_audio_transcript")

    tail_file = sub.add_parser("tail-file", help="Tail a transcript file and ingest new lines continuously")
    tail_file.add_argument("path")
    tail_file.add_argument("--data-dir", default="data")
    tail_file.add_argument("--provider", default="continuous_audio_transcript")
    tail_file.add_argument("--poll-interval", type=float, default=0.5)

    live_mic = sub.add_parser("live-mic", help="Run the macOS live microphone transcription bridge")
    live_mic.add_argument("--data-dir", default="data")
    live_mic.add_argument("--provider", default="continuous_audio_transcript")

    live_audio_auto = sub.add_parser("live-audio-auto", help="Auto-select and run the best available live audio engine")
    live_audio_auto.add_argument("--data-dir", default="data")
    live_audio_auto.add_argument("--provider", default="continuous_audio_transcript")

    evaluate = sub.add_parser("evaluate", help="Run the built-in SOMA evaluation harness")
    evaluate.add_argument("--data-dir", default="data")
    evaluate.add_argument("--dataset", default="")

    graph_audit = sub.add_parser("graph-audit", help="Audit the relational memory graph")
    graph_audit.add_argument("--data-dir", default="data")
    graph_audit.add_argument("--json", action="store_true")

    graph_profiles = sub.add_parser("graph-profiles", help="Print accumulated entity profiles")
    graph_profiles.add_argument("--data-dir", default="data")
    graph_profiles.add_argument("--label", default="")
    graph_profiles.add_argument("--json", action="store_true")

    live_mic_check = sub.add_parser("live-mic-check", help="Report whether the native live microphone bridge is available")
    audio_engines = sub.add_parser("audio-engines", help="List supported and fallback audio engines")

    args = parser.parse_args()
    if args.command == "serve":
        run_server(args.host, args.port, Path(args.data_dir), args.token)
    elif args.command == "ingest":
        hub = SomaHub(Path(args.data_dir))
        print(hub.ingest_text(args.text))
    elif args.command == "chat":
        hub = SomaHub(Path(args.data_dir))
        result = hub.chat(args.message)
        print(result.get("answer", result))
    elif args.command == "stream-stdin":
        hub = SomaHub(Path(args.data_dir))
        TranscriptStreamIngestor(hub, provider=args.provider).ingest_stream(sys.stdin)
    elif args.command == "tail-file":
        hub = SomaHub(Path(args.data_dir))
        TranscriptStreamIngestor(hub, provider=args.provider).tail_file(Path(args.path), poll_interval=args.poll_interval)
    elif args.command == "live-mic":
        hub = SomaHub(Path(args.data_dir))
        bridge = LiveAudioBridge(hub, provider=args.provider)
        root_dir = Path(__file__).resolve().parent.parent
        raise SystemExit(bridge.ingest_from_command(macos_live_transcript_command(root_dir), source_name="macos_live_asr"))
    elif args.command == "live-audio-auto":
        hub = SomaHub(Path(args.data_dir))
        bridge = LiveAudioBridge(hub, provider=args.provider)
        root_dir = Path(__file__).resolve().parent.parent
        engine = selected_audio_engine(root_dir, requested="auto")
        if engine["engine"] == "live-mic":
            raise SystemExit(bridge.ingest_from_command(list(engine["command"]), source_name="macos_live_asr"))
        if engine["engine"] == "stream-stdin":
            TranscriptStreamIngestor(hub, provider=args.provider).ingest_stream(sys.stdin, source_name="auto_stream_stdin")
        else:
            raise SystemExit(f"Auto mode selected unsupported engine: {engine['engine']}")
    elif args.command == "evaluate":
        dataset_path = Path(args.dataset) if args.dataset else None
        print(run_default_evaluation(dataset_path))
    elif args.command == "graph-audit":
        hub = SomaHub(Path(args.data_dir))
        graph = hub.graph_metadata()
        relations = hub.graph_relations()["relations"]
        result = GraphAuditor().audit(graph, relations)
        payload = audit_to_dict(result)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"SOMA graph audit: {result.grade} ({result.score}%)")
            print(f"Counts: {payload['counts']}")
            if result.strengths:
                print("Strengths:")
                for item in result.strengths:
                    print(f"- {item}")
            if result.issues:
                print("Issues:")
                for item in result.issues:
                    print(f"- {item}")
    elif args.command == "graph-profiles":
        hub = SomaHub(Path(args.data_dir))
        payload = hub.graph_profiles(label=args.label or None)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for profile in payload["profiles"]:
                print(f"{profile['label']} ({profile['kind']}, {profile['status']}, obs {profile['observation_count']})")
                for key, values in profile["slots"].items():
                    best = values[0]
                    print(f"  {key}: {best['value']} [{best['status']}, obs {best['observation_count']}]")
    elif args.command == "live-mic-check":
        root_dir = Path(__file__).resolve().parent.parent
        print(live_audio_status(root_dir))
    elif args.command == "audio-engines":
        root_dir = Path(__file__).resolve().parent.parent
        print(audio_engine_profiles(root_dir))


if __name__ == "__main__":
    main()
