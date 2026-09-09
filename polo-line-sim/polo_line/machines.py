# -*- coding: utf-8 -*-
"""2. 스마트 팩토리에 요구되는 기계.

계획서 표 3(Seite 37)의 설비군을 기준으로 하고, 폴로(니트) 때문에 추가되는 설비와
Seite 27~28 · 38 의 공정 인프라를 함께 정리한다.

쪽 번호는 문서 자체의 "Seite N von 55" 기준이다. PDF 뷰어의 쪽 번호는 여기에
4를 더한 값이다(Seite 37 = PDF 41쪽). 보고서에 인용할 때 Seite 를 쓴다.
"""
from __future__ import annotations

from . import term
from .spec import SENSOR_CHANNELS, SENSOR_HZ, STATIONS

# 색상은 term.init() 이후에 결정되므로 라벨은 호출 시점에 만든다.
ORIGIN_STYLE = {
    "plan": ("named in table 3", "blue"),
    "unspec": ("unspecified", "yellow"),
    "option": ("optional", "grey"),
}


def origin_label(origin: str) -> str:
    text, style = ORIGIN_STYLE[origin]
    return term.c(text, style)


# 설비 표의 묶음. (제목, 부연, 해당 기계 키)
GROUPS = (
    ("Machines table 3 names outright", "", ("cut", "lock", "fin", "qc", "emb", "prn")),
    ("Machines knit sewing needs that table 3 leaves unspecified",
     "Table 3 says only “Spezialisierte Pfaff Nähmaschinen” — plural, no stitch type — and "
     "buttons and DPP labelling appear in the process description (Seite 25, 38) with no "
     "machine of their own. These are unspecified, not excluded.",
     ("ovl", "cov", "rib", "btn", "lbl")),
)

INFRASTRUCTURE = [
    ("Transport and robotics", "moves work between modules",
     "Seite 27 — robot and transport systems built in alongside the machines"),
    ("Sensor system", f"{SENSOR_HZ:.0f} Hz · about {SENSOR_CHANNELS} channels per module (count assumed)",
     "Seite 37, 38 — analogue and digital machine signals captured in real time (<1 s)"),
    ("AI assistant", "ideal process variables identified in <2 s",
     "Seite 39 — invertible neural network, projection onto the fabric"),
    ("DPP label unit", "QR printing, SaaS hand-off",
     "Seite 38 — the product is labelled once quality control passes"),
]


def report(verbose: bool = False) -> None:
    term.section("2", "Machines the smart factory needs")
    print()

    for group, caption, keys in GROUPS:
        print(term.c(f"   {group}", "bold"))
        if caption:
            term.note(caption)
        rows = []
        for st in STATIONS:
            if st.key not in keys:
                continue
            rows.append([
                st.machine,
                st.role,
                f"{st.minutes:.1f} min",
                f"{st.kw:.2f} kW",
                origin_label(st.origin),
            ])
        term.table(["Machine", "Role", "Time", "Rated", "Source"], rows,
                   aligns=["left", "left", "right", "right", "left"])
        print()

    print(term.c("   Process infrastructure", "bold"))
    term.table(["Component", "Specification", "Where the plan says so"],
               [[name, value, note] for name, value, note in INFRASTRUCTURE])

    print()
    base = sum(st.minutes for st in STATIONS if not st.optional)
    extra = sum(st.minutes for st in STATIONS if st.optional)
    term.kv("Base line", f"{base:.1f} min across {sum(1 for s in STATIONS if not s.optional)} modules")
    term.kv("With both options", f"+{extra:.1f} min (embroidery and print)")

    if verbose:
        print()
        print(term.c("   What each module measures", "bold"))
        for st in STATIONS:
            names = " · ".join(f"{lb} ({unit})" if unit else lb for lb, unit, _ in st.readouts)
            print(f"     {term.pad(st.machine, 26)} {term.c(names, 'grey')}")
