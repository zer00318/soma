//
// For licensing see accompanying LICENSE file.
// Copyright (C) 2025 Apple Inc. All Rights Reserved.
//

import AVFoundation
import CoreImage
import Foundation
import SwiftUI

/// Displays a stream of video frames
public struct VideoFrameView: View {
    @Environment(\.colorScheme) private var colorScheme

    public let frames: AsyncStream<CVImageBuffer>
    public let cameraType: CameraType
    public let action: ((CVImageBuffer) -> Void)?

    @State private var hold: Bool = false
    @State private var videoFrame: CVImageBuffer?

    private var backgroundColor: Color {
        #if os(iOS)
        return Color(.secondarySystemBackground)
        #elseif os(macOS)
        return Color(.secondarySystemFill)
        #else
        // When in doubt, use these values that I captured to match iOS' secondarySystemBackground
        if colorScheme == .dark {
            return Color(red: 0.11, green: 0.11, blue: 0.12)
        } else {
            return Color(red: 0.95, green: 0.95, blue: 0.97)
        }
        #endif
    }

    public init(
        frames: AsyncStream<CVImageBuffer>,
        cameraType: CameraType,
        action: ((CVImageBuffer) -> Void)?
    ) {
        self.frames = frames
        self.cameraType = cameraType
        self.action = action
    }

    public var body: some View {
        Group {
            if let videoFrame {
                _ImageView(image: videoFrame)
                    .overlay(alignment: .bottom) {
                        if cameraType == .single {
                            Button {
                                tap()
                            } label: {
                                if hold {
                                    Label("Resume", systemImage: "play.fill")
                                } else {
                                    Label("Capture Photo", systemImage: "camera.fill")
                                }
                            }
                            .clipShape(.capsule)
                            .buttonStyle(.borderedProminent)
                            .tint(hold ? .gray : .accentColor)
                            .foregroundColor(.white)
                            .padding()
                        }
                    }
            } else {
                // spinner before the camera comes up
                ProgressView()
                    .controlSize(.large)
            }
        }
        // This ensures that we take up the full 4/3 aspect ratio
        // even if we don't have an image to display
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(backgroundColor)
        .clipShape(RoundedRectangle(cornerRadius: 10.0))
        .task {
            // feed frames to the _ImageView
            if Task.isCancelled {
                return
            }
            for await frame in frames {
                if !hold {
                    videoFrame = frame
                }
            }
        }
        .onChange(of: cameraType) { _, newType in
            // No matter what, when the user switches to .continuous,
            // we need to continue showing updated frames
            if newType == .continuous {
                hold = false
            }
        }
    }

    private func tap() {
        if hold {
            // resume
            hold = false
        } else if let videoFrame {
            hold = true
            if let action {
                action(videoFrame)
            }
        }
    }
}

// Shared CIContext to turn a camera CVPixelBuffer into a CGImage for display.
// WHY: assigning a raw CVPixelBuffer to `layer.contents` renders on the physical screen, but
// its IOSurface backing is NOT captured by AirPlay / screen mirroring / screen recording — so
// the live preview shows BLACK on a projector while looking fine on the phone. A CGImage-backed
// layer mirrors correctly. (Camera preview only; the perception pipeline keeps the raw buffer.)
private let _previewCIContext = CIContext(options: [.useSoftwareRenderer: false])

private func _displayContents(_ image: Any) -> Any {
    let obj = image as AnyObject
    if CFGetTypeID(obj) == CVPixelBufferGetTypeID() {
        let pb = obj as! CVPixelBuffer  // CVImageBuffer is a CVPixelBuffer
        let ci = CIImage(cvPixelBuffer: pb)
        if let cg = _previewCIContext.createCGImage(ci, from: ci.extent) {
            return cg
        }
    }
    return image
}

#if os(iOS)
    /// Internal view to display a CVImageBuffer
    private struct _ImageView: UIViewRepresentable {

        let image: Any
        var gravity = CALayerContentsGravity.resizeAspectFill

        func makeUIView(context: Context) -> UIView {
            let view = UIView()
            view.layer.contentsGravity = gravity
            return view
        }

        func updateUIView(_ uiView: UIView, context: Context) {
            // CGImage (not the raw pixel buffer) so the preview is visible under screen mirroring.
            uiView.layer.contents = _displayContents(image)
        }
    }
#else
    private struct _ImageView: NSViewRepresentable {

        let image: Any
        var gravity = CALayerContentsGravity.resizeAspectFill

        func makeNSView(context: Context) -> NSView {
            let view = NSView()
            view.wantsLayer = true
            view.layer?.contentsGravity = gravity
            return view
        }

        func updateNSView(_ uiView: NSView, context: Context) {
            uiView.layer?.contents = _displayContents(image)
        }
    }

#endif
