"""PowerShell: python -m studio.simulate --measurements result.json --config draft.json.

Attach: --attach JOB --server http://127.0.0.1:8010. STUDIO_PASSWORD supplies
the existing BasicAuth password; it is never put into URLs or output files.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request
from . import paths  # sibling imports
from .simulation import SimulationConfig, build_plan, snapshot
from .simulation.playback import terminal_lines
from .simulation.service import write_json


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--measurements')
    source.add_argument('--attach',metavar='JOB_ID')
    parser.add_argument('--config')
    parser.add_argument('--server',default='http://127.0.0.1:8010')
    parser.add_argument('--speed',type=float)
    parser.add_argument('--no-color',action='store_true')
    parser.add_argument('--instant',action='store_true',help='emit operation-boundary states without wall-clock waits')
    parser.add_argument('--jsonl',help='save observed states as JSONL')
    parser.add_argument('--out',help='save the complete immutable plan and final result')
    args=parser.parse_args(argv)
    log=open(args.jsonl,'w',encoding='utf-8') if args.jsonl else None
    previous=[None]
    def show(s):
        if log:log.write(json.dumps(s,ensure_ascii=False,allow_nan=False)+'\n');log.flush()
        # Non-interactive output remains a readable event log. Interactive
        # terminals get a fixed screen; both consume the same state vocabulary.
        if sys.stdout.isatty() and not args.no_color:print('\033[2J\033[H',end='')
        key=(s.get('revision'),s['operation_index'],s['status'])
        if sys.stdout.isatty() or key!=previous[0]:print('\n'.join(s.get('terminal_lines') or terminal_lines(s)),flush=True)
        previous[0]=key
    try:
        if args.attach:
            if args.config or args.speed is not None or args.instant or args.out:
                parser.error('attached playback is controlled in Studio; config/speed/instant/out require --measurements')
            return attach(args.server,args.attach,show)
        document=json.loads(open(args.measurements,encoding='utf-8').read())
        config=SimulationConfig(**(json.loads(open(args.config,encoding='utf-8').read()) if args.config else {}))
        if args.speed is not None:config=SimulationConfig(**{**config.model_dump(),'speed':args.speed})
        plan=build_plan(document,config)
        run_id=plan['plan_id'];seq=0
        def at(t):
            nonlocal seq
            seq+=1
            s=snapshot(plan,t)
            return {**s,'run_id':run_id,'plan_id':plan['plan_id'],'seq':seq,'revision':0,
                    'speed':config.speed,'status':'completed' if s['finished'] else 'playing'}
        if args.instant:
            for t in [0]+[o['end_s'] for o in plan['operations']]:s=at(t);show(s)
        else:
            begin=time.monotonic()
            while True:
                s=at((time.monotonic()-begin)*config.speed);show(s)
                if s['finished']:break
                time.sleep(.1)
        if args.out:write_json(args.out,{'schema_version':plan['schema_version'],'plan':plan,'result':s})
        return 0
    except (ValueError,OSError) as exc:
        print(f'error: {exc}',file=sys.stderr);return 2
    except KeyboardInterrupt:return 130
    finally:
        if log:log.close()


def attach(server, job, show):
    import re
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',job):raise ValueError('invalid job ID')
    base=server.rstrip('/')+f'/api/jobs/{job}'
    headers={}
    if os.environ.get('STUDIO_PASSWORD'):
        headers['Authorization']='Basic '+base64.b64encode(('studio:'+os.environ['STUDIO_PASSWORD']).encode()).decode()
    def get(url, extra=None):
        return urllib.request.urlopen(urllib.request.Request(url,headers={**headers,**(extra or {})}),timeout=30)
    with get(base+'/simulation') as r:data=json.load(r)
    if not data.get('state'):raise ValueError('start a cutting simulation in Studio first')
    current=data['state'];show(current)
    if current['finished']:return 0
    last=data['last_event_id'];run=current['run_id'];seq=current['seq']
    failures=0
    while failures<5:
        try:
            with get(base+'/events',{'Last-Event-ID':str(last)}) as response:
                event_id=last;event_type='';lines=[]
                for raw in response:
                    line=raw.decode('utf-8').rstrip('\r\n')
                    if line.startswith('id:'):event_id=int(line[3:].strip())
                    elif line.startswith('event:'):event_type=line[6:].strip()
                    elif line.startswith('data:'):lines.append(line[5:].strip())
                    elif not line and lines:
                        state=json.loads('\n'.join(lines));lines=[];last=event_id;failures=0
                        if event_type=='simulation_state':
                            if state['run_id']!=run:run=state['run_id'];seq=-1
                            if state['seq']<=seq:continue
                            seq=state['seq'];show(state)
                            if state['finished']:return 0
            failures+=1
        except (OSError,TimeoutError):failures+=1
        time.sleep(min(2**failures,8))
    raise OSError('event stream disconnected after 5 retries')


if __name__=='__main__':raise SystemExit(main())
