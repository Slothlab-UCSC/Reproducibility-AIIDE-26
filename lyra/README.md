# LegerLegends

An extended implementation of the Lyra opinion dynamics simulation system, featuring natural language conversation generation using Large Language Models (LLMs). This project simulates believable virtual characters with evolving opinions, attitudes, and uncertainties, generating dynamic dialogue that reflects their internal states.

## Overview

LegerLegends extends the original Lyra paper's work by:
- **LLM-based conversation generation**: Produces natural, flowing dialogue from structured interaction events
- **Template-based dialogue**: Provides mathematically-grounded dialogue templates for verification
- **Dual clustering support**: Supports both Jenks Natural Breaks and HDBSCAN clustering algorithms
- **Comprehensive logging**: Saves raw event dictionaries, LLM-generated conversations, and agent state histories

## Installation

### Prerequisites

- Python 3.8 or higher
- LM Studio (for local LLM hosting) OR OpenAI API key

### Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `jenkspy==0.4.1` - Clustering algorithm
- `hdbscan>=0.8.0` - Alternative clustering method
- `numpy==2.3.4` - Numerical computations
- `matplotlib>=3.5.0` - Graph generation
- `openai>=1.0.0` - LLM API client

## Configuration

### 1. Configure Agents

Edit `Simulation/config.py` to customize agents:

```python
AGENTS = [
    Agent("AgentName", opinion=-0.6, attitude=-0.7, uncertainty=0.1, bias=-0.8),
    # Add more agents...
]
```

**Agent Parameters:**
- `opinion`: Initial opinion on the topic (-1.0 to 1.0)
- `attitude`: General disposition/outlook (-1.0 to 1.0)
- `uncertainty`: How uncertain the agent is (0.0 to 1.0)
- `bias`: Agent's inherent bias (-1.0 to 1.0)

### 2. Configure LLM (Optional)

In `Simulation/config.py`, modify `LLM_CONFIG`:

**For LM Studio (local):**
```python
LLM_CONFIG = {
    "base_url": "http://127.0.0.1:1234/v1",
    "api_key": "lm-studio",
    "model_name": "google/gemma-3n-e4b"
}
```

**For OpenAI API:**
```python
LLM_CONFIG = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "your-api-key-here",
    "model_name": "gpt-4"  # or "gpt-3.5-turbo"
}
```

### 3. Configure Topic and Opinion Axis

In `Simulation/config.py`:
- `TOPIC`: The topic being discussed (e.g., "Gun_Control")
- `OPINION_AXIS`: Labels for opinion extremes (min_label, max_label)

## Running the Simulation

### Basic Usage

```bash
python Simulation/main.py
```

### What Happens

1. **Agent Initialization**: Agents are created with their initial states
2. **Multi-Round Simulation**: 
   - Agents are clustered by opinion
   - Interactions occur within clusters
   - Agent opinions/attitudes update based on cluster influence
   - Public opinion forms when ≤3 clusters remain
3. **Output Generation**:
   - Trajectory graphs (opinion, attitude, uncertainty) saved to `graphs/`
   - Conversation logs saved to `Simulation/Interactions/round-*/`
   - Agent state histories saved to `Knowledge_Base/Agent/agent_*/`

### Output Files

- **Graphs**: `graphs/opinion_trajectories.png`, `attitude_trajectories.png`, `uncertainty_trajectories.png`
- **Raw Conversations**: `Simulation/Interactions/round-{N}/conversation-{ID}.jsonl`
- **LLM Conversations**: `Simulation/Interactions/round-{N}/conversation-{ID}_llm.txt`
- **Agent Logs**: `Knowledge_Base/Agent/agent_{ID}/agent_{ID}.json`

## Project Structure

```
LegerLegends/
├── Agent/                 # Agent class implementation
├── Clusters/             # Clustering algorithms (Jenks, HDBSCAN)
├── Knowledge_Base/       # Knowledge base and agent state storage
│   ├── Agent/           # Agent-specific logs and knowledge
│   └── Master_KB/       # Master knowledge base
├── Simulation/          # Main simulation code
│   ├── config.py        # Configuration (agents, LLM, topic)
│   ├── main.py         # Entry point
│   ├── simulation.py   # Core simulation logic
│   ├── interactions.py # Interaction engine
│   └── llm.py          # LLM conversation generation
├── graphs/             # Generated trajectory graphs
└── requirements.txt    # Python dependencies
```

## Key Features

### 1. Natural Language Conversations

The system generates three conversation formats:
- **LLM-generated**: Natural, flowing dialogue using language models
- **Template-based**: Mathematically-grounded dialogue with explicit opinion values
- **Raw events**: Structured JSON dictionaries of interaction events

### 2. Opinion Dynamics

Agents' opinions evolve based on:
- Cluster influence (agents in the same cluster)
- Public opinion strength
- Individual uncertainty and bias
- Knowledge sharing between agents

### 3. Clustering Methods

- **Jenks Natural Breaks**: Original Lyra clustering method
- **HDBSCAN**: Density-based clustering for flexible group formation

### 4. Comprehensive Logging

All agent states, interactions, and conversations are logged for analysis and debugging.

## Customization

### Adjusting Simulation Parameters

In `Simulation/main.py`, modify:
```python
results = run_simulation(
    agents, 
    max_rounds=10,              # Number of simulation rounds
    enable_knowledge_sharing=False  # Enable/disable knowledge sharing
)
```

### Changing Clustering Method

In `Simulation/simulation.py`, line ~113:
```python
c = cluster(self.agents).cluster_by_jenks()  # or .cluster_by_hdbscan()
```

## Troubleshooting

### LLM Not Working

- **LM Studio**: Ensure LM Studio is running with the model loaded at `http://127.0.0.1:1234`
- **OpenAI**: Verify your API key is correct and you have sufficient credits
- The simulation will continue without LLM generation, using template-based conversations

### No Conversations Generated

- Check that agents are being clustered (should see "Number of clusters: X" in output)
- Verify agents have different opinions to enable interactions

## Citation

This project extends the work described in:
- Azad, S., & Martens, C. (2018). "Lyra: Simulating Believable Opinionated Virtual Characters." *Proceedings of the AAAI Conference on Artificial Intelligence and Interactive Digital Entertainment*.


