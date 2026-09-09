"""Original parametric research block, not an industrial drafting standard.

Coordinates: x across fabric, y along grain, mm. Curves are sampled quadratic
Bezier arcs. Sleeve cap halves are solved against the actual body armscye arcs;
seam matching is checked before seam allowance, then shared shrink is applied.
"""
import math
import numpy as np
from shapely import affinity
from shapely.geometry import Polygon, LineString, box


def length(points):
    return float(LineString(points).length)


def curve(a, control, b, n=48):
    return [((1-t)**2*np.array(a) + 2*(1-t)*t*np.array(control) + t*t*np.array(b)).tolist()
            for t in np.linspace(0, 1, n+1)]


def _piece(key, material, outline, seams, marks, slits, config):
    p = Polygon(outline)
    if not p.is_valid or p.area <= 1:
        raise ValueError(f"{key}: invalid or self-intersecting pattern")
    factor = 1 / (1 - config.design.shrink_pct/100)
    cut = p.buffer(config.design.seam_mm, join_style=2)
    if cut.geom_type != "Polygon" or not cut.is_valid:
        raise ValueError(f"{key}: seam allowance produces invalid geometry")
    cut = affinity.scale(cut, factor, factor, origin=(0, 0))
    minx, miny, _, _ = cut.bounds
    def transform(points):
        return [[round(x*factor-minx, 5), round(y*factor-miny, 5)] for x,y in points]
    poly = affinity.translate(cut, -minx, -miny)
    for path in slits + marks:
        if not p.buffer(.01).covers(LineString(path)):
            raise ValueError(f"{key}: internal path outside pattern")
    return {"id": key, "material": material, "grain": [0, 1],
            "contour": [[round(x-minx, 5), round(y-miny, 5)] for x,y in cut.exterior.coords],
            "seam_line": transform(list(p.exterior.coords)),
            "seams": {k: transform(v) for k,v in seams.items()},
            "marks": [transform(v) for v in marks], "slits": [transform(v) for v in slits],
            "area_mm2": poly.area, "width_mm": poly.bounds[2], "height_mm": poly.bounds[3]}


def draft(m, config):
    d = config.design
    shoulder = m['across_back_shoulder_width']/2
    neck = m['neck_circumference']/(2*math.pi)
    shoulder_y = math.tan(math.radians(m['shoulder_slope']))*(shoulder-neck)
    arm_y = m['armhole_depth'] + 20  # explicit block construction allowance, see notes
    waist_y = m['back_length']
    if not (neck+20 < shoulder and shoulder_y+40 < arm_y < waist_y < d.length_mm-40):
        raise ValueError('Body block: shoulder, armhole, waist and garment length are inconsistent')
    widths = {}
    bodies, arm_curves, neck_lengths = [], {}, []
    for name, sign, neck_depth in [('front', 1, neck*1.15), ('back', -1, neck*.3)]:
        # The prototype is front-minus-back contour width; divide by four to
        # distribute the difference around the common quarter circumference.
        balance = sign*m['front_back_width']/4
        chest = (m['chest_circumference']+d.chest_ease_mm)/4 + balance
        waist = (m['waist_circumference']+d.waist_ease_mm)/4 + balance
        hip = (m['hip_girth']+d.hip_ease_mm)/4 + balance
        if min(chest, waist, hip) < neck+30:
            raise ValueError(f'{name}: impossible front/back balance')
        neckline = curve([0, neck_depth], [neck, neck_depth], [neck, 0])
        arm = curve([shoulder, shoulder_y], [shoulder-15, arm_y*.8], [chest, arm_y])
        right = neckline + [[shoulder, shoulder_y]] + arm[1:] + [[waist, waist_y], [hip, d.length_mm]]
        # Reverse the right path and mirror to form a whole panel, not half on fold.
        outline = right + [[-x,y] for x,y in reversed(right)]
        side = [[chest,arm_y],[waist,waist_y],[hip,d.length_mm]]
        marks = [[[0,neck_depth+20],[0,min(d.length_mm-30,neck_depth+100)]]]
        slit = [[[0,neck_depth],[0,neck_depth+d.placket_length_mm]]] if name == 'front' else []
        bodies.append(_piece(name, 'pique', outline, {'armhole_right':arm,
            'armhole_left':[[-x,y] for x,y in arm], 'side_right':side,
            'side_left':[[-x,y] for x,y in side],
            'shoulder_left':[[-neck,0],[-shoulder,shoulder_y]],
            'neckline':[[-x,y] for x,y in reversed(neckline)]+neckline[1:],
            'hem':[[-hip,d.length_mm],[hip,d.length_mm]],
            'placket':[[0,neck_depth],[0,neck_depth+d.placket_length_mm]],
            'shoulder_right':[[neck,0],[shoulder,shoulder_y]]}, marks, slit, config))
        arm_curves[name] = arm
        widths[name] = (chest, waist, hip)
        neck_lengths.append(2*length(neckline))
    # A front/back balance offset is constant at all levels: side seams retain
    # the same shape and length despite the different panel widths.
    checks = []
    def check(name, a, b, ratio=1):
        delta = abs(a-b*ratio)
        checks.append({'name':name, 'a_mm':a, 'b_mm':b, 'ratio':ratio, 'delta_mm':delta})
        if delta > .5:
            raise ValueError(f'{name}: seam mismatch {delta:.2f} mm')
    check('body_sides', length(bodies[0]['seams']['side_right']), length(bodies[1]['seams']['side_right']))
    check('shoulders', length(bodies[0]['seams']['shoulder_right']), length(bodies[1]['seams']['shoulder_right']))
    half_width = (m['upper_arm_girth']+d.arm_ease_mm)/4
    targets = [length(arm_curves['front']), length(arm_curves['back'])]
    # Solve each cap half independently, sharing a common underarm depth by
    # adjusting the control point. Height is chosen from the shorter target.
    cap_h = min(targets)*.7
    def cap(sign, target):
        a,b = [0,0], [sign*half_width,cap_h]
        def points(bulge): return curve(a,[sign*bulge,0],b)
        lo,hi = 0., target*2
        if length(points(lo)) > target:
            raise ValueError('Sleeve: upper arm too wide for generated armhole')
        for _ in range(60):
            mid=(lo+hi)/2
            if length(points(mid)) < target: lo=mid
            else: hi=mid
        return points((lo+hi)/2)
    front_cap, back_cap = cap(-1,targets[0]), cap(1,targets[1])
    if cap_h+35 >= d.sleeve_length_mm:
        raise ValueError('Sleeve length too short for this cap; increase sleeve_length_mm')
    opening = (m['sleeve_opening_girth']+d.arm_ease_mm)/4
    sleeve_outline = list(reversed(front_cap)) + back_cap[1:] + [[opening,d.sleeve_length_mm],[-opening,d.sleeve_length_mm]]
    check('front_armhole_cap', targets[0],length(front_cap))
    check('back_armhole_cap', targets[1],length(back_cap))
    pieces = bodies
    for name,mirror in [('sleeve_left',1),('sleeve_right',-1)]:
        def mir(points): return [[x*mirror,y] for x,y in points]
        pieces.append(_piece(name,'pique',mir(sleeve_outline),
            {'cap_front':mir(front_cap),'cap_back':mir(back_cap),
             'underarm_front':mir([[-half_width,cap_h],[-opening,d.sleeve_length_mm]]),
             'underarm_back':mir([[half_width,cap_h],[opening,d.sleeve_length_mm]]),
             'opening':mir([[-opening,d.sleeve_length_mm],[opening,d.sleeve_length_mm]])},
            [mir([[0,cap_h*.7],[0,d.sleeve_length_mm-15]])],[],config))
    def rectangle(key,material,w,h):
        return _piece(key,material,[[0,0],[w,0],[w,h],[0,h]],
                      {'attach':[[0,0],[w,0]], 'long_edge':[[0,0],[0,h]]}, [[[w/2,5],[w/2,h-5]]], [], config)
    for key in ['placket_left','placket_right']:
        pieces.append(rectangle(key,'pique',2*d.placket_width_mm,d.placket_length_mm))
    collar_length = sum(neck_lengths)*d.rib_ratio
    pieces.append(rectangle('collar','rib',collar_length,2*d.collar_width_mm))
    for key in ['cuff_left','cuff_right']:
        pieces.append(rectangle(key,'rib',opening*2*d.rib_ratio,2*d.cuff_width_mm))
    check('collar_stretch_match',collar_length,sum(neck_lengths),d.rib_ratio)
    return pieces, checks, {
        'chest_mm':m['chest_circumference']+d.chest_ease_mm,
        'waist_mm':m['waist_circumference']+d.waist_ease_mm,
        'hip_mm':m['hip_girth']+d.hip_ease_mm,
        'body_length_mm':d.length_mm,'sleeve_length_mm':d.sleeve_length_mm,
        'construction':'Original symmetric polo block; armhole depth +20 mm; derived neckline and sleeve cap; rib stretch ratio is a design assumption.',
    }


def nest(pieces, config):
    """Deterministic bottom-left candidates, 0/180 only, polygon clearance.

    A window never bisects a part. Fabric usage includes both selvage margins
    and all unoccupied area inside each used rectangular roll window.
    """
    m = config.machine
    windows=[]
    for material,width in [('pique',m.fabric_width_mm),('rib',m.rib_width_mm)]:
        if width > m.bed_width_mm:
            raise ValueError(f'{material}: fabric width exceeds bed width')
        work = sorted([p for p in pieces if p['material']==material],key=lambda p:(-p['area_mm2'],p['id']))
        local=[]
        for p in work:
            polygon=Polygon(p['contour'])
            if p['width_mm']+2*m.gap_mm > width or p['height_mm']+2*m.gap_mm > m.bed_length_mm:
                raise ValueError(f"{p['id']}: entire part does not fit the fabric / cutting bed")
            placed=False
            for window in local+[None]:
                if window is None:
                    window={'id':len(windows),'material':material,'width_mm':width,'length_mm':0,'placements':[]}
                    windows.append(window);local.append(window)
                xs={m.gap_mm};ys={m.gap_mm}
                for q in window['placements']:
                    b=Polygon(q['contour']).bounds
                    xs.add(b[2]+m.gap_mm);ys.add(b[3]+m.gap_mm)
                for y,x,angle in sorted((y,x,a) for y in ys for x in xs for a in (0,180)):
                    rotated=affinity.rotate(polygon,angle,origin=(0,0))
                    minx,miny,_,_=rotated.bounds
                    candidate=affinity.translate(rotated,x-minx,y-miny)
                    if not box(m.gap_mm,m.gap_mm,width-m.gap_mm,m.bed_length_mm-m.gap_mm).buffer(.001).covers(candidate): continue
                    if any(candidate.distance(Polygon(q['contour'])) < m.gap_mm-.001 for q in window['placements']): continue
                    def transform(points):
                        line=affinity.rotate(LineString(points),angle,origin=(0,0))
                        return [[round(a,5),round(b,5)] for a,b in affinity.translate(line,x-minx,y-miny).coords]
                    q={'piece_id':p['id'],'rotation_deg':angle,'contour':transform(p['contour']),
                       'seam_line':transform(p['seam_line']),
                       'marks':[transform(v) for v in p['marks']], 'slits':[transform(v) for v in p['slits']]}
                    window['placements'].append(q)
                    window['length_mm']=max(window['length_mm'],candidate.bounds[3]+m.gap_mm)
                    placed=True;break
                if placed:break
            if not placed: raise ValueError(f"Cannot place {p['id']}")
    return windows
