"""Fixed, reproducible NFR06 fixtures; no application or database mutations."""
from datetime import date, timedelta
from random import Random

from sample_data import dataset, material, task


CASES = ("shared-stock", "deep-zero-stock")


def build_case(name):
    if name not in CASES:
        raise ValueError("Unknown performance case")
    sizes = [20, 40, 60, 80] if name == "shared-stock" else [20] + [10] * 9 + [90]
    layers = [[f"L{level:02}-{i:03}" for i in range(size)] for level, size in enumerate(sizes)]
    materials = [material(mid, "BUY" if level == len(layers) - 1 else "MAKE",
                          lead=1 + level % 3, minimum=25, multiple=12)
                 for level, layer in enumerate(layers) for mid in layer]
    edges = set()
    # Every non-leaf has a child and every non-root has a parent.
    for parents, children in zip(layers, layers[1:]):
        edges.update((parent, children[i % len(children)]) for i, parent in enumerate(parents))
        edges.update((parents[i % len(parents)], child) for i, child in enumerate(children))
    pairs = list(zip(layers, layers[1:])) if name == "shared-stock" else [(layers[-2], layers[-1])]
    candidates = [(p, c) for parents, children in pairs for p in parents for c in children if (p, c) not in edges]
    Random(20261012).shuffle(candidates)
    edges.update(candidates[:500 - len(edges)])
    weighted_edges = [(p, c, 1 + i % 3) for i, (p, c) in enumerate(sorted(edges))]
    tasks = [task(f"PERF-{i:03}", layers[0][i % 20], 10 + i % 11,
                  (date(2026, 11, 1) + timedelta(days=i % 17)).isoformat(), 1 + i % 3)
             for i in range(100)]
    sources, request = dataset(materials, weighted_edges, tasks)
    if name == "shared-stock":
        for i, row in enumerate(sources["stocks"]):
            row.update(on_hand=8 + i % 23, reserved=i % 4)
    sources["source_revision"] = "performance-20261012-" + name
    request["request_id"] = "PERFORMANCE-" + name
    return dict(sources=sources, request=request)
