import SwiftUI

/// One demonstration photo, from disk when it has been seen before.
struct ExercisePhoto: View {
    let path: String

    @State private var image: UIImage?
    @State private var missing = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 8).fill(.quaternary)
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            } else if missing {
                VStack(spacing: 4) {
                    Image(systemName: "photo").font(.title2)
                    Text("Shows once you have signal").font(.caption2)
                }
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(8)
            } else {
                ProgressView()
            }
        }
        .aspectRatio(4 / 3, contentMode: .fit)
        .frame(maxWidth: .infinity)
        .accessibilityLabel("Demonstration photo")
        .task(id: path) {
            if let data = await PhotoCache.shared.data(for: path),
               let loaded = UIImage(data: data) {
                image = loaded
            } else {
                missing = true
            }
        }
    }
}
