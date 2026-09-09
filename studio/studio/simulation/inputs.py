"""Read body_measure's public JSON without mutating its quality decisions."""
import math
from .config import REQUIRED, SimulationConfig


class InputError(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__("; ".join(f"{x['key']}: {x['reason']}" for x in issues))


def size_defaults(document):
    """Only chest is chart-defined; other values are explicit research defaults."""
    from .. import paths  # bootstrap body_measure
    from body_measure.sizing import CHARTS
    size = document.get('sizing') or document.get('meta',{}).get('size') or {}
    if not isinstance(size, dict): return {}
    chart = CHARTS.get(size.get('chart'))
    if chart is None or chart.dimension_kind != 'body': return {}
    band = next((b for b in chart.bands if b.label == size.get('size')), None)
    if band is None: return {}
    chest = (band.chest_min_cm + band.chest_max_cm) * 5
    # Versioned proportional polo block, not additional EN/ISO measurements.
    values = dict(chest_circumference=chest,waist_circumference=chest*.86,
                  neck_circumference=chest*.39,across_back_shoulder_width=chest*.44,
                  back_length=chest*.45,upper_arm_girth=chest*.33,hip_girth=chest,
                  sleeve_opening_girth=chest*.30,armhole_depth=chest*.21,
                  shoulder_slope=12.,front_back_width=0.)
    return {k:{'value':round(v,3),'source':'size_chart' if k=='chest_circumference' else 'size_preset',
               'basis':f"{chart.key} / {band.label}; "+('body chest band midpoint' if k=='chest_circumference' else 'polo-size-fallback/1 research assumption')}
            for k,v in values.items()}


def inspect_inputs(document: dict, config: SimulationConfig) -> list[dict]:
    if not isinstance(document,dict) or not isinstance(document.get('measurements',{}),dict) or not isinstance(document.get('meta',{}),dict):
        raise InputError([{'key':'document','reason':'expected a body_measure JSON object with measurements and meta objects'}])
    measurements = document.get("measurements", {})
    prototypes = document.get("meta", {}).get("garment_prototypes", {})
    if not isinstance(prototypes,dict):raise InputError([{'key':'garment_prototypes','reason':'expected an object'}])
    rows = []
    defaults = size_defaults(document)
    unknown = set(config.manual) - set(REQUIRED)
    if unknown:
        raise InputError([{"key": k, "reason": "unknown manual measurement"} for k in sorted(unknown)])
    for key, (unit, low, high) in REQUIRED.items():
        original = measurements.get(key) or prototypes.get(key) or {}
        if not isinstance(original,dict):raise InputError([{'key':key,'reason':'expected a measurement object with value and quality'}])
        value = original.get("selected_value_mm", original.get("value"))
        source = "measurement" if key in measurements else "prototype" if key in prototypes else "missing"
        # Core JSON's unit is stated at document level; prototype angles carry their unit.
        actual_unit = original.get("unit", document.get("units") if source == "measurement" else unit)
        flags = original.get("quality", original.get("flags", []))
        reason = ""
        if source == "measurement":
            from .. import paths  # bootstrap the existing source of quality decisions
            from body_measure.result import MeasurementValue
            from body_measure.validate.stats import quality_bucket
            fields = MeasurementValue.__dataclass_fields__
            bucket = quality_bucket(MeasurementValue(**{k:v for k,v in original.items() if k in fields}))
            if bucket not in ('clean', 'arm_clipped'):
                reason = f"{bucket}: supply a manual research input"
        if document.get("pathway", document.get("meta", {}).get("pathway")) == "measured_clothed" and source == "measurement":
            reason = "clothed measurement: supply a manual body value"
        if key in config.manual:
            manual = config.manual[key]
            value, actual_unit, source, reason = manual.value, manual.unit, "manual", ""
        if actual_unit != unit:
            reason = f"expected {unit}, received {actual_unit}"
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            reason = "missing or non-finite value; enter a manual value"
        elif not low <= value <= high:
            reason = f"outside research input range {low}–{high} {unit}"
        auto_basis = None
        if key not in config.manual and key in defaults and value is None and reason == 'missing or non-finite value; enter a manual value' and actual_unit in (None,unit):
            fallback = defaults[key]
            if low <= fallback['value'] <= high:
                value, source, reason = fallback['value'], fallback['source'], ''
                auto_basis = fallback['basis']
        rows.append({"key": key, "value": value, "unit": unit, "source": source,
                     "auto_basis": auto_basis,
                     "original": original, "flags": flags, "usable": not reason,
                     "reason": reason, "manual_reason": config.manual[key].reason if key in config.manual else None})
    return rows


def resolve_inputs(document, config):
    rows = inspect_inputs(document, config)
    issues = [r for r in rows if not r["usable"]]
    if issues:
        raise InputError(issues)
    return {r["key"]: float(r["value"]) for r in rows}, rows
