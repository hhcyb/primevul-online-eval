"""5% pilot: run a fixed random 5% of the pairs (prepared/sample_pairs.json, seed 20261009) for every condition of
this round, then estimate the cost of the full run from the measured tokens (estimate_cost.py).

The first-step runs write to results/ exactly like the full run, which later skips these functions, so they are not
paid twice. The protection checks run with --tag pilot (about 80 extra calls), because the full check must wait for
the complete first step. PrimeVul: 22 pairs (44 functions) per condition; PairVul: 29 pairs (58 functions).

usage (same common parameters as the full run; put last round's results/ in place first):
  python pilot.py $M
"""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIRST = [(ROOT, 'graph_diff_v2'), (ROOT, 'graph_diff_text_v2'), (ROOT, 'graph_hint_v2'),
         (ROOT, 'graph_diff_v2_noguard'), (ROOT / 'pairvul', 'graph_diff_v2')]
SECOND = [(ROOT, 'verify_graph_diff_v2'), (ROOT / 'pairvul', 'verify_graph_diff_v2')]


def option(args, name):
    value = None
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            value = args[i + 1]
        elif a.startswith(name + '='):
            value = a.split('=', 1)[1]
    return value


def run_parallel(jobs, extra, model):
    procs = []
    for base, condition in jobs:
        cmd = [sys.executable, str(base / 'online' / 'run_online.py'), 'run', '--condition', condition, *extra,
               '--subset', 'sample']
        if condition.startswith('verify_'):
            stage1 = base / 'results' / f"predictions_graph_diff_v2_{re.sub(r'[^A-Za-z0-9_.-]+', '-', model)}.jsonl"
            # the tag follows the stage-1 file, so a rerun after more stage-1 answers starts a fresh pilot check
            tag = 'pilot' + hashlib.sha256(stage1.read_bytes()).hexdigest()[:6] if stage1.exists() else 'pilot'
            cmd += ['--stage1', str(stage1), '--allow-incomplete-stage1', '--tag', tag]
        (base / 'results').mkdir(exist_ok=True)
        log = open(base / 'results' / f'pilot_{condition}.log', 'w', encoding='utf-8')
        procs.append((base, condition, subprocess.Popen(cmd, cwd=base, stdout=log, stderr=subprocess.STDOUT), log))
        print(f"started  {'PairVul ' if base.name == 'pairvul' else 'PrimeVul'} {condition}", flush=True)
    ok = True
    for base, condition, proc, log in procs:
        proc.wait()
        log.close()
        tail = (base / 'results' / f'pilot_{condition}.log').read_text(encoding='utf-8').strip().splitlines()[-2:]
        failed = proc.returncode != 0 or any('calls failed' in line for line in tail)
        ok &= not failed
        print(f"{'FAIL' if failed else 'done'} {'PairVul ' if base.name == 'pairvul' else 'PrimeVul'} {condition}"
              + ''.join('\n     ' + line for line in tail), flush=True)
    return ok


def main():
    extra = sys.argv[1:]
    model = option(extra, '--model')
    if not model:
        sys.exit('usage: python pilot.py $M   (the common parameters, including --model)')
    if option(extra, '--thinking') not in (None, 'on'):
        sys.exit('thinking mode must be on: keep --thinking on in the common parameters')
    first = run_parallel(FIRST, extra, model)
    second = run_parallel(SECOND, extra, model)
    print()
    if not (first and second):
        print('Some pilot calls failed; run the same command again (finished functions are skipped), then continue.')
    subprocess.run([sys.executable, str(ROOT / 'estimate_cost.py'), '--model', model], cwd=ROOT)


if __name__ == '__main__':
    main()
