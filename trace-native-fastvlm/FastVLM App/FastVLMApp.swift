//
// For licensing see accompanying LICENSE file.
// Copyright (C) 2025 Apple Inc. All Rights Reserved.
//

import SwiftUI
import Video

@main
struct FastVLMApp: App {
    // Persist the ARKit world map when the app backgrounds, but ONLY in spatial
    // mode (ARKit owns the camera). Saving does not touch the camera, so it's
    // safe here. Camera START happens in ContentView's .task (same toggle) so it
    // composes with model load / permissions.
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("spatialMode") private var spatialMode = false
    @AppStorage("traceHubURL") private var hubURL = ""

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active {
                VideoRecorder.shared.configure(hubURL: hubURL)
            } else if phase == .background {
                if spatialMode { TraceARKitEngine.shared.saveWorldMap() }
                // Final flush only if the user explicitly armed recording.
                VideoRecorder.shared.finishAndUpload(hubURL: hubURL)
            }
        }
    }
}
