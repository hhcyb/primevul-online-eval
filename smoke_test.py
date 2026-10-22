"""Small-sample check before the full run (not a development-set run).

Every condition of this round is run on its first functions (default 2, one vulnerable/fixed pair), PrimeVul and
PairVul, about 14 calls in total. The five first-step runs go in parallel, then the two protection checks, so the check
takes about two call lengths. Results go to results_smoke/ and pairvul/results_smoke/, never to results/, so the full
run is not affected. Each condition must return a parsed verdict with thinking on for every function it calls.

usage (same common parameters as the full run):
  python smoke_test.py $M
options of this script only:
  --smoke-limit N   functions per condition (default 2)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIRST = [(ROOT, 'graph_diff_v2'), (ROOT, 'graph_diff_text_v2'), (ROOT, 'graph_hint_v2'),
         (ROOT, 'graph_diff_v2_noguard'), (ROOT / 'pairvul', 'graph_diff_v2')]
SECOND = [(ROOT, 'verify_graph_diff_v2'), (ROOT / 'pairvul', 'verify_graph_diff_v2')]


def option(args, name):
    """Value of the last --name in args (argparse semantics), or None."""
    value = None
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            value = args[i + 1]
        elif a.startswith(name + '='):
            value = a.split('=', 1)[1]
    return value


def without(args, name):
    """args with every --name VALUE / --name=VALUE removed."""
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a == name:
            skip = True
        elif not a.startswith(name + '='):
            out.append(a)
    return out


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


def label(base, condition):
    return f"{'PairVul ' if base.name == 'pairvul' else 'PrimeVul'} {condition}"


def run_parallel(jobs, extra, model, limit):
    """Start every job at once, wait for all, and report each. Returns True if all passed."""
    procs = []
    for base, condition in jobs:
        cmd = [sys.executable, str(base / 'online' / 'run_online.py'), 'run', '--condition', condition, *extra]
        if condition.startswith('verify_'):
            cmd += ['--stage1', str(predictions(base, 'graph_diff_v2', model))]
        cmd += ['--limit', str(limit), '--tag', 'smoke', '--out', str(base / 'results_smoke')]
        if option(extra, '--retries') is None:
            cmd += ['--retries', '3']  # fail within about a minute if the endpoint is wrong or down
        (base / 'results_smoke').mkdir(exist_ok=True)
        log = open(base / 'results_smoke' / f'{condition}.log', 'w', encoding='utf-8')
        procs.append((base, condition, subprocess.Popen(cmd, cwd=base, stdout=log, stderr=subprocess.STDOUT), log))
        print(f'started  {label(base, condition)}', flush=True)
    ok = True
    for base, condition, proc, log in procs:
        proc.wait()
        log.close()
        problems = check(predictions(base, condition, model))
        if problems and not predictions(base, condition, model).exists():
            tail = (base / 'results_smoke' / f'{condition}.log').read_text(encoding='utf-8').strip().splitlines()[-3:]
            problems += [f'log: {line}' for line in tail]
        ok &= not problems
        print(f"{'FAIL' if problems else 'OK  '} {label(base, condition)}" + ''.join('\n     ' + p for p in problems),
              flush=True)
    return ok


def main():
    extra = sys.argv[1:]
    limit = int(option(extra, '--smoke-limit') or 2)
    extra = without(extra, '--smoke-limit')
    model = option(extra, '--model')
    if not model:
        sys.exit('usage: python smoke_test.py $M   (the common parameters, including --model)')
    if option(extra, '--thinking') not in (None, 'on'):
        sys.exit('thinking mode must be on: keep --thinking on in the common parameters')
    for base in {b for b, _ in FIRST + SECOND}:
        shutil.rmtree(base / 'results_smoke', ignore_errors=True)  # a fresh check every time

    passed = run_parallel(FIRST, extra, model, limit)
    if passed:
        passed = run_parallel(SECOND, extra, model, limit)
    else:
        print('protection checks skipped: a first step failed')

    print()
    if not passed:
        print('Smoke test FAILED. Do not start the full run; send the output above to us '
              '(details are in results_smoke/*.log).')
        sys.exit(1)
    print('Smoke test passed: every condition answered with thinking on. You can start the full run.')


if __name__ == '__main__':
    main()
