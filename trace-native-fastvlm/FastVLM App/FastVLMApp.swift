//
// For licensing see accompanying LICENSE file.
// Copyright (C) 2025 Apple Inc. All Rights Reserved.
//

import SwiftUI

@main
struct FastVLMApp: App {
    // Persist the ARKit world map when the app backgrounds, but ONLY in spatial
    // mode (ARKit owns the camera). Saving does not touch the camera, so it's
    // safe here. Camera START happens in ContentView's .task (same toggle) so it
    // composes with model load / permissions.
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("spatialMode") private var spatialMode = false

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background && spatialMode {
                TraceARKitEngine.shared.saveWorldMap()
            }
        }
    }
}
