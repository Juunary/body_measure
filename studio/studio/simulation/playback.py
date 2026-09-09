"""One authoritative clock; random-access snapshots make seeks idempotent."""
import math
import threading
import time
import uuid
from .engine import snapshot


class Playback:
    def __init__(self, plan, publish=lambda s: None, clock=time.monotonic, on_error=lambda exc: None):
        self.plan, self.publish, self.clock = plan, publish, clock
        self.on_error = on_error
        self.run_id = uuid.uuid4().hex[:16]
        self.seq = 0
        self.revision = 0
        self.position = 0.
        self.speed = plan['config']['speed']
        self.status = 'paused'
        self.last = clock()
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.thread = None

    def _advance(self):
        now = self.clock()
        if self.status == 'playing':
            self.position = min(self.plan['totals']['duration_s'], self.position + (now-self.last)*self.speed)
            if self.position >= self.plan['totals']['duration_s']: self.status='completed'
        self.last = now

    def _state(self):
        state = {**snapshot(self.plan,self.position), 'run_id':self.run_id,'plan_id':self.plan['plan_id'],
                'seq':self.seq,'revision':self.revision,'status':self.status,'speed':self.speed}
        state['terminal_lines'] = terminal_lines(state)
        return state

    def get(self):
        with self.lock:
            # Reads do not advance or consume a sequence number. The controller
            # publishes at 10 Hz, so every observer sees the same snapshot.
            return self._state()

    def _emit(self):
        self.seq += 1
        state=self._state()
        self.publish(state)
        return state

    def tick(self):
        with self.lock:
            self._advance()
            return self._emit()

    def control(self, action, value=None):
        with self.lock:
            if self.closed.is_set(): raise ValueError('simulation was replaced or evicted')
            if action in ('seek','speed') and (value is None or not math.isfinite(value)):
                raise ValueError('a finite control value is required')
            if action=='speed' and not .1<=value<=100: raise ValueError('speed must be 0.1–100')
            if action=='seek' and not 0<=value<=self.plan['totals']['duration_s']:
                raise ValueError('seek is outside the simulation timeline')
            if action not in ('play','pause','seek','speed','restart','next','previous'):
                raise ValueError('unknown playback action')
            self._advance()
            if action=='play':
                if self.status=='completed': self.position=0.;self.revision+=1
                self.status='playing'
            elif action=='pause': self.status='paused'
            elif action=='speed': self.speed=value
            else:
                if action=='restart':self.position=0.;self.status='playing'
                elif action=='seek':self.position=value;self.status='paused'
                else:
                    # Step between meaningful manufacturing tasks, skipping rapid
                    # positioning and tool lift/lower operations.
                    boundaries=[o['start_s'] for o in self.plan['operations'] if o['kind'] not in ('travel','tool_up','tool_down')]
                    candidates=[t for t in boundaries if t>self.position+.001] if action=='next' else [t for t in boundaries if t<self.position-.001]
                    self.position=(min(candidates) if action=='next' else max(candidates)) if candidates else (self.plan['totals']['duration_s'] if action=='next' else 0.)
                    self.status='paused'
                self.revision+=1
            return self._emit()

    def start(self):
        self.control('play')
        def loop():
            while not self.closed.wait(.1):
                with self.lock:
                    if self.status=='playing':
                        try:
                            self.tick()
                        except Exception as exc:
                            self.status='error'
                            self.closed.set()
                            self.on_error(exc)
        self.thread=threading.Thread(target=loop,name=f'cutting-{self.run_id}',daemon=True)
        self.thread.start()

    def close(self):
        with self.lock:
            self.closed.set()


def terminal_lines(state):
    """The SAME plain text in browser, attached CLI, and headless CLI."""
    m=state['metrics'];head=state['head_mm']
    resource = state.get('resources')
    resource_lines = ([f"Flow time {resource['flow_time_s']:.2f} s | Energy {resource['energy_kwh']:.5f} kWh | CO2e {resource['co2e_g']:.2f} g | Cost {resource['cost_eur']:.4f} EUR",
                       'Cost: ' + ' | '.join(f'{k} {v:.4f} EUR' for k,v in resource['cost_breakdown_eur'].items()),
                       f"Direct labour {resource['labour_time_s']:.2f} s | thread {resource['thread_used_m']:.3f} m | research estimates; electricity emissions only"]
                      if resource else ['Energy / CO2e / Cost: not provided for this historical run.'])
    return [
        f"Size: {(state.get('size') or {}).get('label') or 'unknown'} | source: {(state.get('size') or {}).get('source', 'unknown')}",
        f"RESEARCH SIMULATION | {state.get('scope','through_cutting')} | {state['status']} | {state['speed']:g}x",
        f"{state['sim_time_s']:8.2f} / {state['duration_s']:.2f} s  window {state['window']+1}  {state['operation']}  {state['piece_id'] or '-'}",
        f"head X {head[0]:8.2f} Y {head[1]:8.2f} mm | tool {state['tool']} | vacuum {'on' if state['vacuum'] else 'off'}",
        f"cut {m['cut_length_mm']/1000:.3f} m | travel {m['travel_mm']/1000:.3f} m | marked {m['mark_length_mm']/1000:.3f} m",
        f"cut parts {m['cut_pieces']}/{len(state['pieces'])} | collected {m['collected_pieces']} | planned yield {m['yield_pct']:.2f}% | planned waste {m['waste_area_mm2']/1e6:.3f} m2",
        '  '.join(f'{k}: {v}' for k,v in state['pieces'].items()),
        f"Pfaff | {state.get('machines',{}).get('pfaff','waiting')} | seam {state.get('sewing',{}).get('seam_id') or '-'} | sewn {m.get('sewn_length_mm',0)/1000:.3f} m | stitches {m.get('stitches',0)} | seams {m.get('seams_complete',0)}/{m.get('seams_total',0)}",
        'Research assembly only. Finishing / QC / buttonholes not executed. No cloth physics or live machine telemetry.',
    ] + resource_lines
