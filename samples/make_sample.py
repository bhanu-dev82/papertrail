"""Generate a fake electricity bill image used by the demo and tests."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1000, 1300
INK = (26, 26, 26)
MUTED = (90, 90, 90)
GREEN = (118, 185, 0)


def _font(size: int = 28) -> ImageFont.ImageFont:
    for candidate in (
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _ddmmyyyy(days: int) -> str:
    return (date.today() + timedelta(days=days)).strftime("%d-%m-%Y")


def make(path: str = "samples/electricity_bill.png") -> str:
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)

    title_font = _font(40)
    head_font = _font(30)
    body_font = _font(28)
    small_font = _font(22)

    # Top accent bar.
    draw.rectangle([0, 0, WIDTH, 18], fill=GREEN)

    draw.text((60, 60), "BANGALORE ELECTRICITY SUPPLY CO.", font=title_font, fill=INK)
    draw.text((60, 108), "(BESCOM) SAMPLE", font=head_font, fill=MUTED)
    draw.text(
        (60, 150),
        "Consumer bill / payment notice",
        font=small_font,
        fill=MUTED,
    )

    draw.line([(60, 195), (WIDTH - 60, 195)], fill=(210, 210, 210), width=2)

    rows = [
        ("Account no.", "7712-3381-09"),
        ("Bill no.", "2026-10-55821"),
        ("Bill date", _ddmmyyyy(-5)),
        ("Consumer", "Asha Rao"),
        ("Address", "Flat 4B, 12th Main, Indiranagar, 560038"),
        ("Units consumed", "312 kWh"),
    ]
    y = 225
    for label, value in rows:
        draw.text((60, y), label, font=small_font, fill=MUTED)
        draw.text((320, y), value, font=body_font, fill=INK)
        y += 48

    draw.text((60, y + 20), "AMOUNT PAYABLE", font=head_font, fill=MUTED)
    draw.text((60, y + 60), "\u20b92,340.00", font=_font(64), fill=INK)

    y += 160
    draw.rectangle([60, y, WIDTH - 60, y + 130], fill=(244, 249, 236))
    draw.text(
        (85, y + 20),
        f"PAY BY: {_ddmmyyyy(4)}",
        font=head_font,
        fill=INK,
    )
    draw.text(
        (85, y + 70),
        "Late payment fee of \u20b9150 applies after due date",
        font=small_font,
        fill=INK,
    )

    y += 170
    draw.text(
        (60, y),
        f"Disconnection may occur after {_ddmmyyyy(18)}",
        font=body_font,
        fill=INK,
    )
    draw.text(
        (60, y + 50),
        "if the bill remains unpaid.",
        font=body_font,
        fill=INK,
    )

    draw.text(
        (60, y + 130),
        "To dispute a charge, contact customer care with your account number.",
        font=small_font,
        fill=MUTED,
    )

    draw.line([(60, HEIGHT - 110), (WIDTH - 60, HEIGHT - 110)], fill=(210, 210, 210), width=2)
    draw.text(
        (60, HEIGHT - 85),
        "SAMPLE DOCUMENT FOR DEMO — not a real bill",
        font=small_font,
        fill=MUTED,
    )

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="PNG")
    return str(target)


if __name__ == "__main__":
    print(make())
