//
// For licensing see accompanying LICENSE file.
// Copyright (C) 2025 Apple Inc. All Rights Reserved.
//

import SwiftUI

@main
struct FastVLMApp: App {
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .active:
                TraceARKitEngine.shared.start()
            case .background:
                TraceARKitEngine.shared.saveWorldMap()
            default:
                break
            }
        }
    }
}
