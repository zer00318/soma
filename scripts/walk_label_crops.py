from __future__ import annotations

import argparse
import os
import sys
import json
from typing import List, Callable, Tuple, Any

def load_vocab(path: str = 'ops/spatial_vocab.txt') -> List[str]:
    with open(path, 'r') as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip()]

def build_labeler(vocab: List[str], model_name: str = 'ViT-B-32', pretrained: str = 'laion2b_s34b_b79k') -> Callable[[List[Any]], List[Tuple[str, float]]]:
    import open_clip
    import torch
    from PIL import Image

    model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
    tokenizer = open_clip.get_tokenizer(model_name)
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    model = model.to(device)

    text_inputs = [f"a photo of a {w}" for w in vocab]
    with torch.no_grad():
        text_features = model.encode_text(tokenizer(text_inputs).to(device))
        text_features = text_features / text_features.norm(dim=-1, keepdim=True)
    
    def labeler(images: List[Any]) -> List[Tuple[str, float]]:
        tensors = []
        for img in images:
            if not isinstance(img, Image.Image):
                with Image.open(img) as opened:
                    img = opened.convert('RGB')
                    tensors.append(preprocess(img).unsqueeze(0))
            else:
                tensors.append(preprocess(img.convert('RGB')).unsqueeze(0))
        image_batch = torch.cat(tensors, dim=0).to(device)
        with torch.no_grad():
            image_features = model.encode_image(image_batch)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            similarities = (image_features @ text_features.T).cpu().numpy()
        results = []
        for sim in similarities:
            best_idx = sim.argmax()
            results.append((vocab[best_idx], float(sim[best_idx])))
        return results
    
    return labeler

def crop_path(crop: dict) -> str:
    return str(crop.get('path') or crop.get('crop_path') or crop.get('crop') or crop.get('file') or '')

def label_all(crops_manifest: List[dict], labeler: Callable[[List[Any]], List[Tuple[str, float]]], batch: int = 32, image_loader: Callable[[str], Any] = None, progress: bool = False) -> List[dict]:
    if image_loader is None:
        from PIL import Image
        image_loader = Image.open

    results = []
    total = len(crops_manifest)
    for i in range(0, total, batch):
        batch_crops = crops_manifest[i:i+batch]
        batch_paths = [crop_path(crop) for crop in batch_crops]
        images = [image_loader(path) for path in batch_paths]
        labels = labeler(images)
        for crop, path, (word, score) in zip(batch_crops, batch_paths, labels):
            crop = crop.copy()
            crop['crop_path'] = path
            crop['word'] = word
            crop['score'] = score
            results.append(crop)
        if progress and (i == 0 or (i // batch + 1) % 10 == 0 or i + batch >= total):
            print(f"labeled {min(i + batch, total)}/{total}", file=sys.stderr, flush=True)
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--crops', default='/tmp/walk_crops/crops_manifest.json')
    parser.add_argument('--vocab', default='ops/spatial_vocab.txt')
    parser.add_argument('--out', default='/tmp/walk_labels.json')
    parser.add_argument('--score-floor', type=float, default=0.0)
    parser.add_argument('--batch', type=int, default=64)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()

    if args.self_test:
        # Stub labeler
        def stub_labeler(imgs):
            return [('mug', 0.31)] * len(imgs)
        
        fake_manifest = [
            {'crop': 'fake1.jpg'},
            {'path': 'fake2.jpg'},
            {'crop_path': 'fake3.jpg'}
        ]
        result = label_all(fake_manifest, stub_labeler, image_loader=lambda p: None)
        assert len(result) == 3
        assert all(r['word'] == 'mug' for r in result)
        assert [r['crop_path'] for r in result] == ['fake1.jpg', 'fake2.jpg', 'fake3.jpg']
        assert json.dumps(result)  # test round-trip
        print("SELF-TEST PASS")
        sys.exit(0)

    vocab = load_vocab(args.vocab)
    labeler = build_labeler(vocab)
    
    with open(args.crops, 'r') as f:
        crops_manifest = json.load(f)
    
    labeled_crops = label_all(crops_manifest, labeler, batch=args.batch, progress=True)
    
    # Filter by score floor
    filtered_crops = [crop for crop in labeled_crops if crop['score'] >= args.score_floor]
    
    with open(args.out, 'w') as f:
        json.dump(filtered_crops, f, indent=2)

    # Print top-20 word histogram
    from collections import Counter
    words = [crop['word'] for crop in labeled_crops]
    counter = Counter(words)
    print("Top 20 words:")
    for word, count in counter.most_common(20):
        print(f"  {word}: {count}")

if __name__ == '__main__':
    main()
