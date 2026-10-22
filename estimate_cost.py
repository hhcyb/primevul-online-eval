"""Cost estimate for the full run from the measured token usage of the 5% pilot (pilot.py).

For every condition: the pilot's prompt and completion tokens (completion includes thinking; a follow-up call, if
any, is added), scaled to the full number of calls. PrimeVul first-step conditions are scaled by their ratio to the
previous round's direct run on the same functions when results/predictions_direct_<model>.jsonl is present (it covers
all 870 functions, which narrows the interval); otherwise by the pilot mean. The protection check is scaled by the
share of first-step pilot functions that were flagged. Interval: 90% bootstrap over the pilot pairs.

usage:
  python estimate_cost.py [--model qwen3.8-max-0902] [--price-in 12] [--price-out 36]
"""
import argparse
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIRST = ['graph_diff_v2', 'graph_diff_text_v2', 'graph_hint_v2', 'graph_diff_v2_noguard']
FUNCTIONS = {'primevul': 870, 'pairvul': 1172}


def latest(path):
    rows = {}
    if path.exists():
        for line in open(path, encoding='utf-8'):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            rows[r['sample_id']] = r
    return rows


def tokens(r):
    """(prompt, completion) tokens of one function with its follow-up call; None if no usage was recorded."""
    total, found = [0, 0], False
    for u in (r.get('usage'), r.get('retry_usage')):
        if isinstance(u, dict) and u.get('completion_tokens') is not None:
            total[0] += u.get('prompt_tokens') or 0
            total[1] += u.get('completion_tokens') or 0
            found = True
    return tuple(total) if found else None


def pair_of(sid):
    if sid.startswith('pairvul-'):
        return sid.rsplit('-', 1)[0]
    return f'test-pair-{int(sid.split("-")[1]) // 2:06d}'


def with_tokens(path, keep=lambda r: True):
    out = {}
    for s, r in latest(path).items():
        t = tokens(r)
        if t and keep(r):
            out[s] = t
    return out


class Plan:
    def __init__(self, name, rows, calls, base=None):
        self.name, self.rows, self.calls, self.base = name, rows, calls, base
        self.by_pair = {}
        for s in rows:
            self.by_pair.setdefault(pair_of(s), []).append(s)

    def estimate(self, ids):
        """(input, output) tokens of the full run, from the pilot functions `ids` (repeats allowed)."""
        ids = [s for s in ids if s in self.rows]
        if not ids:
            return None
        got_in, got_out = sum(self.rows[s][0] for s in ids), sum(self.rows[s][1] for s in ids)
        if self.base is None:
            return got_in / len(ids) * self.calls, got_out / len(ids) * self.calls
        base_in, base_out = sum(self.base[s][0] for s in ids), sum(self.base[s][1] for s in ids)
        full_in, full_out = sum(t[0] for t in self.base.values()), sum(t[1] for t in self.base.values())
        scale = self.calls / len(self.base)
        return got_in / base_in * full_in * scale, got_out / base_out * full_out * scale


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--model', default='qwen3.8-max-0902')
    p.add_argument('--price-in', type=float, default=12.0, help='yuan per million input tokens')
    p.add_argument('--price-out', type=float, default=36.0, help='yuan per million output tokens')
    args = p.parse_args()
    model = re.sub(r'[^A-Za-z0-9_.-]+', '-', args.model)
    cost = lambda e: (e[0] * args.price_in + e[1] * args.price_out) / 1e6

    plans, pairs = [], {}
    for dataset, base in (('primevul', ROOT), ('pairvul', ROOT / 'pairvul')):
        sample = set(json.loads((base / 'prepared' / 'sample_pairs.json').read_text(encoding='utf-8'))['pair_ids'])
        pairs[dataset] = sorted(sample)
        res = base / 'results'
        direct = with_tokens(res / f'predictions_direct_{model}.jsonl')
        for c in (FIRST if dataset == 'primevul' else ['graph_diff_v2']):
            rows = {s: t for s, t in with_tokens(res / f'predictions_{c}_{model}.jsonl').items() if pair_of(s) in sample}
            usable = len(direct) >= 0.9 * FUNCTIONS[dataset] and rows and all(s in direct for s in rows)
            plans.append((dataset, Plan(c, rows, FUNCTIONS[dataset], direct if usable else None)))
        stage1 = [r for s, r in latest(res / f'predictions_graph_diff_v2_{model}.jsonl').items()
                  if pair_of(s) in sample and r.get('prediction') is not None]
        flagged = sum(int(r['prediction']) == 1 for r in stage1) / max(1, len(stage1))
        pilots = sorted(res.glob(f'predictions_verify_graph_diff_v2_{model}_pilot*.jsonl'), key=lambda f: f.stat().st_mtime)
        verify = with_tokens(pilots[-1], keep=lambda r: not r.get('stage1_only')) if pilots else {}
        verify = {s: t for s, t in verify.items() if pair_of(s) in sample}
        plans.append((dataset, Plan(f'verify_graph_diff_v2 ({flagged:.0%} flagged)', verify,
                                    round(flagged * FUNCTIONS[dataset]))))

    print(f"{'condition':44s} {'pilot':>5s} {'calls':>6s} {'in/call':>8s} {'out/call':>9s} "
          f"{'in (M)':>7s} {'out (M)':>8s} {'yuan':>7s}")
    total = [0.0, 0.0, 0]
    for dataset, plan in plans:
        e = plan.estimate(list(plan.rows))
        name = f'{dataset}/{plan.name}' + (' [ratio]' if plan.base is not None else '')
        if e is None:
            print(f'{name:44s} no pilot results')
            continue
        total[0] += e[0]
        total[1] += e[1]
        total[2] += plan.calls
        print(f'{name:44s} {len(plan.rows):5d} {plan.calls:6d} {e[0] / plan.calls:8.0f} {e[1] / plan.calls:9.0f} '
              f'{e[0] / 1e6:7.2f} {e[1] / 1e6:8.2f} {cost(e):7.0f}')
    print(f"{'total':44s} {'':5s} {total[2]:6d} {'':8s} {'':9s} {total[0] / 1e6:7.2f} {total[1] / 1e6:8.2f} "
          f"{cost(total):7.0f}")

    rng, boots = random.Random(20261009), []
    for _ in range(2000):
        pick = {d: [rng.choice(ps) for ps in [pairs[d]] for _ in ps] for d in pairs}
        value = 0.0
        for dataset, plan in plans:
            ids = [s for pr in pick[dataset] for s in plan.by_pair.get(pr, ())]
            e = plan.estimate(ids)
            value += cost(e) if e else 0.0
        boots.append(value)
    boots.sort()
    print(f'90% interval of the total: {boots[100]:.0f} .. {boots[1900]:.0f} yuan '
          f'(prices: {args.price_in:g} in / {args.price_out:g} out yuan per million tokens)')
    print('The first-step pilot calls are part of the full run (it skips them later); only the pilot protection '
          'checks (tag pilot) are extra.')


if __name__ == '__main__':
    main()
