"""`python -m body_measure index ...` — build, calibrate, query, evaluate
and export a retrieval store. Every heavy import is inside its command,
so registering the parser costs nothing.

Synthetic SMPL stores need torch and are built by
scripts/build_synthetic_db.py; this CLI only reads them."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_OK, EXIT_ERROR = 0, 1


def add_parser(sub) -> None:
    index = sub.add_parser("index", help="retrieval store: build, query, evaluate, export")
    cmds = index.add_subparsers(dest="index_command", required=True)

    build = cmds.add_parser("build", help="build a store from scans on this machine")
    build.add_argument("--db", required=True, help="store name under data/retrieval/, or a path")
    build.add_argument("--source", choices=["real", "meshes"], required=True,
                       help="real: Texel + NOMO (local-only licence); meshes: a directory")
    build.add_argument("--nomo", type=int, default=30, help="NOMO subjects for --source real")
    build.add_argument("--mesh-dir", type=Path, help="for --source meshes")
    build.add_argument("--input-unit", choices=["mm", "cm", "m"], help="for --source meshes")
    build.add_argument("--up-axis", choices=["Y", "Z"], default="Y")
    build.add_argument("--licence", choices=["local_only_licensed", "public_hsrd", "synthetic_smpl"],
                       default="local_only_licensed",
                       help="licence class of --source meshes records; defaults to the strict one")
    build.add_argument("--population", choices=["men", "women"], default=None)
    build.add_argument("--overwrite", action="store_true")

    merge = cmds.add_parser("merge", help="a new store holding the records of several")
    merge.add_argument("--db", required=True)
    merge.add_argument("--from", dest="sources", nargs="+", required=True)
    merge.add_argument("--overwrite", action="store_true")

    cal = cmds.add_parser("calibrate", help="fit and save the abstention threshold")
    cal.add_argument("--db", required=True)
    cal.add_argument("--k", type=int, default=15)

    info = cmds.add_parser("info", help="print a store's manifest summary")
    info.add_argument("--db", required=True)

    query = cmds.add_parser("query", help="size a scan by its nearest reference bodies")
    query.add_argument("--db", required=True)
    query.add_argument("mesh", type=Path)
    query.add_argument("--input-unit", choices=["mm", "cm", "m"], required=True)
    query.add_argument("--up-axis", choices=["Y", "Z"], default="Y")
    query.add_argument("--population", choices=["men", "women"], default=None)
    query.add_argument("--size-chart", choices=["en13402", "en13402-women", "lacoste"],
                       default="en13402")
    query.add_argument("--k", type=int, default=None)
    query.add_argument("--skip-pose-gate", action="store_true")
    query.add_argument("--encoder", type=Path, default=None,
                       help="ONNX encoder: the query vector is the encoder's prediction "
                            "from surface points instead of the pipeline's measurement; "
                            "the way to query a CLOTHED scan without torch")
    query.add_argument("--format", choices=["table", "json"], default="table")

    ev = cmds.add_parser("eval", help="agreement of retrieval with the pipeline, per track")
    ev.add_argument("--db", required=True)
    ev.add_argument("--track", choices=["real", "synthetic"], required=True,
                    help="real: leave-one-subject-out over the real records; "
                         "synthetic: the store's holdout split")
    ev.add_argument("--k", type=int, default=None)
    ev.add_argument("--reports-dir", type=Path, default=Path("reports"))

    export = cmds.add_parser("export", help="copy a store elsewhere; refuses licensed records")
    export.add_argument("--db", required=True)
    export.add_argument("--dest", type=Path, required=True)


def run(args: argparse.Namespace) -> int:
    from .store import StoreError

    handler = {
        "build": _build, "merge": _merge, "calibrate": _calibrate, "info": _info,
        "query": _query, "eval": _eval, "export": _export,
    }[args.index_command]
    try:
        return handler(args)
    except (StoreError, ValueError, FileNotFoundError) as exc:
        # ValueError: a store too small to calibrate, a feature space the
        # encoder was not trained in; said plainly, not as a traceback
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


# ------------------------------------------------------------------ build --
def _build(args) -> int:
    from ..spec import load_spec
    from .features import FEATURE_SPACE_VERSION
    from .ingest import measure_mesh, record_from_measured
    from .record import RECORD_SCHEMA_VERSION, LicenceClass
    from .store import RecordStore
    from .versioning import pipeline_hash

    spec = load_spec()
    phash = pipeline_hash(feature_space_version=FEATURE_SPACE_VERSION,
                          record_schema_version=RECORD_SCHEMA_VERSION)
    if args.source == "real":
        from .sources import real_subjects

        items = ((sid, pop, mesh, LicenceClass.LOCAL_ONLY, "dataset_scan")
                 for sid, pop, mesh in real_subjects(args.nomo))
        note = "Texel Part1 + NOMO male, unclothed A-pose; local-only licence"
    else:
        if not args.mesh_dir or not args.input_unit:
            print("error: --source meshes needs --mesh-dir and --input-unit", file=sys.stderr)
            return EXIT_ERROR
        items = _mesh_dir_items(args)
        note = f"meshes from {args.mesh_dir}"

    store = RecordStore.create(args.db, note=note, overwrite=args.overwrite)
    skipped = []
    for sid, population, mesh, licence, source_type in items:
        m = measure_mesh(mesh)
        if m is None:
            skipped.append(sid)
            print(f"  skip {sid}: pose gate refused", file=sys.stderr)
            continue
        store.append(record_from_measured(
            m, record_id=sid, source_type=source_type, source_id=sid, licence_class=licence,
            population=population, spec_version=spec.version, pipeline_hash=phash))
        print(f"  {sid}", file=sys.stderr)
    if not len(store):
        print("error: no scan produced a record", file=sys.stderr)
        return EXIT_ERROR
    store.manifest["skipped_pose_gate"] = skipped
    store.save()
    print(f"{len(store)} records -> {store.path}  ({len(skipped)} refused by the pose gate)")
    return EXIT_OK


def _mesh_dir_items(args):
    from ..adapters.mesh_file import MeshFileAdapter
    from ..canonicalize import canonicalize
    from .record import LicenceClass

    adapter = MeshFileAdapter()
    for path in sorted(p for p in args.mesh_dir.iterdir()
                       if p.suffix.lower() in (".obj", ".ply", ".stl")):
        mesh = canonicalize(adapter.load(path, unit=args.input_unit), up_axis=args.up_axis)
        yield (path.stem, args.population, mesh, LicenceClass(args.licence), "mesh_file")


def _merge(args) -> int:
    from .store import RecordStore

    stores = [RecordStore.open(name) for name in args.sources]
    out = RecordStore.merged(args.db, stores, overwrite=args.overwrite,
                             note="merge of " + ", ".join(s.db_name for s in stores))
    out.save()
    print(f"{len(out)} records -> {out.path}")
    return EXIT_OK


def _calibrate(args) -> int:
    from .calibration import fit_calibration
    from .store import RecordStore

    store = RecordStore.open(args.db)
    before = store.space.version if store.space else None
    # the space is refitted with this code's keys first, so the threshold
    # is taken in the space queries will use
    store.save(refit=True)
    cal = fit_calibration(store, k=args.k)
    path = store.save_calibration(cal.to_dict())
    if before != store.space.version:
        print(f"feature space {before} -> {store.space.version}")
    print(f"index keys {', '.join(store.space.index_keys)}")
    print(f"threshold {cal.threshold:.3f}  sigma {cal.sigma:.3f}  k {cal.k}  "
          f"on {cal.n} records ({cal.split_used}) -> {path}")
    return EXIT_OK


def _info(args) -> int:
    from .store import RecordStore

    store = RecordStore.open(args.db)
    keep = ("db_name", "note", "n_records", "n_by_licence_class", "n_by_split",
            "n_by_source_type", "n_by_population", "pipeline_hash", "updated_utc")
    print(json.dumps({k: store.manifest.get(k) for k in keep}, indent=2, ensure_ascii=False))
    print("stale flags:", store.check_against_current() or "none")
    cal = store.load_calibration()
    print("calibration:", "none" if cal is None else
          f"threshold {cal['threshold']:.3f}, k {cal['k']}, n {cal['n']}")
    return EXIT_OK


# ------------------------------------------------------------------ query --
def _query(args) -> int:
    from ..adapters.mesh_file import MeshFileAdapter
    from ..canonicalize import canonicalize
    from .. import sizing
    from ..charts import ita_he_26
    from .calibration import load_or_fit
    from .estimator import query_from_measurements, estimate
    from .ingest import measure_mesh
    from .store import RecordStore

    store = RecordStore.open(args.db)
    flags = store.check_against_current()
    cal, cal_flags = load_or_fit(store)
    mesh = canonicalize(MeshFileAdapter().load(args.mesh, unit=args.input_unit),
                        up_axis=args.up_axis)
    chart = sizing.CHARTS[args.size_chart]
    if args.encoder is not None:
        from .onnx_query import OnnxEncoder
        from .points import sample_surface
        from ..pose_gate import check_pose

        if not args.skip_pose_gate and not check_pose(mesh).ok:
            print("error: the scan is not a standing A pose (--skip-pose-gate overrides)",
                  file=sys.stderr)
            return EXIT_ERROR
        encoder = OnnxEncoder(args.encoder)
        encoder.check_space(store.space)
        predicted = encoder(sample_surface(mesh))
        values = dict(predicted.values)
        usable = {k: True for k in values}
        query_pathway = "encoder_predicted_body"
        flags.append("query_vector_is_an_encoder_prediction")
        direct = sizing.SizeAssignment(
            chart, None, None, reason="no direct size: the query was not measured, it was "
                                      "predicted by the encoder", flags=["encoder_query"])
    else:
        m = measure_mesh(mesh, check_pose=not args.skip_pose_gate)
        if m is None:
            print("error: the scan is not a standing A pose (--skip-pose-gate overrides)",
                  file=sys.stderr)
            return EXIT_ERROR
        values, usable = query_from_measurements(m.measurements, m.prototypes, m.stature_mm)
        query_pathway = "estimated"
        direct = sizing.assign(m.measurements, chart=chart, population=args.population)
    est = estimate(store, store.index(), cal, values, usable, population=args.population,
                   k=args.k, query_pathway=query_pathway, extra_flags=flags + cal_flags)
    retrieved = est.to_size_assignment(chart, population=args.population,
                                       chest_mm=values.get("chest_circumference"))
    shirt = ita_he_26.nearest_size(values, usable)
    out = {"retrieval": est.to_dict(), "size_retrieved": retrieved.to_dict(),
           "size_direct": direct.to_dict(), "ita_he_26_direct": shirt.to_dict()}
    if args.format == "json":
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        return EXIT_OK
    print(f"\nstore {store.db_name}: {len(store)} records, k={est.k}, "
          f"threshold {est.threshold:.3f}")
    if est.abstained:
        print(f"ABSTAINED — {est.abstain_reason}")
    else:
        print(f"nearest {est.nearest_distance:.3f}")
        for n in est.neighbours[:5]:
            print(f"  {n.record_id:28s} d={n.distance:.3f} w={n.weight:.2f}  "
                  f"{n.size_labels.get(chart.key)}  {n.licence_class}")
        own = "predicted" if args.encoder is not None else "measured"
        print(f"\n{'key':28s} {own:>9s} {'retrieved':>10s} {'spread':>8s}")
        for key in store.space.keys:
            own = values.get(key)
            got, sp = est.values.get(key), est.spread.get(key)
            print(f"{key:28s} {('—' if own is None else f'{own:9.1f}'):>9s} "
                  f"{('—' if got is None else f'{got:10.1f}'):>10s} "
                  f"{('—' if sp is None else f'{sp:8.1f}'):>8s}")
        print(f"\nvotes {chart.key}: {est.size_votes.get(chart.key)}")
        print(f"votes ita_he_26: {est.size_votes.get('ita_he_26')}")
    print(f"\nsize by retrieval: {retrieved.label}  ({retrieved.reason})")
    print(f"size by chest girth (authority on an unclothed scan): {direct.label}  "
          f"({direct.reason})")
    print(f"ITA_HE_26 nearest row: {shirt.size}  ({shirt.reason})")
    for flag in est.flags:
        print(f"  flag: {flag}")
    return EXIT_OK


# ------------------------------------------------------------------- eval --
def _eval(args) -> int:
    from .calibration import fit_calibration
    from .evaluate import markdown, run_track
    from .record import LicenceClass
    from .store import RecordStore

    store = RecordStore.open(args.db)
    if args.track == "real":
        queries = [r for r in store.records if r.source_type != "synthetic_smpl"]
    else:
        queries = store.filter(split="holdout")
    if not queries:
        print(f"error: the store has no queries for the {args.track} track", file=sys.stderr)
        return EXIT_ERROR
    # calibrated afresh so the threshold is the one the track's split rule
    # gives (train when the store has one), not whatever was saved
    cal = fit_calibration(store, k=args.k or 15)

    def progress(i, n):
        if i % 50 == 0 or i == n:
            print(f"  {i}/{n}", file=sys.stderr)

    result = run_track(store, cal, args.track, queries, k=args.k, progress=progress)
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"retrieval_eval_{store.db_name}_{args.track}"
    (args.reports_dir / f"{stem}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md = markdown(result)
    if any(r.licence_class == LicenceClass.LOCAL_ONLY for r in store.records):
        md += ("\nThis store holds local-only licensed records (Texel, NOMO, CAPE); "
               "per-record rows stay in the JSON, which reports/ keeps out of git.\n")
    (args.reports_dir / f"{stem}.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"wrote {args.reports_dir / stem}.{{json,md}}")
    return EXIT_OK


def _export(args) -> int:
    from .store import LicenceExportError, RecordStore

    store = RecordStore.open(args.db)
    try:
        dest = store.export(args.dest)
    except LicenceExportError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"{len(store)} records exported -> {dest}")
    return EXIT_OK
