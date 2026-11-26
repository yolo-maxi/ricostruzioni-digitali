"""Balilla Type Lab reconstruction pipeline.

Stages (each stage is deterministic and reads only checked-in inputs):

1. ``rectify``   photo plane geometry: line features -> homography per photo.
2. ``segment``   text blocks -> glyph occurrences (the evidence map).
3. ``trace``     occurrences -> consensus masks -> Bezier outlines (UFO).
4. ``build``     UFO -> TTF and WOFF2 (see ``build_font.py``).
5. ``evaluate``  built font vs. source occurrences -> metrics, overlays, gates.
"""
