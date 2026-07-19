#!/usr/bin/env python3
"""Wayfinder #7 prototype: split large cohorts with community detection (networkx).
Reads the real graph.json from the #6 spike. Read-only. Emits refined sub-cohorts."""
import json, collections
from pathlib import Path
import networkx as nx
from networkx.algorithms.community import greedy_modularity_communities, louvain_communities

g = json.loads((Path(__file__).parent / "graph.json").read_text())
node = {n["id"]: n for n in g["nodes"]}

G = nx.Graph()
G.add_nodes_from(node.keys())
for e in g["edges"]:
    G.add_edge(e["source"], e["target"])

# cohorts (connected components) from #6
cohorts = collections.defaultdict(list)
for n in g["nodes"]:
    cohorts[n["cohort"]].append(n["id"])
big = sorted([c for c in cohorts.values() if len(c) > 1], key=len, reverse=True)

def describe(ids):
    files = collections.Counter(node[i]["file"] for i in ids)
    pkgs = collections.Counter(node[i]["pkg"] for i in ids)
    hub = max(ids, key=lambda i: node[i]["degree"])
    return hub, files.most_common(1)[0], pkgs

print(f"= INPUT: {len(node)} symbols, {G.number_of_edges()} edges, "
      f"{len(big)} multi-symbol cohorts (largest {len(big[0])}) =\n")

for method_name, fn in [("greedy_modularity", greedy_modularity_communities),
                        ("louvain", lambda H: louvain_communities(H, seed=7))]:
    print(f"########## method: {method_name} ##########")
    for ci, ids in enumerate(big):
        sub = G.subgraph(ids)
        comms = [sorted(c, key=lambda i: (node[i]["layer"], -node[i]["degree"])) for c in fn(sub)]
        comms.sort(key=len, reverse=True)
        hub, topfile, pkgs = describe(ids)
        pkgtxt = ", ".join(f"{k.split('/')[-1]}:{v}" for k, v in pkgs.items())
        print(f"\n  COHORT {ci+1}: {len(ids)} symbols [{pkgtxt}] hub={node[hub]['name']} "
              f"-> split into {len(comms)} sub-groups")
        for si, c in enumerate(comms):
            hub_c = max(c, key=lambda i: node[i]["degree"])
            files = collections.Counter(node[i]["file"] for i in c)
            fdesc = ", ".join(f"{f}×{n}" for f, n in files.most_common(3))
            print(f"    ── sub-group {si+1}: {len(c)} symbols · anchor={node[hub_c]['name']} · files[{fdesc}]")
            for i in c[:8]:
                nd = node[i]
                print(f"         L{nd['layer']}  {nd['name']:<40} ({nd['kind'][:18]:<18}) {nd['file']}")
            if len(c) > 8:
                print(f"         … +{len(c)-8} more")
    print()

# also compute modularity score of the greedy split on the largest cohort
big0 = big[0]
sub0 = G.subgraph(big0)
gm = list(greedy_modularity_communities(sub0))
print(f"= largest cohort ({len(big0)} symbols): greedy_modularity found {len(gm)} communities, "
      f"modularity={nx.algorithms.community.modularity(sub0, gm):.3f} =")
