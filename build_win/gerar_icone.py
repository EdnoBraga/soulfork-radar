"""Gera o radar.ico (roda no build; Pillow só é dependência do CI)."""
from PIL import Image, ImageDraw

TAM = 256
img = Image.new("RGBA", (TAM, TAM), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# fundo arredondado escuro
d.rounded_rectangle([8, 8, TAM - 8, TAM - 8], radius=56, fill=(11, 18, 32, 255))

verde = (199, 244, 100, 255)
cx = cy = TAM // 2

# anéis do radar
for r, alpha in ((88, 90), (62, 140), (36, 200)):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(199, 244, 100, alpha), width=7)

# varredura (setor)
d.pieslice([cx - 88, cy - 88, cx + 88, cy + 88], start=-80, end=-20,
           fill=(199, 244, 100, 70))
# agulha e centro
d.line([cx, cy, cx + 72, cy - 52], fill=verde, width=10)
d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=verde)
# um "lead" encontrado
d.ellipse([cx + 44, cy - 66, cx + 60, cy - 50], fill=(246, 242, 182, 255))

img.save("build_win/radar.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print("radar.ico gerado")
