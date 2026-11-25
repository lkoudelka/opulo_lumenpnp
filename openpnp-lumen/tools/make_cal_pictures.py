#!/usr/bin/env python3
"""Pictures for Scripts > Lumen > Machine Calibration (manual steps), written to lib/lumen/pictures/.

  python3 tools/make_cal_pictures.py [BENCH_LOG_DIR]

Drawn pictures need only Pillow.  The three camera pictures (visual home free, target on the visual
home, target at its park spot) are cut from top-camera images taken on a LumenPnP V4.1 (bench
2026-11-06, ~/claude/opulo/_logs); without BENCH_LOG_DIR the committed ones are kept.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "lib", "lumen", "pictures")
W, H = 520, 300
BG = (250, 250, 247)
INK = (40, 40, 40)
GREY = (150, 150, 150)
GREEN = (30, 150, 60)
RED = (200, 40, 40)
BLUE = (40, 90, 200)
PLATE = (70, 95, 160)


def font(size, bold=False):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else ""),
              "/usr/share/fonts/TTF/DejaVuSans%s.ttf" % ("-Bold" if bold else "")):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F, FB, FS = font(15), font(16, True), font(13)


def canvas():
    im = Image.new("RGB", (W, H), BG)
    return im, ImageDraw.Draw(im)


def label(d, xy, text, fill=INK, f=None, anchor="la"):
    d.text(xy, text, fill=fill, font=f or F, anchor=anchor)


def nozzle(d, x, ytip, name, tip_w=10, body=INK):
    """Side view: nozzle body above ytip, tip opening at ytip."""
    d.rectangle([x - 14, ytip - 120, x + 14, ytip - 60], fill=(120, 120, 125), outline=body)
    d.polygon([(x - 14, ytip - 60), (x + 14, ytip - 60), (x + tip_w // 2 + 2, ytip), (x - tip_w // 2 - 2, ytip)],
              fill=(185, 185, 190), outline=body)
    d.line([(x, ytip - 118), (x, ytip - 2)], fill=(90, 90, 95), width=2)
    label(d, (x, ytip - 128), name, f=FB, anchor="ms")


def save(im, name):
    p = os.path.join(OUT, name)
    im.save(p, optimize=True)
    print("wrote", os.path.relpath(p))


def nozzles_level():
    im, d = canvas()
    label(d, (14, 10), "Before homing: both nozzles UP and level", f=FB)
    d.rectangle([0, 250, W, 262], fill=PLATE)
    label(d, (10, 268), "staging plate / datum board", fill=GREY, f=FS)
    nozzle(d, 150, 170, "N1")
    nozzle(d, 240, 170, "N2")
    d.line([(110, 170), (280, 170)], fill=GREEN, width=2)
    label(d, (290, 148), "same height", fill=GREEN)
    d.line([(330, 170), (330, 248)], fill=GREEN, width=2)
    d.polygon([(324, 178), (336, 178), (330, 168)], fill=GREEN)
    label(d, (340, 200), "high above", fill=GREEN)
    label(d, (340, 218), "the plate", fill=GREEN)
    nozzle(d, 475, 240, "", body=RED)
    d.line([(445, 110), (505, 250)], fill=RED, width=4)
    d.line([(505, 110), (445, 250)], fill=RED, width=4)
    label(d, (W - 10, 268), "never home with a nozzle low", fill=RED, f=FS, anchor="ra")
    save(im, "cal-nozzles-level.png")


def z_contact():
    im, d = canvas()
    label(d, (14, 10), "Z by vacuum contact (the nozzle is never pushed down)", f=FB)
    d.rectangle([0, 230, 260, 245], fill=PLATE)
    d.ellipse([110, 225, 150, 235], fill=(240, 240, 240))
    label(d, (130, 262), "fiducial", fill=GREY, f=FS, anchor="ms")
    nozzle(d, 130, 228, "N1")
    for i, yy in enumerate((150, 175, 200)):
        d.line([(60, yy), (90, yy)], fill=GREY, width=1)
    label(d, (20, 140), "0.05 mm", fill=GREY, f=FS)
    label(d, (20, 156), "steps, slow", fill=GREY, f=FS)
    # vacuum level graph
    ox, oy, gw, gh = 300, 60, 200, 170
    d.line([(ox, oy), (ox, oy + gh), (ox + gw, oy + gh)], fill=INK, width=2)
    label(d, (ox + gw, oy + gh + 6), "Z down", f=FS, anchor="ra")
    label(d, (ox - 6, oy - 4), "vacuum", f=FS, anchor="rs")
    pts = [(ox + 5 + i * 12, oy + 30 + (i % 2) * 2) for i in range(12)] + [(ox + 150, oy + 130), (ox + 170, oy + 135)]
    d.line(pts, fill=BLUE, width=3)
    d.line([(ox + 141, oy + 10), (ox + 141, oy + gh)], fill=GREEN, width=2)
    label(d, (ox + 146, oy + 12), "contact =", fill=GREEN, f=FS)
    label(d, (ox + 146, oy + 28), "surface Z", fill=GREEN, f=FS)
    label(d, (ox + 6, oy + 42), "open tip: free air", fill=BLUE, f=FS)
    label(d, (14, 282), "stops at the first drop; max 2.5 mm travel; back to safe Z with vacuum off", fill=INK, f=FS)
    save(im, "cal-z-contact.png")


def tip_swap():
    im, d = canvas()
    label(d, (14, 10), "Swap the nozzle tip by hand", f=FB)
    nozzle(d, 120, 165, "N1")
    d.rectangle([108, 178, 132, 215], fill=(200, 200, 205), outline=INK)
    d.polygon([(112, 215), (128, 215), (124, 232), (116, 232)], fill=(200, 200, 205), outline=INK)
    d.line([(150, 200), (190, 200)], fill=BLUE, width=3)
    d.polygon([(190, 194), (190, 206), (200, 200)], fill=BLUE)
    label(d, (60, 250), "1. pull the old tip", f=FS)
    label(d, (60, 268), "   straight down", f=FS)
    # holder
    d.rectangle([230, 200, 500, 240], fill=(215, 215, 210), outline=INK)
    for i, n in enumerate(("N045", "N08", "N14", "N24", "N40", "N75")):
        x = 255 + i * 45
        d.ellipse([x - 12, 208, x + 12, 232], fill=(255, 255, 255), outline=INK)
        label(d, (x, 196), n, f=FS, anchor="ms")
    d.ellipse([288, 206, 316, 234], outline=GREEN, width=3)
    label(d, (230, 96), "2. put it in its holder slot,", f=FS)
    label(d, (230, 114), "   take the requested tip", f=FS)
    label(d, (230, 132), "3. push it onto the nozzle until", f=FS)
    label(d, (230, 150), "   it clicks; it must sit straight", f=FS)
    label(d, (14, 282), "OpenPnP moved the nozzle to the tip change position first. Then press Done.", f=FS)
    save(im, "cal-tip-swap.png")


def circle_pair(name, title, good_text, bad_text, inner, outer, ring_bad):
    im, d = canvas()
    label(d, (14, 10), title, f=FB)
    for k, (cx, ok) in enumerate(((140, True), (390, False))):
        cy = 150
        d.rectangle([cx - 110, cy - 105, cx + 110, cy + 105], fill=(25, 35, 70))
        d.ellipse([cx - outer, cy - outer, cx + outer, cy + outer], fill=(120, 130, 150))
        d.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], fill=(10, 10, 15) if name != "cal-fid-circle.png"
                  else (245, 245, 245))
        r = inner if ok else ring_bad
        col = GREEN if ok else RED
        d.ellipse([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], outline=col, width=3)
        d.line([(cx - 12, cy), (cx + 12, cy)], fill=col, width=2)
        d.line([(cx, cy - 12), (cx, cy + 12)], fill=col, width=2)
        label(d, (cx, cy + 128), good_text if ok else bad_text, fill=col, f=FS, anchor="ms")
        label(d, (cx, cy + 146), "RIGHT" if ok else "WRONG", fill=col, f=FB, anchor="ms")
    save(im, name)


def camera_picture(src, name, caption, colour, box=None):
    im = Image.open(src).convert("RGB")
    if box:
        im = im.crop(box)
    im.thumbnail((W, H - 34))
    out = Image.new("RGB", (W, im.size[1] + 34), BG)
    out.paste(im, ((W - im.size[0]) // 2, 34))
    d = ImageDraw.Draw(out)
    label(d, (14, 8), caption, fill=colour, f=FB)
    save(out, name)


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    nozzles_level()
    z_contact()
    tip_swap()
    circle_pair("cal-fid-circle.png", "Fiducial: the green circle must hug the white dot",
                "circle on the dot edge", "circle on another ring", 22, 34, 60)
    circle_pair("cal-bottom-circle.png", "Bottom camera: circle on the INNER opening of the tip",
                "inner dark opening", "outer edge of the tip", 26, 62, 62)
    logs = sys.argv[1] if len(sys.argv) > 1 else None
    if logs:
        camera_picture(os.path.join(logs, "look-visual-home-094446.png"), "cal-home-free.png",
                       "Visual home free: OK to home", GREEN)
        camera_picture(os.path.join(logs, "ocal-home-after-160149.png"), "cal-home-disc.png",
                       "Target ON the visual home: NEVER home now", RED)
        camera_picture(os.path.join(logs, "ocal-park-after-160213.png"), "cal-disc-park.png",
                       "Target at its park spot (correct)", GREEN)


if __name__ == "__main__":
    main()
