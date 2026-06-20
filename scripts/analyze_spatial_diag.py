from __future__ import annotations
import json
import argparse
import math
import statistics
import collections
import sys
import tempfile
import os

def load_lines(path: str) -> tuple[list[dict], int]:
    parsed_rows = []
    bad_line_count = 0
    with open(path, 'r') as f:
        for line in f:
            try:
                row = json.loads(line)
                parsed_rows.append(row)
            except json.JSONDecodeError:
                bad_line_count += 1
    return parsed_rows, bad_line_count

def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    by_decision = collections.defaultdict(int)
    by_word = collections.defaultdict(lambda: {
        'count': 0,
        'decisions': collections.defaultdict(int),
        'score_min': float('inf'),
        'score_max': -float('inf'),
        'score_total': 0.0,
        'score_mean': 0.0,
    })
    scores = []
    ms_values = []
    dist_to_nearest_same_words = []
    positions_by_word = collections.defaultdict(list)

    for row in rows:
        by_decision[row['decision']] += 1
        word_info = by_word[row['word']]
        word_info['count'] += 1
        word_info['decisions'][row['decision']] += 1
        word_info['score_min'] = min(word_info['score_min'], row['score'])
        word_info['score_max'] = max(word_info['score_max'], row['score'])
        word_info['score_total'] += row['score']
        scores.append(row['score'])
        ms_values.append(row['ms'])
        if 'dist_to_nearest_same_word' in row:
            dist_to_nearest_same_words.append(row['dist_to_nearest_same_word'])
        pos = row.get('pos')
        if isinstance(pos, list) and len(pos) >= 3:
            try:
                positions_by_word[row['word']].append(tuple(float(pos[idx]) for idx in range(3)))
            except (TypeError, ValueError):
                pass

    for word_info in by_word.values():
        if word_info['count']:
            word_info['score_mean'] = round(word_info['score_total'] / word_info['count'], 3)

    score_histogram = {
        "<0.20": sum(1 for s in scores if s < 0.20),
        "0.20-0.25": sum(1 for s in scores if 0.20 <= s < 0.25),
        "0.25-0.30": sum(1 for s in scores if 0.25 <= s < 0.30),
        "0.30-0.40": sum(1 for s in scores if 0.30 <= s < 0.40),
        ">=0.40": sum(1 for s in scores if s >= 0.40)
    }

    ms_p50 = round(statistics.median(ms_values), 3) if ms_values else None
    ms_p95_index = int(0.95 * (len(ms_values) - 1))
    ms_p95 = round(sorted(ms_values)[ms_p95_index], 3) if ms_values and len(ms_values) > 1 else None

    dup_distances = {
        "count": len(dist_to_nearest_same_words),
        "min": round(min(dist_to_nearest_same_words), 3) if dist_to_nearest_same_words else None,
        "p50": round(statistics.median(dist_to_nearest_same_words), 3) if dist_to_nearest_same_words else None,
        "max": round(max(dist_to_nearest_same_words), 3) if dist_to_nearest_same_words else None
    }

    words_per_minute = collections.defaultdict(int)
    for row in rows:
        minute = row['ts'][:16]  # YYYY-MM-DDTHH:MM
        words_per_minute[minute] += 1

    words_per_minute_peak = max(words_per_minute.values()) if words_per_minute else 0

    position_spread_by_word = {}
    for word, positions in positions_by_word.items():
        if len(positions) < 2 or word.startswith("__"):
            continue
        centroid = tuple(sum(p[idx] for p in positions) / len(positions) for idx in range(3))
        distances = [
            math.sqrt(sum((p[idx] - centroid[idx]) ** 2 for idx in range(3)))
            for p in positions
        ]
        max_pairwise = 0.0
        for i, a in enumerate(positions):
            for b in positions[i + 1:]:
                max_pairwise = max(
                    max_pairwise,
                    math.sqrt(sum((a[idx] - b[idx]) ** 2 for idx in range(3)))
                )
        position_spread_by_word[word] = {
            "count": len(positions),
            "rms_from_centroid_m": round(math.sqrt(sum(d * d for d in distances) / len(distances)), 3),
            "max_from_centroid_m": round(max(distances), 3),
            "max_pairwise_m": round(max_pairwise, 3),
        }

    spread_over_1m = {
        word: info
        for word, info in position_spread_by_word.items()
        if info["max_pairwise_m"] > 1.0 or info["max_from_centroid_m"] > 1.0
    }

    return {
        "total": total,
        "by_decision": dict(by_decision),
        "by_word": {
            word: {
                k: round(v, 3) if isinstance(v, float) else v
                for k, v in info.items()
                if k != "score_total"
            }
            for word, info in by_word.items()
        },
        "score_histogram": score_histogram,
        "ms_p50": ms_p50,
        "ms_p95": ms_p95,
        "dup_distances": dup_distances,
        "words_per_minute_peak": words_per_minute_peak,
        "position_spread_by_word": position_spread_by_word,
        "position_spread_over_1m": spread_over_1m,
    }

def render(summary: dict) -> str:
    report = f"Total lines: {summary['total']}\n\n"
    report += "Decision table:\n"
    for decision, count in sorted(summary['by_decision'].items(), key=lambda item: item[1], reverse=True):
        report += f"{decision}: {count}\n"
    report += "\nTop 15 words by count with their decision mix and score range:\n"
    top_words = sorted(summary['by_word'].items(), key=lambda item: item[1]['count'], reverse=True)[:15]
    for word, info in top_words:
        report += f"{word}: {info['count']} (decisions: {', '.join(f'{d}:{c}' for d, c in info['decisions'].items())}, score range: {info['score_min']}-{info['score_max']})\n"
    report += "\nScore histogram:\n"
    for bin, count in summary['score_histogram'].items():
        report += f"{bin}: {count}\n"
    report += f"\nms p50: {summary['ms_p50']}, ms p95: {summary['ms_p95']}\n\n"
    report += "Dup-distance stats:\n"
    for key, value in summary['dup_distances'].items():
        report += f"{key}: {value}\n"
    report += f"\nPeak words/min: {summary['words_per_minute_peak']}\n"
    report += "\nPosition spread by word (top 15 by max pairwise meters):\n"
    spreads = sorted(
        summary.get('position_spread_by_word', {}).items(),
        key=lambda item: item[1]['max_pairwise_m'],
        reverse=True,
    )[:15]
    if spreads:
        for word, info in spreads:
            flag = " RAISE_PROMOTE_THRESHOLD" if word in summary.get('position_spread_over_1m', {}) else ""
            report += (
                f"{word}: n={info['count']} rms={info['rms_from_centroid_m']}m "
                f"max_centroid={info['max_from_centroid_m']}m max_pairwise={info['max_pairwise_m']}m{flag}\n"
            )
    else:
        report += "none\n"
    return report

def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze spatial diagnostics from NDJSON.")
    parser.add_argument("path", nargs='?', default="/tmp/spatial_pull/spatial_diag.ndjson", help="Path to the NDJSON file")
    parser.add_argument("--json", action="store_true", help="Print the summary as JSON instead of text")
    parser.add_argument("--self-test", action="store_true", help="Run self-test and exit")
    args = parser.parse_args()

    if args.self_test:
        with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8') as temp_file:
            test_data = [
                '{"ts":"2026-06-12T08:00:01Z","word":"bottle","score":0.31,"ms":42,"decision":"pending"}\n',
                '{"ts":"2026-06-12T08:00:05Z","word":"bottle","score":0.33,"ms":40,"decision":"pending_promote","pos":[0.1,-1.2,-0.8],"sightings":2}\n',
                '{"ts":"2026-06-12T08:00:09Z","word":"bottle","score":0.35,"ms":38,"decision":"permanent_merge","dist_to_nearest_same_word":0.21,"pos":[0.4,-1.1,-0.7]}\n',
                '{"ts":"2026-06-12T08:01:02Z","word":"keyboard","score":0.24,"ms":55,"decision":"pending"}\n',
                '{"ts":"2026-06-12T08:01:30Z","word":"keyboard","score":0.19,"ms":61,"decision":"rejected","reason":"below_floor"}\n',
                'not json at all\n',
                '{"ts":"2026-06-12T08:02:00Z","word":"monitor","score":0.41,"ms":47,"decision":"pending"}\n'
            ]
            temp_file.writelines(test_data)
        rows, bad_line_count = load_lines(temp_file.name)
        assert bad_line_count == 1
        assert len(rows) == 6
        summary = summarize(rows)
        assert summary["by_decision"]['pending'] == 3
        assert summary["by_word"]['bottle']['count'] == 3
        assert summary["score_histogram"]['<0.20'] == 1
        assert summary["score_histogram"]['>=0.40'] == 1
        assert 40 <= summary["ms_p50"] <= 55
        assert summary["dup_distances"]['count'] == 1
        assert summary["words_per_minute_peak"] == 3
        assert summary["position_spread_by_word"]["bottle"]["count"] == 2
        assert summary["position_spread_by_word"]["bottle"]["max_pairwise_m"] > 0
        assert 'bottle' in render(summary)
        assert 'pending' in render(summary)
        print("SELF-TEST PASS")
        os.unlink(temp_file.name)
        sys.exit(0)

    rows, bad_line_count = load_lines(args.path)
    summary = summarize(rows)
    if args.json:
        print(json.dumps(summary, indent=4))
    else:
        print(render(summary))

if __name__ == "__main__":
    main()
