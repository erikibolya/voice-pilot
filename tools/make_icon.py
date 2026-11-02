"""Vygeneruje installer/icon.ico z kreslené ikony aplikace.

Ikona se nekreslí ručně v obrázkovém editoru — vzniká ze stejného kódu,
jaký používá okno a lišta, takže se nikdy nerozejde.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from pilot.ui.icons import app_icon  # noqa: E402


def main() -> int:
    from PIL import Image

    _app = QApplication.instance() or QApplication([])  # noqa: F841

    sizes = [16, 24, 32, 48, 64, 128, 256]
    png_dir = ROOT / "installer" / ".build"
    png_dir.mkdir(parents=True, exist_ok=True)

    images = []
    for size in sizes:
        pixmap = app_icon(size).pixmap(size, size)
        path = png_dir / f"icon-{size}.png"
        pixmap.save(str(path))
        images.append(Image.open(path).convert("RGBA"))

    target = ROOT / "installer" / "icon.ico"
    images[-1].save(
        target,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[:-1],
    )
    print(f"ikona: {target} ({target.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
