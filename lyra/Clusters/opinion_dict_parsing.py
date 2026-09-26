import os, sys, json
import numpy as np


with open("Clusters/agent_opinions.json", "r", encoding="utf-8") as f:
    dct = json.load(f)
    
agents, opinion_vals = [], []
for agent, opinions in dct.items():
    agents.append(agent)
    opinion_vals.append(opinions)

arr = np.array(opinion_vals)

print(arr)

arr = arr.transpose()

print(arr)