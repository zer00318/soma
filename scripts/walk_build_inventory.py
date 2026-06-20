from __future__ import annotations
import argparse
import json
import os
import tempfile
import html
from collections import Counter


def _norm_trust(value) -> str:
    trust = str(value or "trusted").strip().lower()
    return "rejected" if trust == "rejected" else "trusted"


def _name_source(value) -> str:
    return str(value or "").strip() or "unknown"

def cluster(labels: list[dict], score_floor=0.22) -> dict:
    result = {}
    for label in labels:
        word = label.get('word') or label.get('label')
        try:
            score = float(label.get('score', label.get('confidence', 0.0)))
        except (TypeError, ValueError):
            score = 0.0
        crop_path = label.get('crop_path') or label.get('crop') or label.get('path') or label.get('file')
        if not word:
            continue
        if score < score_floor:
            continue
        trust = _norm_trust(label.get('trust'))
        name_source = _name_source(label.get('name_source'))
        if word not in result:
            result[word] = {
                'count': 0,
                'trusted_count': 0,
                'rejected_count': 0,
                'best': None,
                'examples': [],
                'score_max': -1.0,
                'score_mean': 0.0,
                'trust': trust,
                'name_source': name_source,
                'name_source_counts': {},
            }
        entry = result[word]
        entry['count'] += 1
        if trust == 'trusted':
            entry['trusted_count'] += 1
        else:
            entry['rejected_count'] += 1
        entry['score_mean'] += score
        entry['trust'] = 'trusted' if entry['trusted_count'] > 0 else 'rejected'
        counts = Counter(entry.get('name_source_counts') or {})
        counts[name_source] += 1
        entry['name_source_counts'] = dict(counts)
        if entry['trust'] == 'trusted':
            trusted_sources = {k: v for k, v in counts.items() if k != 'clip_only'}
            if trusted_sources:
                entry['name_source'] = max(trusted_sources.items(), key=lambda kv: kv[1])[0]
        else:
            entry['name_source'] = max(counts.items(), key=lambda kv: kv[1])[0]
        if score > entry['score_max']:
            entry['score_max'] = score
            entry['best'] = label
        if crop_path and len(entry['examples']) < 4:
            entry['examples'].append(crop_path)
    for word in result:
        entry = result[word]
        entry['score_mean'] /= entry['count']
    return result

def render_gallery(inventory, out_html, title):
    sorted_words = sorted(inventory.items(), key=lambda x: x[1]['count'], reverse=True)
    html_content = f'''<!DOCTYPE html>
<html>
<head>
  <title>{html.escape(title)}</title>
  <meta charset="utf-8">
  <style>
    body {{
      background-color: #121212;
      color: #e0e0e0;
      font-family: sans-serif;
      padding: 20px;
    }}
    .card {{
      background-color: #1e1e1e;
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
      display: flex;
      flex-direction: column;
    }}
    .word {{
      font-size: 24px;
      font-weight: bold;
      margin-bottom: 8px;
    }}
    .count {{
      font-size: 18px;
      margin-bottom: 8px;
    }}
    .score-max {{
      font-size: 16px;
      margin-bottom: 8px;
    }}
    .examples {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .example-img {{
      max-width: 160px;
      max-height: 160px;
    }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
'''
    for word, entry in sorted_words:
        html_content += f'''<div class="card">
  <div class="word">{html.escape(word)}</div>
  <div class="count">Count: {entry['count']}</div>
  <div class="score-max">Max Score: {entry['score_max']:.3f}</div>
  <div class="examples">
'''
        for example_path in entry['examples']:
            html_content += f'    <img src="{html.escape(example_path)}" class="example-img">\n'
        html_content += '''  </div>
</div>
'''
    html_content += '</body>\n</html>'
    with open(out_html, 'w') as f:
        f.write(html_content)

def render_summary(inventory) -> str:
    total_words = len(inventory)
    total_instances = sum(entry['count'] for entry in inventory.values())
    trusted_words = sum(1 for entry in inventory.values() if entry.get('trust', 'trusted') == 'trusted')
    rejected_words = sum(1 for entry in inventory.values() if entry.get('trust') == 'rejected')
    sorted_words = sorted(inventory.items(), key=lambda x: x[1]['count'], reverse=True)
    top_words = ', '.join(f"{word}({entry['count']})" for word, entry in sorted_words[:30])
    return f"""Total distinct words: {total_words}
Total instances: {total_instances}
Trusted distinct words: {trusted_words}
Rejected distinct words: {rejected_words}
Top 30 words: {top_words}"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--labels', default='/tmp/walk_labels.json')
    parser.add_argument('--out-html', default='/tmp/walk_inventory.html')
    parser.add_argument('--out-json', default='/tmp/walk_inventory.json')
    parser.add_argument('--score-floor', type=float, default=0.22)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()

    if args.self_test:
        labels = [
            {'word': 'mug', 'score': 0.3, 'crop': 'c1'},
            {'word': 'mug', 'score': 0.3, 'path': 'c2'},
            {'word': 'mug', 'score': 0.3, 'crop_path': 'c3'},
            {'word': 'mug', 'score': 0.3, 'crop_path': 'c4'},
            {'word': 'mug', 'score': 0.3, 'crop_path': 'c5'},
            {'word': 'desk', 'score': 0.4, 'crop_path': 'd1', 'trust': 'trusted', 'name_source': 'clip_agreed'},
            {'word': 'desk', 'score': 0.4, 'crop_path': 'd2'},
            {'word': 'bedpan', 'score': 0.4, 'crop_path': 'b1', 'trust': 'rejected', 'name_source': 'clip_only'},
            {'word': 'mug', 'score': 0.1, 'crop_path': 'c6'},
        ]
        inventory = cluster(labels, args.score_floor)
        assert inventory['mug']['count'] == 5
        assert inventory['desk']['count'] == 2
        assert inventory['desk']['trust'] == 'trusted'
        assert inventory['bedpan']['trust'] == 'rejected'
        assert inventory['bedpan']['rejected_count'] == 1
        assert inventory['mug']['examples'][:3] == ['c1', 'c2', 'c3']
        with tempfile.TemporaryDirectory() as tmpdir:
            test_html = os.path.join(tmpdir, 'test.html')
            render_gallery(inventory, test_html, 'Test Inventory')
            with open(test_html, 'r') as f:
                content = f.read()
                assert 'mug' in content
                assert 'desk' in content
        summary = render_summary(inventory)
        assert 'distinct' in summary
        print("SELF-TEST PASS")
        return

    with open(args.labels, 'r') as f:
        labels = json.load(f)
    inventory = cluster(labels, args.score_floor)
    with open(args.out_json, 'w') as f:
        json.dump(inventory, f, indent=2)
    render_gallery(inventory, args.out_html, 'Object Inventory')
    summary = render_summary(inventory)
    print(summary)

if __name__ == '__main__':
    main()
