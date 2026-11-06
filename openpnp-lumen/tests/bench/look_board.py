# camera only: homing fiducial (middle of the bed), 2 cm to its right, the 4 board fiducials (job board location)
import math
look("homing-fid", 218.18, 197.36, 0.0)
look("homing-fid+20x", 238.18, 197.36, 0.0)
bx, by, br = 281.87061927526315, 95.5251955507456, -0.9332188672243589
a = math.radians(br)
for name, x, y in (("REF_1", 12.0, 3.85), ("REF_2", 88.9202, 3.85), ("REF_3", 88.9202, 104.5), ("REF_4", 12.0, 104.5)):
    look("board-" + name, bx + x * math.cos(a) - y * math.sin(a), by + x * math.sin(a) + y * math.cos(a), 0.0)
