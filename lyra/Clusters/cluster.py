import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import numpy as np
import hdbscan
from collections import defaultdict
import random

from Agent.agent import Agent
from typing import List, Optional, Dict, Any
import statistics
import math
import jenkspy

try:
    import jenkspy  # type: ignore
    _HAS_JENKSPY = True
except Exception:
    _HAS_JENKSPY = False

def _jenks_breaks_pure(values: list[float], k: int) -> List[float]:
    if k <= 0:
        raise ValueError("k must be >= 1")
    if k > len(values):
        raise ValueError("k cannot exceed number of observations")
    data = sorted(values)
    n = len(data)
    lower = [[0]*(k+1) for _ in range(n+1)]
    varc = [[0.0]*(k+1) for _ in range(n+1)]
    for i in range(1, k+1):
        lower[1][i] = 1
        varc[1][i] = 0.0
        for j in range(2, n+1):
            varc[j][i] = float("inf")
    sums = [0.0]*(n+1)
    sums_sq = [0.0]*(n+1)
    for i in range(1, n+1):
        v = data[i-1]
        sums[i] = sums[i-1] + v
        sums_sq[i] = sums_sq[i-1] + v*v
    for l in range(2, n+1):
        for m in range(1, min(l, k)+1):
            for i in range(1, l):
                count = l - i + 1
                s = sums[l] - sums[i-1]
                ss = sums_sq[l] - sums_sq[i-1]
                mean = s / count
                var = ss - mean*mean*count
                if varc[l][m] >= var + varc[i-1][m-1]:
                    lower[l][m] = i
                    varc[l][m] = var + varc[i-1][m-1]
    breaks = [0.0]*(k+1)
    breaks[k] = data[-1]
    count = k
    last = n
    while count >= 2:
        idx = int(lower[last][count]) - 1
        breaks[count-1] = data[idx]
        last = int(lower[last][count] - 1)
        count -= 1
    breaks[0] = data[0]
    return breaks[1:]

def jenks_breaks(values: List[float], k: int) -> List[float]:
    if _HAS_JENKSPY:
        return list(jenkspy.jenks_breaks(values, n_classes=k)[1:])
    return _jenks_breaks_pure(values, k)

def _assign_labels(values: List[float], breaks: List[float]) -> List[int]:
    labels: List[int] = []
    for v in values:
        cid = 0
        while cid < len(breaks) and v > breaks[cid] + 1e-12:
            cid += 1
        labels.append(min(cid, len(breaks)-1))
    return labels

def _total_variance(xs: List[float]) -> float:
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs)

def _class_variance(xs: List[float]) -> float:
    if not xs:
        return 0.0
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs)

def _cluster_sse(values: List[float], labels: List[int], k: int) -> float:
    sse = 0.0
    for cid in range(k):
        pts = [values[i] for i in range(len(values)) if labels[i] == cid]
        if not pts:
            continue
        mu = sum(pts) / len(pts)
        sse += sum((x - mu) ** 2 for x in pts)
    return sse

class individual_cluster:
    def __init__(self, 
                 cluster_id: int = 0, 
                 agents: Optional[List['Agent']] = None):
        self.cluster_id: int = cluster_id
        self.agents: List[Agent] = list(agents) if agents else []
        
    def add_to_cluster(self, agent):
        if agent not in self.agents:
            self.agents.append(agent)

    def remove_from_cluster(self, agent):
        if agent in self.agents:
            self.agents.remove(agent)
        
    def size(self) -> int:
        return len(self.agents)
    
    def opinions(self):
        return [a.get_opinion() for a in self.agents]
    
    def attitudes(self):
        return [a.get_attitude() for a in self.agents]
    
    def mean_opinion(self) -> float:
        if not self.agents:
            return 0.0
        return sum(self.opinions()) / len(self.agents)
    
    def mean_attitude(self) -> float:
        if not self.agents:
            return 0.0
        return sum(self.attitudes()) / len(self.agents)
    
    def mean_opinion(self) -> float:
        if not self.agents:
            return 0.0
        return sum(self.opinions()) / len(self.agents)
    
    
    def variance_opinion(self) -> float:
        n = len(self.agents)
        if n <= 1:
            return 0.0

        mu = self.mean_opinion()
        return sum((a.opinion - mu)**2 for a in self.agents) / (n - 1)
    
class cluster:
    def __init__(self, agents: List[Agent]):
        self.agents: List[Agent] = agents
        # Keep attribute names but fix obvious type issues.
        self.labels: List[int] = []               # label per agent in input order
        self._clusters: List[individual_cluster] = []  # list of clusters
        self._breaks: Optional[List[float]] = None
        self._k: Optional[int] = None


    def cluster_by_hdbscan(self, min_cluster_size: Optional[int] = 2, eps: Optional[float] = 0.1):
        self.labels = []
        self._clusters = []
        self._breaks = None
        self._k = 0
        if not self.agents:
            return self
        
        opinions = [a.get_opinion() for a in self.agents]
        data = np.array(opinions).reshape(-1, 1) # Data needs to be a np.array column
        
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=1,
            cluster_selection_method='eom',
            cluster_selection_epsilon=eps
        )
        lbls = clusterer.fit_predict(data)
        self.labels = lbls
        dct = defaultdict(list)
        for i in range(len(self.agents)):
            dct[lbls[i]].append(self.agents[i])
        
        # Count actual clusters (excluding noise label -1)
        unique_labels = set(lbls)
        if -1 in unique_labels:
            unique_labels.remove(-1)  # Remove noise label
        self._k = len(unique_labels)
        
        for id in dct.keys():
            if id != -1:  # Skip noise points
                individual_cl = individual_cluster(id, dct[id])
                self._clusters.append(individual_cl)
        
        return self


    def cluster_by_jenks(self, k: Optional[int] = None, k_min: int = 2) -> 'cluster':
        """
        Directly integrate Jenks: if k is given, use it; else pick k in [k_min, k_max] maximizing GVF.
        Populates self.labels and self._clusters in-place and returns self.
        """
        if not self.agents:
            self.labels = []
            self._clusters = []
            self._breaks = None
            self._k = 0
            return self
        
        opinions = [a.get_opinion() for a in self.agents]

        if k is None:
            n = len(opinions)
            k_max = int(math.sqrt(n)) + 1
            print("k_max: ", str(k_max))
            lo = max(1, k_min)
            hi = min(n, max(lo,k_max))
            prev_sse = None
            chosen = lo
            for kk in range(lo, hi + 1):
                br = jenks_breaks(opinions, kk)
                lbl = _assign_labels(opinions, br)
                sse = _cluster_sse(opinions, lbl, kk)
                if prev_sse is not None:
                    improvement = (prev_sse - sse) / max(prev_sse, 1e-12)
                    if improvement < 0.05:  # 5% elbow threshold
                        chosen = kk - 1
                        break
                prev_sse = sse
                chosen = kk
            k = max(lo, chosen)

        # Compute final breaks / labels
        self._k = max(1, min(k, len(opinions)))
        self._breaks = jenks_breaks(opinions, self._k)
        self.labels = _assign_labels(opinions, self._breaks)

        # Build clusters
        clusters: List[individual_cluster] = [individual_cluster(cid, []) for cid in range(self._k)]
        for ag, cid in zip(self.agents, self.labels):
            clusters[cid].add_to_cluster(ag)
        self._clusters = clusters
        return self

    # Convenience accessors that do not break existing code style
    @property
    def clusters(self) -> List[individual_cluster]:
        return self._clusters

    @property
    def breaks(self) -> Optional[List[float]]:
        return self._breaks

    @property
    def k(self) -> Optional[int]:
        return self._k

    def as_assignments(self) -> Dict[int, List[Agent]]:
        return {c.cluster_id: list(c.agents) for c in self._clusters}


