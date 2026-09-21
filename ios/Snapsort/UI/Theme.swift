import SwiftUI

/// later.exe "Relay" visual language (port of android/.../ui/theme): near-black and graphite
/// surfaces, warm off-white text, electric green for active/success, amber for attention,
/// thin borders, monospace only for technical accents.
enum Relay {
    static let background = Color(hex: 0x0D100B)
    static let surface = Color(hex: 0x171B15)
    static let textPrimary = Color(hex: 0xF1F1E8)
    static let textMuted = Color(hex: 0xA2AA9B)
    static let border = Color(hex: 0x2B3228)
    static let green = Color(hex: 0x2DFF60)
    static let lime = Color(hex: 0x80ED28)
    static let amber = Color(hex: 0xE7C17D)

    static let gutter: CGFloat = 20
}

enum RelayFont {
    static let headline = Font.system(size: 26, weight: .semibold)
    static let titleLarge = Font.system(size: 20, weight: .semibold)
    static let titleMedium = Font.system(size: 17, weight: .semibold)
    static let bodyLarge = Font.system(size: 16)
    static let bodyMedium = Font.system(size: 14)
    static let bodyMediumStrong = Font.system(size: 14, weight: .medium)
    static let labelLarge = Font.system(size: 13, weight: .semibold, design: .monospaced)
    static let labelMedium = Font.system(size: 11, weight: .medium, design: .monospaced)
    static let brand = Font.system(size: 17, weight: .bold, design: .monospaced)
}

extension Color {
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: 1
        )
    }
}

extension View {
    /// Small monospace status label (labelMedium, 0.8 tracking).
    func relayLabel(_ color: Color = Relay.textMuted) -> some View {
        font(RelayFont.labelMedium).tracking(0.8).foregroundStyle(color)
    }
}

/// Filled button: off-white on near-black (Review) or green (primary actions).
struct RelayFilledButtonStyle: ButtonStyle {
    var fill: Color = Relay.textPrimary
    var height: CGFloat = 50

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(RelayFont.labelLarge)
            .tracking(0.5)
            .foregroundStyle(Relay.background)
            .frame(maxWidth: .infinity, minHeight: height)
            .background(fill.opacity(configuration.isPressed ? 0.8 : 1))
            .clipShape(RoundedRectangle(cornerRadius: 2))
    }
}

/// Outlined button with a thin border.
struct RelayOutlineButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(RelayFont.labelLarge)
            .tracking(0.5)
            .foregroundStyle(Relay.textPrimary)
            .frame(maxWidth: .infinity, minHeight: 48)
            .background(configuration.isPressed ? Relay.border : Color.clear)
            .overlay(RoundedRectangle(cornerRadius: 2).stroke(Relay.border, lineWidth: 1))
    }
}

struct ToastView: View {
    let text: String

    var body: some View {
        Text(text)
            .font(RelayFont.bodyMedium)
            .foregroundStyle(Relay.textPrimary)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Relay.surface)
            .overlay(RoundedRectangle(cornerRadius: 3).stroke(Relay.border, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 3))
            .padding(.horizontal, Relay.gutter)
    }
}
