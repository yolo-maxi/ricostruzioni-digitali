from fontTools.pens.ttGlyphPen import TTGlyphPen

from shapely.geometry import Polygon

from shapely.ops import unary_union

def close_voids(shape, min_area):
    """Close holes smaller than ``min_area`` square units. In this heavy
    lettering such a hole is a void in the printed ink, not a counter."""
    polys = [shape] if shape.geom_type == "Polygon" else list(shape.geoms)
    return unary_union([Polygon(p.exterior, [h for h in p.interiors if Polygon(h).area >= min_area])
                        for p in polys])

def glyph_from_curves(contours):
    pen = TTGlyphPen(None)
    for c in contours:
        if not c[0][2]:                         # no on-curve point at all (a ring)
            pen.qCurveTo(*[(x, y) for x, y, _ in c], None)
            pen.closePath()
            continue
        pen.moveTo(c[0][:2])
        run = []
        for x, y, on in c[1:]:
            if on:
                if run:
                    pen.qCurveTo(*run, (x, y))
                else:
                    pen.lineTo((x, y))
                run = []
            else:
                run.append((x, y))
        if run:
            pen.qCurveTo(*run, c[0][:2])
        pen.closePath()
    return pen.glyph()

def shape_dice(a, b):
    return 2.0 * a.intersection(b).area / (a.area + b.area)
