
from PIL import Image, ImageDraw, ImageFont
import os
out = r"D:\dshwork\bili-simul\extension\icons"
os.makedirs(out, exist_ok=True)
size = 512
img = Image.new("RGBA", (size, size), (0,0,0,0))
d = ImageDraw.Draw(img)
# rounded square with vertical gradient
grad = Image.new("RGBA", (size, size), (0,0,0,0))
gd = ImageDraw.Draw(grad)
for y in range(size):
    t = y / (size-1)
    r = int(251 + (255-251)*t)
    g = int(114 + (157-114)*t)
    b = int(153 + (183-153)*t)
    gd.line([(0,y),(size,y)], fill=(r,g,b,255))
mask = Image.new("L", (size,size), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle([0,0,size-1,size-1], radius=int(size*0.24), fill=255)
img.paste(grad, (0,0), mask)
# subtle top highlight
hl = Image.new("RGBA",(size,size),(0,0,0,0))
hd = ImageDraw.Draw(hl)
hd.ellipse([-size*0.2, -size*0.55, size*1.2, size*0.35], fill=(255,255,255,34))
img = Image.alpha_composite(img, hl)
# glyph
font = None
for cand in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
    if os.path.exists(cand):
        try:
            font = ImageFont.truetype(cand, int(size*0.56))
            break
        except Exception:
            pass
d = ImageDraw.Draw(img)
if font:
    txt = "译"
    bbox = d.textbbox((0,0), txt, font=font)
    w = bbox[2]-bbox[0]; h = bbox[3]-bbox[1]
    d.text(((size-w)/2 - bbox[0], (size-h)/2 - bbox[1] - size*0.01), txt, font=font, fill=(255,255,255,255))
for s in (16,32,48,128):
    img.resize((s,s), Image.LANCZOS).save(os.path.join(out, "icon%d.png" % s))
print("icons:", os.listdir(out))
