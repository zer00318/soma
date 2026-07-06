//
// TimelineView.swift — P41: the memory you can SEE.
//
// Open the app → today's episodes, honest gaps included, plus the sleep-authored
// day digest with its receipts. Serves entirely from the hub's derived rows
// (GET /episodes?day= + GET /digest?day=, both <20ms) — no brain invocation,
// no waiting. Gaps are first-class cards: the timeline never pretends the
// memory was awake when it wasn't.
//

import SwiftUI

struct TimelineEpisode: Decodable, Identifiable {
    let id: String
    let day: String?
    let text: String
    let start_ms: Int64
    let end_ms: Int64
    let kind: String?
    let label: String?
    let place: String?
    let observation_count: Int?
    let channels: [String: Int]?
}

struct TimelineDigestRow: Decodable {
    struct Bullet: Decodable { let text: String; let episode_ids: [String] }
    let day: String?
    let text: String
    let bullets: [Bullet]?
    let thin_day: Bool?
    let episode_count: Int?
}

private struct EpisodesReply: Decodable { let rows: [TimelineEpisode] }
private struct DigestReply: Decodable { let rows: [TimelineDigestRow] }

struct TimelineView: View {
    let hubURL: String
    @State private var dayOffset = 0
    @State private var episodes: [TimelineEpisode] = []
    @State private var digest: TimelineDigestRow?
    @State private var loading = false
    @State private var loadError: String?
    @Environment(\.dismiss) private var dismiss

    private var dayString: String {
        let d = Calendar.current.date(byAdding: .day, value: dayOffset, to: Date()) ?? Date()
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"
        return f.string(from: d)
    }

    private var dayTitle: String {
        switch dayOffset {
        case 0: return "Today"
        case -1: return "Yesterday"
        default:
            let d = Calendar.current.date(byAdding: .day, value: dayOffset, to: Date()) ?? Date()
            let f = DateFormatter(); f.dateFormat = "EEE, MMM d"
            return f.string(from: d)
        }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                TraceBrand.ink.ignoresSafeArea()
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        if let digest {
                            digestCard(digest)
                        }
                        if episodes.isEmpty && !loading {
                            VStack(alignment: .leading, spacing: 8) {
                                Text(loadError ?? "Nothing captured \(dayTitle.lowercased()) yet.")
                                    .font(.callout).foregroundStyle(TraceBrand.neutral)
                                Text("Episodes appear as the day is lived; the nightly sleep names them.")
                                    .font(.footnote).foregroundStyle(TraceBrand.neutral.opacity(0.7))
                            }.padding(.vertical, 24)
                        }
                        ForEach(episodes) { ep in
                            if ep.kind == "gap" { gapCard(ep) } else { episodeCard(ep) }
                        }
                    }
                    .padding()
                }
                .refreshable { await load() }
            }
            .navigationTitle(dayTitle)
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(TraceBrand.ink, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    HStack(spacing: 2) {
                        Button { dayOffset -= 1; Task { await load() } } label: {
                            Image(systemName: "chevron.left")
                        }
                        Button { dayOffset += 1; Task { await load() } } label: {
                            Image(systemName: "chevron.right")
                        }.disabled(dayOffset >= 0)
                    }.tint(TraceBrand.emberLight)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }.tint(TraceBrand.emberLight)
                }
            }
        }
        .preferredColorScheme(.dark)
        .task { await load() }
    }

    // MARK: cards

    @ViewBuilder private func digestCard(_ d: TimelineDigestRow) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: "moon.zzz.fill").foregroundStyle(TraceBrand.emberLight)
                Text("The day, digested").font(.subheadline.weight(.semibold))
                    .foregroundStyle(TraceBrand.lab)
                Spacer()
                if d.thin_day == true {
                    Text("mostly uncaptured").font(.caption2)
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(Color.white.opacity(0.08), in: Capsule())
                        .foregroundStyle(TraceBrand.neutral)
                }
            }
            if let bullets = d.bullets, !bullets.isEmpty {
                ForEach(Array(bullets.enumerated()), id: \.offset) { _, b in
                    HStack(alignment: .top, spacing: 8) {
                        Circle().fill(TraceBrand.ember).frame(width: 5, height: 5)
                            .padding(.top, 6)
                        Text(b.text).font(.callout).foregroundStyle(TraceBrand.lab)
                    }
                }
            } else {
                Text(d.text).font(.callout).foregroundStyle(TraceBrand.lab)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TraceBrand.glass(RoundedRectangle(cornerRadius: 18)))
    }

    @ViewBuilder private func episodeCard(_ ep: TimelineEpisode) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(ep.label ?? titleFrom(ep.text))
                    .font(.subheadline.weight(.semibold)).foregroundStyle(TraceBrand.lab)
                Spacer()
                Text(span(ep)).font(.caption.monospacedDigit())
                    .foregroundStyle(TraceBrand.emberLight)
            }
            HStack(spacing: 8) {
                if let n = ep.observation_count {
                    Text("\(n) observations").font(.caption).foregroundStyle(TraceBrand.neutral)
                }
                if let chans = ep.channels, !chans.isEmpty {
                    Text(chans.keys.sorted().prefix(3).joined(separator: " · "))
                        .font(.caption).foregroundStyle(TraceBrand.neutral.opacity(0.8))
                        .lineLimit(1)
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(TraceBrand.glass(RoundedRectangle(cornerRadius: 16)))
    }

    @ViewBuilder private func gapCard(_ ep: TimelineEpisode) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "eye.slash").font(.caption)
                .foregroundStyle(TraceBrand.neutral.opacity(0.7))
            Text(titleFrom(ep.text)).font(.caption)
                .foregroundStyle(TraceBrand.neutral)
            Spacer()
        }
        .padding(.horizontal, 14).padding(.vertical, 8)
        .overlay(RoundedRectangle(cornerRadius: 12)
            .strokeBorder(Color.white.opacity(0.10),
                          style: StrokeStyle(lineWidth: 0.8, dash: [5, 4])))
    }

    // MARK: helpers

    private func titleFrom(_ text: String) -> String {
        // "GAP | no capture | 2h 14m" -> "no capture · 2h 14m"
        let parts = text.split(separator: "|").dropFirst().map {
            $0.trimmingCharacters(in: .whitespaces)
        }
        return parts.joined(separator: " · ")
    }

    private func span(_ ep: TimelineEpisode) -> String {
        let f = DateFormatter(); f.dateFormat = "HH:mm"
        let a = f.string(from: Date(timeIntervalSince1970: Double(ep.start_ms) / 1000))
        let b = f.string(from: Date(timeIntervalSince1970: Double(ep.end_ms) / 1000))
        return a == b ? a : "\(a)–\(b)"
    }

    private func fetch<T: Decodable>(_ path: String, as type: T.Type) async -> T? {
        guard !hubURL.isEmpty,
              let url = URL(string: "\(hubURL)\(path)?day=\(dayString)") else { return nil }
        var req = URLRequest(url: url); req.timeoutInterval = 6
        guard let (data, _) = try? await URLSession.shared.data(for: req) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }

    private func load() async {
        loading = true; loadError = nil
        async let eps = fetch("/episodes", as: EpisodesReply.self)
        async let dig = fetch("/digest", as: DigestReply.self)
        let (e, d) = await (eps, dig)
        if e == nil && d == nil {
            loadError = "Can't reach the memory hub — same Wi-Fi as the Mac?"
        }
        episodes = e?.rows ?? []
        digest = d?.rows.first
        loading = false
    }
}
