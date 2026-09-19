import UIKit

/// Downscale + re-encode as JPEG. Re-encoding from pixels drops EXIF/GPS (CLAUDE.md §4).
/// Never upload the original asset data.
enum ImagePrep {
    static let maxSide: CGFloat = 1600

    static func jpeg(from image: UIImage, maxSide: CGFloat = ImagePrep.maxSide) -> Data? {
        let pixelW = image.size.width * image.scale
        let pixelH = image.size.height * image.scale
        guard pixelW > 0, pixelH > 0 else { return nil }
        let ratio = min(1, maxSide / max(pixelW, pixelH))
        let target = CGSize(width: (pixelW * ratio).rounded(), height: (pixelH * ratio).rounded())

        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        let resized = UIGraphicsImageRenderer(size: target, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: target))
        }
        return resized.jpegData(compressionQuality: 0.85)
    }

    static func jpeg(from data: Data) -> Data? {
        UIImage(data: data).flatMap { jpeg(from: $0) }
    }
}
