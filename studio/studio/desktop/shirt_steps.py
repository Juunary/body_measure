"""Measured men's-shirt work steps ("Arbeitsschritte Herrenhemd", total 42:35).

Every row of the source table is kept, including the ironing steps, so they can
be restored later. Ironing is skipped for now; the remaining timed rows total
exactly 1811 s (30:11). Rows without a measured time (fusing, cutting the top
collar, buttonholes and buttons) are recorded but not scheduled here; the
button chapter still covers rows 33-34 with its own research timings.

`seam_ids` links a step to the polo pattern seams it closes. Each of the 18
seams is closed by exactly one step; collar-construction and overlock rows have
no matching polo seam and run as timed operations without seam geometry.
"""

# (no, step, tool, measured seconds or None, stitch length mm or None, seams closed)
STEPS = (
    (1, "Stoff für Oberkragen mit Einlage G710 verstärken", "Fixierpresse", None, None, ()),
    (2, "Oberkragen zuschneiden", "Schere", None, None, ()),
    (3, "Verstärkten Oberkragen mit Einlage G700 verstärken", "Fixierpresse", None, None, ()),
    (4, "Knopfleiste (li. VT) mit Einlage G710 verstärken", "Fixierpresse", None, None, ()),
    (5, "Ober- und Unterkragen an der Oberkante verstürzen", "Nähmaschine", 22, 2.5, ()),
    (6, "Naht ausbügeln, Nahtzugabe in den Unterkragen bügeln", "Bügelanlage", 8, None, ()),
    (7, "Kragensteg Oberkragen Nahtzugabe umbügeln", "Bügelanlage", 16, None, ()),
    (8, "Kragensteg Oberkragen Nahtzugabe von rechts absteppen 0,4 cm", "Nähmaschine", 21, 3, ()),
    (9, "Naht von rechts 1,5 mm breit absteppen", "Nähmaschine", 18, 3, ()),
    (10, "Kragenseiten und Steg rechts auf rechts verstürzen", "Nähmaschine", 79, 2.5, ()),
    (11, "Kragenecken schräg zurückschneiden, Kragen wenden", "Schere", 47, None, ()),
    (12, "Ecken ausformen", "Pfriem", 54, None, ()),
    (13, "Kragen bügeln", "Bügelanlage", 80, None, ()),
    (14, "Passe an Rückenteil arbeiten", "Nähmaschine", 105, 2.5, ()),
    (15, "Passe an die beiden Vorderteile arbeiten", "Nähmaschine", 190, 2.5,
     ("shoulder_left", "shoulder_right")),
    (16, "Passen – Nähte flach bügeln", "Bügelanlage", 20, None, ()),
    (17, "Knopfleiste an beiden Vorderteilen umbügeln (2 x 3,5 cm)", "Bügelanlage", 83, None, ()),
    (18, "Knopfleiste an beiden Vorderteilen absteppen 3,3 cm", "Nähmaschine", 93, 3,
     ("placket_left", "placket_right")),
    (19, "Seiten- und Unterärmelnähte schließen", "Nähmaschine", 184, 2.5,
     ("side_left", "underarm_left", "side_right", "underarm_right")),
    (20, "Seiten- und Unterärmelnähte versäubern", "Kettelmaschine", 80, None, ()),
    (21, "Seiten- und Unterärmelnähte flach bügeln", "Bügelanlage", 60, None, ()),
    (22, "Ärmelsäume bügeln 1 cm & 3,2 cm", "Bügelanlage", 150, None, ()),
    (23, "Ärmelsäume absteppen 3 cm", "Nähmaschine", 66, 3, ("cuff_left", "cuff_right")),
    (24, "2 x Ärmel in Armloch stecken und Armloch nähen", "Nähmaschine", 361, 2.5,
     ("armhole_left_front", "armhole_left_back", "armhole_right_front", "armhole_right_back")),
    (25, "2 x Armloch versäubern", "Kettelmaschine", 80, None, ()),
    (26, "Ärmelnähte überbügeln", "Bügelanlage", 50, None, ()),
    (27, "Saum bügeln 2 x 0,7 cm", "Bügelanlage", 105, None, ()),
    (28, "Saum absteppen 0,6 cm", "Nähmaschine", 68, None, ("hem_front", "hem_back")),
    (29, "Kragen auf Rumpf steppen 0,5 cm", "Nähmaschine", 160, 2.5, ("collar_front", "collar_back")),
    (30, "Kragen bügeln, Nahtzugabe in den Kragen bügeln", "Bügelanlage", 22, None, ()),
    (31, "Oberkragen am Ansatz 0,1 cm breit aufsteppen", "Nähmaschine", 97, 3, ()),
    (32, "Kragenkanten absteppen 0,1 cm", "Nähmaschine", 86, 3, ()),
    (33, "Knopflöcher auf der linken Knopfleiste arbeiten", "Knopflochautomat", None, None, ()),
    (34, "Knöpfe annähen", "Knopfautomat", None, None, ()),
    (35, "Endbügeln", "Bügelanlage", 150, None, ()),
)

# Intermediate and final pressing, skipped for now (744 s in total).
IRONING = frozenset((6, 7, 13, 16, 17, 21, 22, 26, 27, 30, 35))

# Tool -> (operation kind, simulated station). Hand work stays at the lockstitch table.
TOOLS = {
    "Nähmaschine": ("stitch", "pfaff"),
    "Kettelmaschine": ("stitch", "overlock"),
    "Schere": ("hand_work", "pfaff"),
    "Pfriem": ("hand_work", "pfaff"),
}

# Row 28 gives no stitch length; the table's other topstitching uses 3 mm.
DEFAULT_STITCH_MM = 3.


def rows():
    """All table rows with their scheduling decision."""
    return [{"no": no, "name": name, "tool": tool, "duration_s": seconds,
             "stitch_length_mm": stitch_mm, "seam_ids": list(seams),
             "ironing": no in IRONING,
             "scheduled": seconds is not None and no not in IRONING}
            for no, name, tool, seconds, stitch_mm, seams in STEPS]
