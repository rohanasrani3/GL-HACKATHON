import Photos
import UIKit

/// The iOS stand-in for ScreenshotWatcherService. iOS can't run code when a screenshot is taken,
/// so we look for new screenshots when the app opens, while it's open (change observer), in
/// background refresh, and on demand (App Intent / Back Tap).
@MainActor
final class ScreenshotScanner: NSObject, PHPhotoLibraryChangeObserver {
    static let shared = ScreenshotScanner()

    private var observing = false
    private var debounce: Task<Void, Never>?

    var canRead: Bool { PHPhotoLibrary.authorizationStatus(for: .readWrite) == .authorized }

    var statusText: String {
        switch PHPhotoLibrary.authorizationStatus(for: .readWrite) {
        case .authorized: return "Full access"
        case .limited: return "Limited: needs Full Access to see new screenshots"
        case .denied, .restricted: return "Denied"
        case .notDetermined: return "Not asked yet"
        @unknown default: return "Unknown"
        }
    }

    func requestAccess() async -> Bool {
        await PHPhotoLibrary.requestAuthorization(for: .readWrite) == .authorized
    }

    private static var screenshotPredicate: String { "(mediaSubtypes & %d) != 0" }

    /// Screenshots created after `date`, oldest first. Other photos are never fetched.
    func screenshots(after date: Date) -> [PHAsset] {
        let opts = PHFetchOptions()
        opts.predicate = NSPredicate(
            format: "\(Self.screenshotPredicate) AND creationDate > %@",
            Int(PHAssetMediaSubtype.photoScreenshot.rawValue), date as NSDate
        )
        opts.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: true)]
        var out: [PHAsset] = []
        PHAsset.fetchAssets(with: .image, options: opts).enumerateObjects { asset, _, _ in out.append(asset) }
        return out
    }

    func latestScreenshot() -> PHAsset? {
        let opts = PHFetchOptions()
        opts.predicate = NSPredicate(format: Self.screenshotPredicate, Int(PHAssetMediaSubtype.photoScreenshot.rawValue))
        opts.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        opts.fetchLimit = 1
        return PHAsset.fetchAssets(with: .image, options: opts).firstObject
    }

    /// Downscaled, re-encoded JPEG for upload, or nil if the asset is gone.
    func jpeg(assetId: String) async -> Data? {
        guard let asset = PHAsset.fetchAssets(withLocalIdentifiers: [assetId], options: nil).firstObject else { return nil }
        let opts = PHImageRequestOptions()
        opts.deliveryMode = .highQualityFormat
        opts.resizeMode = .fast
        opts.isNetworkAccessAllowed = true
        let target = CGSize(width: ImagePrep.maxSide, height: ImagePrep.maxSide)
        let image: UIImage? = await withCheckedContinuation { cont in
            PHImageManager.default().requestImage(for: asset, targetSize: target, contentMode: .aspectFit, options: opts) { img, _ in
                cont.resume(returning: img)
            }
        }
        return image.flatMap { ImagePrep.jpeg(from: $0) }
    }

    // MARK: Live while open

    func startObserving() {
        guard !observing, canRead else { return }
        PHPhotoLibrary.shared().register(self)
        observing = true
    }

    nonisolated func photoLibraryDidChange(_ changeInstance: PHChange) {
        Task { @MainActor in self.scheduleScan() }
    }

    /// Screenshots are written in steps, so changes arrive in bursts. Debounce.
    private func scheduleScan() {
        debounce?.cancel()
        debounce = Task {
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            guard !Task.isCancelled else { return }
            await Agent.shared.scan()
        }
    }
}
