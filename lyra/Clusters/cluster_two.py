import os, sys, re, random, json
from jenkspy.core import jenks
import hdbscan
import numpy as np
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
import matplotlib.pyplot as plt
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

#from Agent.agent import Agent
from typing import List, Optional, Dict, Any
import statistics
import math
import jenkspy


data_fpath = "Clusters/data.txt"


#N: total number of points
#k: number of clusters
def random_split(N, k):
    points = sorted([0] + [random.random() * N for _ in range(k - 1)] + [N])
    return [int(points[i+1] - points[i]) for i in range(k)]


def gen_data(num_points, num_clusters, max_value, spread, return_clusters = False, no_overlap = True):
    min_cluster_size = max(1, (num_points / num_clusters) // 4)
    
    splits = []
    good_splits = False
    # Splits a number into a list of numbers that add up to the input number. A good split is when each "cluster" is bigger than the min size.
    while not good_splits:
        splits = random_split(num_points, num_clusters)
        if all([split > min_cluster_size for split in splits]):
            good_splits = True
            
    data = []
    for split in splits:
        cluster = np.random.normal(random.random() * max_value, spread, split)
        data.append(cluster)
        
    if return_clusters:
        return data
    return [int(x) for cluster in data for x in cluster]
    

def GVF(data, clusters):
    # GVF = (SDAM - SDCM) / SDAM
    mean = sum(data) / len(data)
    SDAM = sum([(x - mean)**2 for x in data])
    SDCM = 0
    for cluster in clusters:
        cluster_mean = sum(cluster) / len(cluster)
        cluster_sum = sum([(x - cluster_mean)**2 for x in cluster])
        SDCM += cluster_sum
    return (SDAM - SDCM) / SDAM


def get_clusters(data, k):
    # Ensure k doesn't exceed the number of unique values
    unique_values = len(set(data))
    k = min(k, unique_values)
    if k < 1:
        k = 1
    breaks = jenkspy.jenks_breaks(data, n_classes=k)
    clusters = []
    break_pointer = 1
    item_pointer = 0
    while break_pointer < len(breaks) and item_pointer < len(data) and break_pointer < len(breaks):
        cluster = []
        while item_pointer < len(data) and data[item_pointer] <= breaks[break_pointer] and break_pointer < len(breaks):
            cluster.append(data[item_pointer])
            item_pointer += 1
        clusters.append(cluster)
        break_pointer += 1
    return clusters
        

def get_data(path, d_num):
    with open(path, "r") as f:
        datasets = f.readlines()
        
    for dataset in datasets:
        if f"dataset_{d_num}" in dataset:
            true_num_clusters = re.findall("num_clusters.*", dataset)
            true_num_clusters = int(true_num_clusters[0].split()[-1])
            d = re.findall(r"\[.*\]", dataset)[0]
            nums = re.findall(r"\d+\.?\d*", d)
            nums = list(map(float, nums))
            return nums, true_num_clusters


def jenks_test(dataset):
    data, true_num_clusters = get_data(data_fpath, dataset)
    data.sort()
    unique_values = len(set(data))
    max_clusters = min(10, unique_values)  # Don't try more clusters than unique values
    all_gvfs = []
    for i in range(1, max_clusters + 1):
        clusters = get_clusters(data, i)
        #print(*[len(cluster) for cluster in clusters], sep = ", ")
        gvf = GVF(data, clusters)
        all_gvfs.append(gvf)
        
    print(f"GVFs: {all_gvfs}")
    print(f"True num of clusters: {true_num_clusters}")
    
    
def hdb_test(dataset, min_size=2, eps=1.5, return_labels=False):
    data, true_num_clusters = get_data(data_fpath, dataset)
    data = np.array(data).reshape(-1, 1)
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_size,
        min_samples=1,
        cluster_selection_method='eom',
        cluster_selection_epsilon=eps     # 1.0 → 2.0 is usually good
    )
    labels = clusterer.fit_predict(data)
    mx = max(labels) + 1
    if return_labels:
        return mx, true_num_clusters, labels
    return mx, true_num_clusters


def hdbscan_cluster(dataset, min_size=2, eps=0.1):
    data = np.array(dataset).reshape(-1, 1) # Data needs to be a np.array column
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_size,
        min_samples=1,
        cluster_selection_method='eom',
        cluster_selection_epsilon=eps
    )
    labels = clusterer.fit_predict(data)
    return labels


def create_data(num_points, num_clusters, max_value, spread, massgen = False):
    data = gen_data(num_points, num_clusters, max_value, spread)
    
    inp = ""
    if not massgen:
        print(data)
        plt.hist(data)
        plt.show()
        inp = input("Save data? Y/N: ")
    if massgen or inp == "Y":
        if not os.path.exists(data_fpath):
            with open(data_fpath, "w") as f:
                f.write("datasets = 0")
        with open(data_fpath, "r") as f:
            txt = f.readlines()
            
        num_datasets = int(re.findall(r"\d+", txt[0])[0])
        num_datasets += 1
        txt.append(f"dataset_{num_datasets}: {data}, num_clusters = {num_clusters}")
        txt[0] = f"datasets = {num_datasets}"
        
        for i in range(len(txt)):
            if "\n" not in txt[i]:
                txt[i] += "\n"
            
        print(txt)
        
        with open(data_fpath, "w") as f:
            f.writelines(txt)
            
        print(f"Saved as dataset {num_datasets}")
    

def plot_number_line(list1, list2):
    """
    Generally used to plot 2 different lists on the same number line with different colors.
    Using to compare data to centroids
    """
    list1 = sorted(list1)
    list2 = sorted(list2)
    all_points = list1 + list2
    plt.hlines(0, min(all_points) - 1, max(all_points) + 1)
    
    plt.plot(list1, [0]*len(list1), 'o', label='Data')
    plt.plot(list2, [0]*len(list2), 'o', label='Cluster centroids')
    
    for p in list1:
        plt.text(p, -0.05, str(p), ha='center', va='top', color='blue')
    for p in list2:
        plt.text(p, -0.1, str(p), ha='center', va='top', color='red')

    plt.yticks([])
    plt.xlabel("Number Line")
    plt.legend()
    plt.show()


def opinion_dict_parse(path):
    with open(path, "r", encoding="utf-8") as f:
        opinion_dict = json.load(f)
    agents, opinions = [], []
    for agent, opinion in opinion_dict.items():
        agents.append(agent)
        opinions.append(opinion)
    
    opinions = np.array(opinions).transpose()
    return agents, opinions

        
if __name__ == "__main__":
    help = """
    Inputs:
        test: test a specific dataset from data.txt
        create: generate a dataset to test on and output into data.txt
        massgen: Creates a lot of datasets. Points and number of clusters will be randomized. The number of points and max value can be set.
        masstest: Test all of the datasets in data.txt
        hdbtest: Test clustering by HDBSCAN
        masshdbtesting: Test all of the datasets in data.txt using HDBSCAN
        visualize: visualize datasets
        wipe: Wipe the contents of the current data file stored in data_fpath.
    """
    inp = input("help, jenkstest, hdbtest, create, massgen, masstesting, masshdbtesting, visualize, or wipe: ")
    if inp == "help":
        print(help)
    elif inp == "jenkstest":
        inp = int(input("Which dataset?: "))
        jenks_test(inp)
    elif inp == "create":
        # num_points, num_clusters, max_value, spread
        inp = input("Specify parameters space separated (num_points num_clusters max_value spread): ")
        points, nc, mv, sp = list(map(int, inp.split()))
        create_data(points, nc, mv, sp)
    elif inp == "massgen":
        inp = input("Specify general parameters space separated (num_points max_value spread num_datasets min_num_clusters max_num_clusters): ")
        num_points, max_value, spread, num_iterations, min_num_clusters, max_num_clusters = list(map(int, inp.split()))
        for i in range(num_iterations):
            num_clusters = random.randint(min_num_clusters, max_num_clusters)
            create_data(num_points, num_clusters, max_value, spread, massgen=True)
    elif inp == "masstesting":
        with open(data_fpath, "r") as f:
            txt = f.readline()
            num_datasets = int(re.findall(r"\d+", txt)[0])
        for i in range(1, num_datasets + 1):
            jenks_test(i)
    elif inp == "hdbtest":
        inp = int(input("Which dataset?: "))
        result, true, labels = hdb_test(inp, min_size=2, eps=0.1, return_labels=True)
        print(f"Prediction: {result}, true cluster num: {true}")
        print(f"Labels: {labels}")
    elif inp == "masshdbtesting":
        with open(data_fpath, "r") as f:
            txt = f.readline()
            num_datasets = int(re.findall(r"\d+", txt)[0])
        for j in range(0, 41):
            print(f"Epsilon: {j/10}")
            total_diffs = 0
            for i in range(1, num_datasets + 1):
                # SET THE MIN_CLUSTER_SIZE v PROPERLY!!!! Since we're working with a small amount of agents, a small min cluster size is absolutely necessary.
                result, true = hdb_test(i, 2, j/10)
                print(f"Dataset: {i}, prediction: {result}, true cluster num: {true}")
                total_diffs += abs(result - true)
            print(f"&&& Inverse Effectiveness (higher is worse) &&&&&&&&: {total_diffs}")
            print("--------------")
    elif inp == "visualize":
        done = False
        while not done:
            inp = int(input("Which dataset?: "))
            data, true_num_clusters = get_data(data_fpath, inp)
            print(f"True number of clusters for this data: {true_num_clusters}")
            plt.hist(data)
            plt.show()
            ask = input("Would you like to view another dataset (y/n)?: ")
            if ask == "n":
                done = True
    elif inp == "wipe":
        if os.path.exists("data.txt"):
            os.remove(data_fpath)
            print("\nFile deleted. When create or massgen is run, it'll be created automatically again.\n")
        else:
            print("\nThe data.txt file doesn't exist. Which is good from my persective as the data wipe handler.\n")
    elif inp == "test":
        agents, opinions = opinion_dict_parse("Clusters/agent_opinions.json")
        with open(data_fpath, "w") as f:
            f.write(f"datasets = {len(opinions)}\n")
            for i in range(len(opinions)):
                #adj = list(map(float, (opinions[i] * 4) ** 3))
                adj = list(map(float, opinions[i]))
                f.write(f"dataset_{i+1}: {adj}, num_clusters = 3\n")
    else:
        print("Bad input")