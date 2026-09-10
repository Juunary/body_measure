"""Run: python -m studio.factory --scenario scenario.json --out run.json.

Replay: python -m studio.factory --replay run.json --at 120 --garment order-1:0001.
All numeric results are research simulation estimates. The default scope ends
at the sewn assembly; scope through_qc adds steam finishing and vision QC and
stops before the DPP label / QR.
"""
import argparse
from pathlib import Path
import sys
from . import simulate, Replay, load, save
from .storage import read_json, save_events


def scenario_file(path):
    path = Path(path)
    data = read_json(path)
    if not isinstance(data,dict): raise ValueError('scenario must be a JSON object')
    # Resolve convenience paths at the boundary, never persist local filenames.
    for key in ('measurements','config'):
        if isinstance(data.get(key),str): data[key] = read_json(path.parent/data[key])
    return data


def resource_line(r):
    return (f"Flow {r['flow_time_s']:.3f} s | Energy {r['energy_kwh']:.6f} kWh | "
            f"CO2e {r['co2e_g']:.3f} g | Cost {r['cost_eur']:.6f} EUR")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--scenario'); source.add_argument('--replay')
    parser.add_argument('--out'); parser.add_argument('--jsonl')
    parser.add_argument('--at',type=float); parser.add_argument('--garment')
    parser.add_argument('--no-color',action='store_true',help='plain output (also the default)')
    args = parser.parse_args(argv)
    try:
        if args.scenario:
            if not args.out: parser.error('--scenario requires --out')
            if args.at is not None or args.garment: parser.error('--at and --garment require --replay')
            destinations = [Path(p).resolve() for p in (args.out,args.jsonl) if p]
            scenario_path = Path(args.scenario).resolve()
            raw = read_json(scenario_path)
            if not isinstance(raw,dict): raise ValueError('scenario must be a JSON object')
            inputs = [scenario_path]+[(scenario_path.parent/raw[k]).resolve() for k in ('measurements','config') if isinstance(raw.get(k),str)]
            if len(set(destinations)) != len(destinations) or set(inputs).intersection(destinations):
                raise ValueError('input, artifact and JSONL paths must be different')
            run = simulate(scenario_file(args.scenario)); save(args.out,run)
            if args.jsonl: save_events(args.jsonl,run)
            result = run['result']
            print(f"RESEARCH SIMULATION | {run['run_id']} | size {run['scenario']['size']['label']} | scope {run['scope']}")
            print(f"Collected research assemblies: {result['completed_garments']} | Throughput {result['throughput_per_hour']:.3f}/h")
            if 'qc' in result:
                qc = result['qc']
                print(f"Pressed {result['resources']['metrics']['pressed']} | Inspected {qc['inspected']} | "
                      f"QC pass {qc['passed']} / fail {qc['failed']} ({qc['verdict_model']}) | "
                      f"Ready for DPP label: {qc['ready_for_dpp_label']}")
            print(resource_line(result['resources']))
            print('Cost: '+' | '.join(f'{k} {v:.6f} EUR' for k,v in result['resources']['cost_breakdown_eur'].items()))
            print('Order | Quantity | Lead time (s) | Energy (kWh) | Cost (EUR)')
            for order in result['orders']:
                print(f"{order['id']} | {order['quantity']} | {order['lead_time_s']:.3f} | "
                      f"{order['resources']['energy_kwh']:.6f} | {order['resources']['cost_eur']:.6f}")
            if 'qc' in result:
                print('DPP label / QR / packing / shipping: not executed. No finished manufactured product.')
            else:
                print('Finishing / QC / shipping: not executed. No finished manufactured product.')
        else:
            if args.out or args.jsonl: parser.error('--out/--jsonl require --scenario')
            run = load(args.replay)
            state = Replay(run).snapshot(run['duration_s'] if args.at is None else args.at,args.garment)
            print(f"RESEARCH REPLAY | {state['run_id']} | {state['time_s']:.3f}/{state['duration_s']:.3f} s")
            print(resource_line(state['resources']))
            print(' | '.join(f'{k}: {v}' for k,v in state['counts'].items()))
            for rid,allocation in sorted(state['active_resources'].items()):
                names=', '.join(run['garments'][gi]['id'] for gi in allocation['garments'])
                print(f"{rid} | {allocation['mode']} | {names}")
            if state['selected_garment']:
                g = state['selected_garment']
                print(f"{g['id']} | {g['status']} | {g['operation']} | {g['operation_progress']:.3f}")
                print(resource_line(g['resources']))
                if g['stage']:
                    s = g['stage']
                    values = ' | '.join(f'{k} {v:.1f}' if isinstance(v,float) else f'{k} {v}' for k,v in s['readouts'].items())
                    print(f"{s['stage']} | {s['step']} | {s['machine']} | attended {s['attended']} | {values}")
                else:
                    print(f"Head {g['head_mm']} mm | tool {g['tool']} | vacuum {g['vacuum']}")
                print(' | '.join(f'{k}: {v}' for k,v in g['pieces'].items()))
        return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(f'error: {exc}',file=sys.stderr); return 2
    except KeyboardInterrupt: return 130


if __name__ == '__main__': raise SystemExit(main())
