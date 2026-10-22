"""Small-sample check before the full run (not a development-set run).

Every condition of this round is run on its first 2 functions (one vulnerable/fixed pair), PrimeVul and PairVul,
about 14 calls in total. Results go to results_smoke/ and pairvul/results_smoke/, never to results/, so the full run
is not affected. Each condition must return a parsed verdict with thinking on for every function it calls.

usage (same common parameters as the full run):
  python smoke_test.py $M
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIMIT = 2
PLAN = [(ROOT, 'graph_diff_v2'), (ROOT, 'verify_graph_diff_v2'), (ROOT, 'graph_diff_text_v2'),
        (ROOT, 'graph_hint_v2'), (ROOT, 'graph_diff_v2_noguard'),
        (ROOT / 'pairvul', 'graph_diff_v2'), (ROOT / 'pairvul', 'verify_graph_diff_v2')]


def option(args, name):
    """Value of the last --name in args (argparse semantics), or None."""
    value = None
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            value = args[i + 1]
        elif a.startswith(name + '='):
            value = a.split('=', 1)[1]
    return value


def predictions(base, condition, model):
    name = f"{condition}_{re.sub(r'[^A-Za-z0-9_.-]+', '-', model)}_smoke"
    return base / 'results_smoke' / f'predictions_{name}.jsonl'


def check(path):
    """Problems found in one smoke predictions file (empty list = passed)."""
    if not path.exists():
        return ['no result file was written']
    rows = [json.loads(line) for line in open(path, encoding='utf-8') if line.strip()]
    if not rows:
        return ['no functions in the result file']
    problems = []
    for r in rows:
        sid = r['sample_id']
        if r.get('status') not in ('ok', 'ok_after_retry'):
            problems.append(f"{sid}: status {r.get('status')}: {r.get('error')}")
        elif r.get('prediction') not in (0, 1):
            problems.append(f'{sid}: no verdict')
        elif not r.get('stage1_only') and not r.get('reasoning_chars'):
            problems.append(f'{sid}: no thinking output (reasoning_chars = 0); thinking mode is not on')
    return problems


def main():
    extra = sys.argv[1:]
    model = option(extra, '--model')
    if not model:
        sys.exit('usage: python smoke_test.py $M   (the common parameters, including --model)')
    if option(extra, '--thinking') not in (None, 'on'):
        sys.exit('thinking mode must be on: keep --thinking on in the common parameters')
    for base in {b for b, _ in PLAN}:
        shutil.rmtree(base / 'results_smoke', ignore_errors=True)  # a fresh check every time

    failed = False
    for base, condition in PLAN:
        where = 'PairVul ' if base.name == 'pairvul' else 'PrimeVul'
        cmd = [sys.executable, str(base / 'online' / 'run_online.py'), 'run', '--condition', condition, *extra]
        if condition.startswith('verify_'):
            stage1 = predictions(base, 'graph_diff_v2', model)
            if check(stage1):
                print(f'FAIL {where} {condition}\n     skipped: its stage 1 (graph_diff_v2) failed', flush=True)
                failed = True
                continue
            cmd += ['--stage1', str(stage1)]
        cmd += ['--limit', str(LIMIT), '--tag', 'smoke', '--out', str(base / 'results_smoke')]
        if option(extra, '--retries') is None:
            cmd += ['--retries', '3']  # fail within about a minute if the endpoint is wrong or down
        print(f'--- {where} {condition}', flush=True)
        subprocess.run(cmd, cwd=base)
        problems = check(predictions(base, condition, model))
        failed |= bool(problems)
        print(f"{'FAIL' if problems else 'OK  '} {where} {condition}" + ''.join('\n     ' + p for p in problems), flush=True)

    print()
    if failed:
        print('Smoke test FAILED. Do not start the full run; send the output above to us.')
        sys.exit(1)
    print('Smoke test passed: every condition answered with thinking on. You can start the full run.')


if __name__ == '__main__':
    main()
