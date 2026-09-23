"""
Regenerates Robert's app icon files from the vector source (logo.svg).
Run after editing logo.svg:

    python -m desktop.assets.generate_icon
"""
from pathlib import Path

import cairosvg
from PIL import Image

ASSETS_DIR = Path(__file__).parent
SVG_PATH = ASSETS_DIR / "logo.svg"

if __name__ == "__main__":
    png_path = ASSETS_DIR / "icon.png"
    ico_path = ASSETS_DIR / "icon.ico"

    cairosvg.svg2png(url=str(SVG_PATH), write_to=str(png_path), output_width=512, output_height=512)

    img = Image.open(png_path)
    img.save(ico_path, sizes=[(16, 16), (32, 32), (48, 48), (128, 128), (256, 256)])

    print(f"Wrote {png_path} and {ico_path} from {SVG_PATH.name}")
