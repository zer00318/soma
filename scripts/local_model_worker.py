#!/usr/bin/env python3
"""Run tightly bounded local-worker tasks against an LM Studio OpenAI-style server.

This script is intentionally conservative. It is meant to offload low-risk drafting,
review, and summarization work to a local model while leaving architecture,
integration, and final judgment to the lead agent.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable


SYSTEM_PROMPTS = {
    "scout": textwrap.dedent(
        """
        You are a local scout model working inside the SOMA product monorepo.
        Your job is to inspect bounded context and return concise, grounded notes.

        Rules:
        - Stay inside the provided task and files.
        - Do not invent code, files, runtime behavior, or test results.
        - Call out uncertainty plainly.
        - Prefer bullets over long prose.
        - Focus on concrete facts, risks, missing pieces, and likely next edits.
        """
    ).strip(),
    "implement": textwrap.dedent(
        """
        You are a local implementation worker for the SOMA monorepo.
        You are drafting bounded changes for a lead engineer who will review
        and integrate the result.

        Rules:
        - Only work on the requested scope.
        - Prefer small edits over broad rewrites.
        - Preserve the existing architecture and style.
        - Do not claim something was tested unless it is explicitly provided.
        - Output:
          1. Short plan
          2. Proposed code or patch blocks
          3. Risks / open questions
        """
    ).strip(),
    "critic": textwrap.dedent(
        """
        You are a local review worker for the SOMA monorepo.
        Review the provided material like a careful product engineer.

        Rules:
        - Prioritize bugs, regressions, missing tests, and incorrect assumptions.
        - Be specific and grounded in the supplied text.
        - If something looks fine, say so briefly and move on.
        - Output findings first, then residual risks, then a very short summary.
        """
    ).strip(),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a bounded task to a local LM Studio model."
    )
    parser.add_argument(
        "--mode",
        choices=sorted(SYSTEM_PROMPTS),
        default="scout",
        help="Worker mode / prompt preset.",
    )
    parser.add_argument(
        "--task",
        help="Task text to send to the local worker.",
    )
    parser.add_argument(
        "--task-file",
        type=Path,
        help="Path to a file containing the task text.",
    )
    parser.add_argument(
        "--context-file",
        action="append",
        default=[],
        type=Path,
        help="Attach a file as bounded context. May be passed multiple times.",
    )
    parser.add_argument(
        "--context-text",
        action="append",
        default=[],
        help="Attach an extra block of context text. May be passed multiple times.",
    )
    parser.add_argument(
        "--server",
        default="http://127.0.0.1:1234",
        help="Base URL for the LM Studio OpenAI-compatible server.",
    )
    parser.add_argument(
        "--model",
        help="Optional explicit model id. If omitted, the first loaded model is used.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1200,
        help="Max output tokens.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout in seconds for local model requests.",
    )
    parser.add_argument(
        "--show-payload",
        action="store_true",
        help="Print the final request payload instead of sending it.",
    )
    return parser.parse_args()


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def load_task(args: argparse.Namespace) -> str:
    sources = []
    if args.task:
        sources.append(args.task.strip())
    if args.task_file:
        sources.append(read_text_file(args.task_file).strip())
    task = "\n\n".join(part for part in sources if part)
    if not task:
        raise SystemExit("Provide --task or --task-file.")
    return task


def render_context_blocks(paths: Iterable[Path], snippets: Iterable[str]) -> str:
    blocks = []
    for path in paths:
        body = read_text_file(path)
        blocks.append(
            f"FILE: {path}\n```text\n{body.rstrip()}\n```"
        )
    for idx, snippet in enumerate(snippets, start=1):
        blocks.append(f"CONTEXT {idx}\n```text\n{snippet.rstrip()}\n```")
    return "\n\n".join(blocks)


def http_json(url: str, payload: dict | None = None, timeout: int = 60) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def detect_model(server: str) -> str:
    payload = http_json(f"{server.rstrip('/')}/v1/models")
    models = payload.get("data") or []
    if not models:
        raise RuntimeError(
            "LM Studio server responded, but no models are loaded. Load a model in LM Studio first."
        )
    return models[0]["id"]


def build_messages(mode: str, task: str, context: str) -> list[dict[str, str]]:
    user_parts = [f"TASK\n{task.strip()}"]
    if context.strip():
        user_parts.append(f"BOUNDED CONTEXT\n{context.strip()}")
    user_parts.append(
        textwrap.dedent(
            """
            RESPONSE RULES
            - Ground everything in the supplied task/context.
            - Do not assume hidden files or tools.
            - If context is missing, say exactly what is missing.
            """
        ).strip()
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPTS[mode]},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


def main() -> int:
    args = parse_args()
    task = load_task(args)
    context = render_context_blocks(args.context_file, args.context_text)

    if args.show_payload:
        model = args.model or "lm-studio-loaded-model"
    else:
        try:
            model = args.model or detect_model(args.server)
        except urllib.error.URLError:
            print(
                "Could not reach LM Studio at "
                f"{args.server}. Start LM Studio, load a model, and enable the local server.",
                file=sys.stderr,
            )
            return 2
        except Exception as exc:  # pragma: no cover - defensive cli path
            print(str(exc), file=sys.stderr)
            return 2

    payload = {
        "model": model,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "messages": build_messages(args.mode, task, context),
    }

    if args.show_payload:
        print(json.dumps(payload, indent=2))
        return 0

    try:
        response = http_json(
            f"{args.server.rstrip('/')}/v1/chat/completions",
            payload,
            timeout=args.timeout,
        )
    except urllib.error.HTTPError as exc:
        print(f"LM Studio request failed: HTTP {exc.code}", file=sys.stderr)
        try:
            print(exc.read().decode("utf-8"), file=sys.stderr)
        except Exception:
            pass
        return 3
    except urllib.error.URLError:
        print(
            "LM Studio server became unreachable while sending the request.",
            file=sys.stderr,
        )
        return 3
    except TimeoutError:
        print(f"LM Studio request timed out after {args.timeout}s.", file=sys.stderr)
        return 3

    choices = response.get("choices") or []
    if not choices:
        print("LM Studio returned no choices.", file=sys.stderr)
        return 4

    content = choices[0].get("message", {}).get("content", "").strip()
    if not content:
        print("LM Studio returned an empty response.", file=sys.stderr)
        return 4

    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
