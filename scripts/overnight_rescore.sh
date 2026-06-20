#!/bin/bash

set -u

while true; do
    sleep 3600
    timestamp=$(date +%H%M)
    destination="/tmp/overnight_world_${timestamp}.json"
    
    # Pull device world json
    xcrun devicectl device copy from --device D3A506B2-8923-5313-B8A3-FF769ABBA228 --domain-type appDataContainer --domain-identifier de.zer00.soma --source 'Library/Application Support/SOMA/spatial_world.json' --destination "${destination}" || {
        echo "failure at $(date): pull failed" >> /tmp/overnight_rescore.log
        continue
    }
    
    # Run python evaluation
    python3 - <<EOF
import json
import sys

with open("${destination}", 'r') as f:
    data = json.load(f)

objects = len(data) if isinstance(data, list) else 1
phantoms = sum(1 for obj in (data if isinstance(data, list) else [data]) if obj.get('phantom') is True)
footprinted = sum(1 for obj in (data if isinstance(data, list) else [data]) if isinstance(obj.get('footprint'), list) and len(obj['footprint']) >= 3)

result = {
    "ts": "${timestamp}",
    "objects": objects,
    "phantoms": phantoms,
    "footprinted": footprinted
}

print(json.dumps(result), file=sys.stdout)
EOF
    
    echo "done at $(date): processed ${destination}" >> /tmp/overnight_rescore.log
done
