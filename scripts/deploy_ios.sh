#!/bin/bash
# Build the 1080p-stream change, install to the iPhone, and launch it. One shot.
set -e
XCODEBUILD_UDID="00008150-001460D83686401C"   # ECID-style id, for xcodebuild -destination
DEVICECTL_UDID="D3A506B2-8923-5313-B8A3-FF769ABBA228"  # devicectl pairing UUID, for install/launch
cd /Users/zer00/Documents/VLM/trace-native-fastvlm
echo "=== building for device ==="
xcodebuild -project "FastVLM.xcodeproj" -scheme "FastVLM App" -configuration Debug \
  -destination "id=$XCODEBUILD_UDID" -allowProvisioningUpdates -derivedDataPath build/dd build
APP=$(find build/dd/Build/Products/Debug-iphoneos -maxdepth 1 -name "*.app" | head -1)
echo "=== installing $APP ==="
xcrun devicectl device install app --device "$DEVICECTL_UDID" "$APP"
echo "=== launching de.zer00.trace ==="
xcrun devicectl device process launch --device "$DEVICECTL_UDID" de.zer00.trace || true
echo "=== DEPLOY DONE ==="
