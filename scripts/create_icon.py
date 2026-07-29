from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
output = root / "assets" / "ion.ico"
size = 512
image = Image.new("RGBA", (size, size), "#030404")
draw = ImageDraw.Draw(image)
amber = "#ff7100"
blue = "#51aee8"
polygon = [(74, 256), (164, 84), (348, 84), (438, 256), (348, 428), (164, 428)]
draw.line(polygon + [polygon[0]], fill=amber, width=18, joint="curve")
draw.line([(94, 256), (148, 256)], fill=blue, width=10)
draw.line([(364, 256), (418, 256)], fill=blue, width=10)
draw.rectangle((157, 185, 195, 327), fill="#ff8a1c")
draw.rectangle((227, 185, 265, 327), fill="#ff8a1c")
draw.polygon([(265, 185), (317, 264), (317, 185), (355, 185), (355, 327), (319, 327), (265, 247)], fill="#ff8a1c")
image.save(output, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(output)
