"""Pick readable foreground colours for an arbitrary background.

This is how real applications do it: decide light-on-dark vs dark-on-light from
the background's **relative luminance**, not from a naive RGB average. The eye is
far more sensitive to green than to blue, so `(r+g+b)/3` misjudges saturated
colours badly — a mid pink and a mid blue of the same "average" read very
differently.

`relative_luminance` and `contrast_ratio` follow WCAG 2.x:
    https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
    https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio

Rather than pure black/white, `ink()` returns near-black or near-white tuned to
the background, and `muted_ink()` a softened version for secondary text — the
same "dark grey / light grey" idea, but verified to keep enough contrast instead
of assumed.

**Known ceiling.** For mid-luminance backgrounds neither near-black nor
near-white can reach 4.5:1 — e.g. #6E74BF tops out around 4.1:1. That is a
property of the colour, not a bug: 4.5:1 is simply unreachable there with a
two-colour scheme. `ink()` always picks the better of the two, so it is as
readable as a black/white choice can be; only a background-tinted overlay
(which would change the design) could do better.
"""

from PyQt6.QtGui import QColor

# WCAG AA wants 4.5:1 for body text and 3:1 for large/secondary text. Secondary
# chrome (a title bar caption, a close glyph) is large or bold, so 3:1 is the
# floor we hold it to — but we always take the better of the two candidates.
AA_NORMAL = 4.5
AA_LARGE = 3.0

# Near-black / near-white read as less harsh than #000 / #fff while keeping
# essentially the same contrast.
INK_DARK = "#1c1917"
INK_LIGHT = "#fafaf9"


def _srgb_to_linear(channel: float) -> float:
    """Undo the sRGB transfer function for one 0..1 channel."""
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(color: QColor) -> float:
    """WCAG relative luminance, 0 (black) .. 1 (white)."""
    r, g, b = (_srgb_to_linear(c / 255.0) for c in (color.red(), color.green(),
                                                    color.blue()))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: QColor, b: QColor) -> float:
    """WCAG contrast ratio between two colours, 1.0 .. 21.0."""
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def is_dark(background: str | QColor) -> bool:
    """True when a background wants light text on it."""
    bg = QColor(background)
    if not bg.isValid():
        return False
    return contrast_ratio(bg, QColor(INK_LIGHT)) >= contrast_ratio(bg, QColor(INK_DARK))


def ink(background: str | QColor) -> str:
    """Primary foreground for `background`: whichever of near-black/near-white
    contrasts better."""
    return INK_LIGHT if is_dark(background) else INK_DARK


def muted_ink(background: str | QColor, strength: float = 0.62,
              minimum: float = AA_LARGE) -> str:
    """A softened foreground for secondary chrome (captions, glyphs).

    Blends the primary ink toward the background by `strength` (0 = background,
    1 = full ink), then backs off toward full ink until the result still clears
    `minimum` contrast — so "muted" never becomes "invisible", which is exactly
    how a mid-grey caption disappeared on a mid-tone note.
    """
    bg = QColor(background)
    if not bg.isValid():
        return INK_DARK
    target = QColor(ink(bg))

    best = target
    # Walk from the requested softness back toward full ink, taking the first
    # blend that still meets the contrast floor.
    steps = 12
    for i in range(steps + 1):
        f = strength + (1.0 - strength) * (i / steps)
        candidate = QColor(
            round(bg.red() + (target.red() - bg.red()) * f),
            round(bg.green() + (target.green() - bg.green()) * f),
            round(bg.blue() + (target.blue() - bg.blue()) * f),
        )
        best = candidate
        if contrast_ratio(bg, candidate) >= minimum:
            break
    return best.name()


def blend(background: str | QColor, toward: str | QColor, amount: float) -> str:
    """Mix `background` toward another colour by `amount` (0..1).

    Used for chrome fills (a title bar tint, a divider) that should follow the
    note's colour instead of being a fixed grey.
    """
    bg, other = QColor(background), QColor(toward)
    if not bg.isValid():
        return QColor(toward).name()
    amount = max(0.0, min(1.0, amount))
    return QColor(
        round(bg.red() + (other.red() - bg.red()) * amount),
        round(bg.green() + (other.green() - bg.green()) * amount),
        round(bg.blue() + (other.blue() - bg.blue()) * amount),
    ).name()


def shade(background: str | QColor, amount: float = 0.10) -> str:
    """Darken a light background / lighten a dark one by `amount`.

    Gives chrome (title bars, hover fills) a tint that stays visible whichever
    way the background leans.
    """
    return blend(background, INK_LIGHT if is_dark(background) else INK_DARK, amount)
