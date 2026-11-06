# camera only: 3 x 3 mosaic right of the homing fiducial (x 222..258, y 187..208)
for j, y in enumerate((207.5, 197.36, 187.2)):
    for i, x in enumerate((222.0, 240.0, 258.0)):
        look("survey-%d%d" % (j, i), x, y, 0.0)
