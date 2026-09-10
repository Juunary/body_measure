"""Reproducible 1,000-garment performance and equivalence report (public deps only)."""
import argparse
import ctypes
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import random
import sys
import time
import numpy as np
from . import simulate, Replay, save, load
from .__main__ import scenario_file
from .storage import atomic_text


def peak_rss_bytes():
    if sys.platform == 'win32':
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),
                        ('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),
                        ('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),
                        ('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),
                        ('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t)]
        data=Counters();data.cb=ctypes.sizeof(data)
        get_process=ctypes.windll.kernel32.GetCurrentProcess
        get_process.restype=wintypes.HANDLE
        get_info=ctypes.windll.psapi.GetProcessMemoryInfo
        get_info.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        if not get_info(get_process(),ctypes.byref(data),data.cb): raise ctypes.WinError()
        return int(data.PeakWorkingSetSize)
    import resource
    maximum=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(maximum if sys.platform=='darwin' else maximum*1024)


def equivalence(data):
    from copy import deepcopy
    one=deepcopy(data);one['orders']=[{'id':'equivalence','quantity':1}];one['factory']={}
    run=simulate(one);new=run['result']['resources'];old=run['template']['totals']['resources']
    rates=run['scenario']['config']['resources'];transfer=run['scenario']['factory']['transport_s']
    energy=-transfer*rates['pfaff_idle_kw']/3600
    equipment=-transfer*rates['pfaff_eur_h']/3600
    expected={'duration_s':0.,'energy_kwh':energy,'co2e_g':energy*rates['grid_gco2e_kwh'],
              'cost_eur':equipment+energy*rates['electricity_eur_kwh'],
              'labour_time_s':0.,'thread_used_m':0.}
    old={**old,'duration_s':run['template']['totals']['duration_s']}
    new={**new,'duration_s':run['duration_s']}
    rows={key:{'legacy':old[key],'factory':new[key],'actual_delta':new[key]-old[key],'expected_delta':delta}
          for key,delta in expected.items()}
    for row in rows.values():
        if not np.isclose(row['actual_delta'],row['expected_delta'],rtol=1e-9,atol=1e-6):
            raise AssertionError('single-garment accounting equivalence failed')
    return rows


def run_benchmark(artifact):
    root=Path(__file__).resolve().parents[2]
    data=scenario_file(root/'examples/factory-scenario.json')
    eq=equivalence(data)
    data['orders']=[{'id':'scale','quantity':1000}]
    data['factory'].update(zund=2,pfaff=4,cutting_workers=1,sewing_workers=4,
                           transport_workers=1,carts=1,batch_size=5,buffer_capacity=10)
    began=time.perf_counter();run=simulate(data);build_s=time.perf_counter()-began
    began=time.perf_counter();save(artifact,run);save_s=time.perf_counter()-began
    event_count=len(run['events']);row_count=len(run['rows']);checkpoint_count=len(run['checkpoints'])
    total=run['result'];content_hash=run['content_hash'];duration=run['duration_s']
    size=Path(artifact).stat().st_size
    del run
    began=time.perf_counter();run=load(artifact);load_s=time.perf_counter()-began
    if run['content_hash'] != content_hash: raise AssertionError('save/load content changed')
    player=Replay(run);rng=random.Random(20260910)
    queries=[rng.uniform(0,duration) for _ in range(1050)]
    for t in queries[:50]:player.snapshot(t,'scale:0500')
    samples=[];replayed=[]
    for t in queries[50:]:
        began=time.perf_counter();player.snapshot(t,'scale:0500')
        samples.append((time.perf_counter()-began)*1000);replayed.append(player.applied_last)
    final=player.snapshot(duration,'scale:0500')
    if final['counts'] != {'complete':1000}:raise AssertionError('not all garments completed')
    source=hashlib.sha256()
    for folder in (root/'studio/factory',root/'studio/simulation'):
        for path in sorted(folder.glob('*.py')):
            source.update(path.name.encode());source.update(path.read_bytes())
    return {'schema_version':'factory-benchmark/1','source_sha256':source.hexdigest(),
            'environment':{'platform':platform.platform(),'processor':platform.processor(),'python':platform.python_version(),
                           'dependencies':{name:version(name) for name in ('simpy','numpy','shapely','pydantic')}},
            'scenario':{'quantity':1000,'factory':data['factory'],'seed':20260910,'warmup':50,'queries':1000},
            'build_s':build_s,'save_s':save_s,'load_verify_s':load_s,'artifact_bytes':size,
            'peak_process_rss_bytes':peak_rss_bytes(),
            'memory_scope':'OS whole-process high-water resident set, including imports, build, JSON IO and replay',
            'domain_events':event_count,'segments_including_waits':row_count,'checkpoints':checkpoint_count,
            'query_ms':{'p50':float(np.percentile(samples,50)),'p95':float(np.percentile(samples,95)),
                        'max':max(samples)},'max_events_replayed':max(replayed),'p95_target_ms':50,
            'passed':bool(np.percentile(samples,95)<50 and max(replayed)<=255),
            'content_hash':content_hash,'single_garment_equivalence':eq,
            'research_result':{k:total[k] for k in ('completed_garments','makespan_s','throughput_per_hour','resources')}}


def report_text(result):
    env=result['environment']; q=result['query_ms']
    lines=['# Factory phase 1 — measured benchmark and equivalence','',
           'Synthetic research simulation; no actual manufactured-product claim.','',
           f"Environment: {env['platform']}; {env['processor']}; Python {env['python']}.",
           'Dependencies: '+', '.join(f'{k} {v}' for k,v in env['dependencies'].items())+'.','',
           'The workload is 1,000 identical polos: 2 cutters / 1 cutting worker, 4 Pfaff / 4 sewing workers,',
           '1 transport worker / cart, batches of 5, sewing buffer capacity 10. Geometry is compiled once.',
           'The 1,000 queries select one garment plus the whole-factory summary at random timestamps after 50 warmups.','',
           '| Measurement | Observed |','| --- | --- |',
           f"| Compute run | {result['build_s']:.3f} s |",f"| Save / load and verify | {result['save_s']:.3f} / {result['load_verify_s']:.3f} s |",
           f"| Domain events / segments including waits | {result['domain_events']} / {result['segments_including_waits']} |",
           f"| Checkpoints | {result['checkpoints']} |",f"| Artifact | {result['artifact_bytes']/1024**2:.2f} MiB |",
           f"| Peak process resident memory | {result['peak_process_rss_bytes']/1024**2:.2f} MiB |",
           f"| Query p50 / p95 / max | {q['p50']:.3f} / {q['p95']:.3f} / {q['max']:.3f} ms |",
           f"| Max replayed events after checkpoint | {result['max_events_replayed']} |",
           f"| p95 < 50 ms | {'PASS' if result['passed'] else 'FAIL'} |",'',
           'Memory is the OS high-water mark for the entire process, including scientific-library imports and JSON serialization.',
           'This verifies Python state-query latency, not browser rendering, SSE throughput or concurrent web clients.','',
           '## One garment, no waiting','',
           'Geometry, detailed operation order/times, piece recovery, seams and stitches are tested against the existing engine.',
           'The only accounting change removes Pfaff standby power and equipment occupancy during transport.',
           'Common power still spans the same uninterrupted work interval for this one-garment case.','',
           '| Quantity | Legacy | Factory | Actual delta | Expected delta |','| --- | ---: | ---: | ---: | ---: |']
    for key,row in result['single_garment_equivalence'].items():
        lines.append(f"| {key} | {row['legacy']:.12g} | {row['factory']:.12g} | {row['actual_delta']:.12g} | {row['expected_delta']:.12g} |")
    lines += ['', 'Tolerance: relative 1e-9, absolute 1e-6. Differences are calculations, not fitted corrections.','',
              f"Source SHA-256: `{result['source_sha256']}`", f"Deterministic run content hash: `{result['content_hash']}`",'',
              'Reproduce from `studio`:','',
              '```powershell','python -m pytest factory_tests -q',
              'python -m studio.factory.benchmark --out runs/factory-benchmark.json --report runs/factory-benchmark.md','```','']
    return '\n'.join(lines)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',default='runs/factory-benchmark.json')
    parser.add_argument('--report',default='runs/factory-benchmark.md')
    parser.add_argument('--artifact',default='runs/factory-1000.json')
    args=parser.parse_args(argv)
    if len({Path(p).resolve() for p in (args.out,args.report,args.artifact)})!=3:
        parser.error('report, metrics and artifact paths must be different')
    result=run_benchmark(args.artifact)
    atomic_text(args.out,lambda stream:json.dump(result,stream,ensure_ascii=False,allow_nan=False,indent=2))
    atomic_text(args.report,lambda stream:stream.write(report_text(result)))
    print(json.dumps({k:result[k] for k in ('passed','build_s','artifact_bytes','peak_process_rss_bytes','domain_events','query_ms')},indent=2))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
