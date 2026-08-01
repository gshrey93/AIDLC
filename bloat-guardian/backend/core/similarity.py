"""Similarity utilities: deterministic normalised-text near-duplicate detection."""
from __future__ import annotations

import zlib
from collections import defaultdict

from .config import SHINGLE_SIZE, SKETCH_SIZE


def shingle_set(norm_text: str, k: int = SHINGLE_SIZE) -> set:
    words = norm_text.split()
    if not words:
        return set()
    if len(words) < k:
        return {zlib.crc32(" ".join(words).encode("utf-8"))}
    return {
        zlib.crc32(" ".join(words[i:i + k]).encode("utf-8"))
        for i in range(len(words) - k + 1)
    }


def bottom_k_sketch(shingles: set, size: int = SKETCH_SIZE) -> tuple:
    return tuple(sorted(shingles)[:size])


def sketch_jaccard(a: tuple, b: tuple, size: int = SKETCH_SIZE) -> float:
    """Bottom-k (KMV) Jaccard estimate."""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    union = sorted(sa | sb)[:size]
    if not union:
        return 0.0
    us = set(union)
    inter = len(us & sa & sb)
    return inter / len(union)


def exact_jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def candidate_pairs(sketches: list, min_shared_ratio: float = 0.35, max_posting: int = 1200) -> set:
    """Inverted-index candidate generation over bottom-k sketches."""
    index = defaultdict(list)
    for idx, sk in enumerate(sketches):
        for h in sk:
            index[h].append(idx)

    min_shared = max(4, int(SKETCH_SIZE * min_shared_ratio))
    pairs = set()
    counters = [defaultdict(int) for _ in range(len(sketches))]
    for postings in index.values():
        if len(postings) < 2:
            continue
        use = postings[:max_posting]
        for i in range(len(use)):
            a = use[i]
            ca = counters[a]
            for j in range(i + 1, len(use)):
                ca[use[j]] += 1
    for a, ca in enumerate(counters):
        for b, count in ca.items():
            if count >= min_shared:
                pairs.add((a, b) if a < b else (b, a))
    return pairs


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def groups(self) -> dict:
        out = defaultdict(list)
        for i in range(len(self.parent)):
            out[self.find(i)].append(i)
        return {k: v for k, v in out.items() if len(v) > 1}
