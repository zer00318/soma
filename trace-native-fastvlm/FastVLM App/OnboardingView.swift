//
// For licensing see accompanying LICENSE file.
// Copyright (C) 2025 Apple Inc. All Rights Reserved.
//

import SwiftUI

/// First-launch welcome for TRACE. Three short, warm slides shown once (gated by
/// the `traceHasOnboarded` @AppStorage flag in ContentView), then never again.
/// Skippable at any time. Purely presentational — no capture/permission logic.
struct OnboardingView: View {
    /// Called when the user finishes (Start) or skips. The caller flips the flag.
    let onFinish: () -> Void

    @State private var page = 0

    private struct Slide: Identifiable {
        let id = UUID()
        let symbol: String
        let title: String
        let body: String
    }

    private let slides: [Slide] = [
        Slide(
            symbol: "eye",
            title: "A memory for everything you see",
            body: "Point your camera at the world."
        ),
        Slide(
            symbol: "brain.head.profile",
            title: "It remembers",
            body: "Signs, faces, objects, and what's said — all kept on your phone."
        ),
        Slide(
            symbol: "sparkles",
            title: "Ask it anything you saw",
            body: "It only tells you what it actually saw. When it's unsure, it says so."
        ),
    ]

    var body: some View {
        ZStack {
            // Warm, calm gradient backdrop.
            LinearGradient(
                colors: [Color.black, Color(red: 0.10, green: 0.10, blue: 0.18)],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            VStack(spacing: 0) {
                // Skip is always available.
                HStack {
                    Spacer()
                    Button("Skip") { onFinish() }
                        .font(.body.weight(.medium))
                        .foregroundStyle(.white.opacity(0.6))
                        .padding(.trailing, 20)
                        .padding(.top, 12)
                }

                TabView(selection: $page) {
                    ForEach(Array(slides.enumerated()), id: \.element.id) { index, slide in
                        slideView(slide)
                            .tag(index)
                    }
                }
                #if os(iOS)
                .tabViewStyle(.page(indexDisplayMode: .always))
                .indexViewStyle(.page(backgroundDisplayMode: .always))
                #endif

                Button {
                    if page < slides.count - 1 {
                        withAnimation { page += 1 }
                    } else {
                        onFinish()
                    }
                } label: {
                    Text(page < slides.count - 1 ? "Next" : "Start")
                        .font(.title3.bold())
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(Color.accentColor, in: RoundedRectangle(cornerRadius: 16))
                }
                .padding(.horizontal, 28)
                .padding(.bottom, 36)
            }
        }
    }

    @ViewBuilder private func slideView(_ slide: Slide) -> some View {
        VStack(spacing: 24) {
            Spacer()
            Image(systemName: slide.symbol)
                .font(.system(size: 76, weight: .light))
                .foregroundStyle(.white)
                .padding(36)
                .background(Color.accentColor.opacity(0.18), in: Circle())

            VStack(spacing: 14) {
                Text(slide.title)
                    .font(.largeTitle.bold())
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.white)
                Text(slide.body)
                    .font(.title3)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.white.opacity(0.8))
            }
            .padding(.horizontal, 32)
            Spacer()
            Spacer()
        }
    }
}

#Preview {
    OnboardingView(onFinish: {})
}
