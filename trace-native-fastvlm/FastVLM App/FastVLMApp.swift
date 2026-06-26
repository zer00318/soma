//
// For licensing see accompanying LICENSE file.
// Copyright (C) 2025 Apple Inc. All Rights Reserved.
//

import SwiftUI

@main
struct FastVLMApp: App {
    // NOTE: ARKit world-tracking lifecycle is intentionally NOT wired here.
    // ARKit and the app's AVCaptureSession can't both own the camera without
    // the multitasking-camera entitlement; running both produced black/rotated
    // frames. TraceARKitEngine stays in the tree for a future, properly-tested
    // ARKit-only frame path. See ContentView camera.start().
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
