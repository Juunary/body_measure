"""Encode and draw the existing fixed-appearance QR, then capture its results.

The legacy document API retains qr-configurator's role-filtered document in
memory. The Studio consumer page uses a separate, durable public summary;
it includes only QR declarations and actual captured simulation progress.
"""
from __future__ import annotations
import sqlite3

from . import events as ev
from . import paths  # noqa: F401
from . import sizing_map, passport_summary
from .jobs import Job
from .paths import RUNS
from app import codec, qrfixed, validation
from app import passport as qr_passport
from app.access import AccessPolicy, Role
from app.schemas import ACTIVE_VERSION, SCHEMAS, as_json_schema

PHASE = ev.PHASE_QR
POLICY = AccessPolicy()
STORE: dict[str, dict] = {}

_CODE_LENGTHS = sorted({spec.code_length for spec in SCHEMAS.values()}, reverse=True)


class PassportError(ValueError):
    pass


def default_config() -> dict:
    """The schema's first option per field — the same seed the configurator
    page uses before anyone touches the form."""
    config = {}
    for f in SCHEMAS[ACTIVE_VERSION].fields:
        config[f.key] = f.options[0]
    # a plausible polo: mono-material cotton, regular, 40 °C
    config.update({"fibre_1": "cotton", "fibre_1_pct": "100", "fit": "regular",
                   "wash_temp": "40"})
    for key in ("fibre_2", "fibre_3", "fibre_4"):
        if key in config:
            config[key] = "none"
    for key in ("fibre_2_pct", "fibre_3_pct"):
        if key in config:
            config[key] = "0"
    return config


def schema(lang: str) -> dict:
    doc = as_json_schema(ACTIVE_VERSION, "", lang)
    doc["x-studio-locked"] = ["size"]
    return doc


def build(job: Job, config: dict, base_url: str) -> dict:
    """Encode, draw, compose. Raises PassportError with the reason."""
    option, size_source = sizing_map.effective_qr_option(job)
    if option is None:
        view = job.size_view or {}
        raise PassportError(
            "no size for the QR: " + (view.get("qr_reason") or view.get("reason") or
                                      "measure the scan first, or override the size in settings"))
    config = {**config, "size": option}
    player = job.simulation
    if player and player.plan.get('schema_version') == 'garment-simulation/3':
        if (player.plan.get('size') or {}).get('label') != option.upper():
            raise PassportError('simulation size differs from the assigned size; regenerate the simulation before creating this QR')
    try:
        validation.validate(config, ACTIVE_VERSION)
        code = codec.encode(config, ACTIVE_VERSION)
        profile = qrfixed.profile_for(base_url.rstrip("/"))
    except (validation.ValidationError, codec.CodecError, qrfixed.ProfileError) as exc:
        raise PassportError(str(exc)) from exc
    url = qrfixed.build_url(profile, code)
    png = qrfixed.png(profile, code)
    folder = RUNS / job.id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "qr.png").write_bytes(png)

    document = qr_passport.build(config, ACTIVE_VERSION, code)
    # Keep the document viewer, not the sibling builder's fabricated production.
    for key in ('manufacturing_date', 'manufacturing_facility_id', 'production_events',
                'garment_measurements', 'recyclability_score', 'repair_instructions', 'warranty',
                'end_of_life_instructions', 'operators', 'commodity_code_hs'):
        document.pop(key, None)
    document['product_name'] = f"Research polo · {config['colour']} · {option.upper()}"
    document['product_identifier']['granularity'] = 'configuration'
    document['model_id'] = 'research-polo'
    document["customer_spec"] = sizing_map.customer_spec(job, config["fit"])
    document['customer_spec'].pop('fabric', None)
    state = player.get() if player else None
    if player:
        document["manufacturing_data"] = {
            "source": "Maß-DPP geometry manufacturing simulation",
            "is_simulation": True, "scope": player.plan['scope'],
            "pattern_status": "research_draft_unverified",
            "cutting_complete": state["cutting_complete"], "sewing_complete": state["sewing_complete"], "finished_garment": False,
            "plan_id": player.plan["plan_id"],
            "status": state["status"], "metrics": state["metrics"],
            "resources": passport_summary.public_resources(state.get('resources')),
            "size": player.plan.get('size'), "resource_model": player.plan.get('resource_model'),
            "resource_preset": player.plan['config'].get('resources'),
            "finishing": "not_executed", "quality_control": "not_executed",
        }
    elif job.replay.get("blocks"):
        document["manufacturing_data"] = {
            "source": "polo-line-sim live replay",
            "embroidery": job.replay["embroidery"], "printing": job.replay["printing"],
            "process_chain": job.replay["blocks"],
            "totals": job.replay["totals"],
        }
    try:
        summary = passport_summary.build(code, ACTIVE_VERSION, config, job,
                                         size_source, state, player.plan if player else None)
        passport_summary.save(summary)
    except (OSError, sqlite3.Error) as exc:
        raise PassportError('could not save the public passport snapshot; retry generation') from exc
    STORE[code] = {"document": document, "config": config, "job_id": job.id,
                   "profile": {"version": profile.version, "base_url": profile.base_url}}
    decoded = codec.decode(code)[1]
    withheld = POLICY.redaction_report(document, Role.PUBLIC)
    job.passport = {
        "code": code, "url": url, "config": config, "decoded": decoded,
        "size_source": size_source, "size_option": option,
        "public_summary": summary,
        "profile": {"version": profile.version, "base_url": profile.base_url,
                    "code_length": profile.code_length},
        "passport": document, "withheld_from_public": withheld,
        "png_path": str(folder / "qr.png"),
    }
    job.stage(PHASE, "passport", "start", code)
    job.line(PHASE, ev.stage_line(1, 1, "passport", f"code {code}"), "head")
    job.line(PHASE, ev.seg("      ", ("size ", "grey"), (option.upper(), "bold", "green"),
                           (f"  source {size_source}", "grey")))
    job.line(PHASE, ev.seg("      ", ("QR  ", "grey"), (url, "cyan")))
    job.line(PHASE, ev.note(f"QR version {profile.version}, ECC L, mask {qrfixed.MASK} — fixed appearance, "
                            f"{profile.code_length}-char code in the variable band"))
    job.line(PHASE, ev.note(f"passport: {len(document)} top-level fields · "
                            f"{len(withheld)} withheld from a consumer scan"))
    job.stage(PHASE, "passport", "done")
    job.emit("passport", PHASE, **{k: v for k, v in job.passport.items() if k != "png_path"})
    return job.passport


def png(code: str, base_url: str, scale: int = 8) -> bytes:
    try:
        profile = qrfixed.profile_for(base_url.rstrip("/"))
    except qrfixed.ProfileError as exc:
        raise PassportError(str(exc)) from exc
    return qrfixed.png(profile, code, scale=scale)


def decode_checked(code: str) -> tuple[str, dict]:
    try:
        version, config = codec.decode(code)
        validation.validate(config, version)
    except (codec.CodecError, validation.ValidationError) as exc:
        raise PassportError(str(exc)) from exc
    return version, config


def resolve(padded: str) -> str:
    """qr-configurator's resolver: the trailing code characters mean
    something, the padding does not."""
    for length in _CODE_LENGTHS:
        if len(padded) < length:
            continue
        code = padded[-length:]
        spec = SCHEMAS.get(code[0])
        if spec is not None and spec.code_length == length:
            decode_checked(code)
            return code
    raise PassportError("no code in URL")


def passport_for(code: str, role: Role, explain: bool) -> dict:
    stored = STORE.get(code)
    if stored is not None:
        document = stored["document"]
    else:
        version, config = decode_checked(code)
        document = qr_passport.build(config, version, code)
    payload = {"role": role.value, "passport": POLICY.filter(document, role),
               "known_to_studio": stored is not None}
    if explain:
        payload["withheld"] = POLICY.redaction_report(document, role)
    return payload
