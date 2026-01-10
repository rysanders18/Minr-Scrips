# Disco Zoo Decision Tracing Guide

## Overview

You now have comprehensive debugging tools to understand why your model makes poor decisions after 5000 episodes. This guide shows you how to use each tool.

## Quick Start

### 1. Trace a Single Episode (Detailed Analysis)

```bash
# Trace with your trained model
python evaluate.py --trace --model models/your_model.pt --agent dqn --trace-seed 42

# Trace with heatmap agent (optimal baseline) for comparison
python evaluate.py --trace --agent heatmap --trace-seed 42

# Trace multiple episodes
python evaluate.py --trace --model models/your_model.pt --agent dqn --trace-episodes 5
```

**What you'll see:**
- Step-by-step decisions with Q-values
- Probability heatmaps from the probability engine
- Whether agent picks optimal tiles
- Alignment between Q-values and probabilities
- Episode summary with performance metrics

### 2. Interactive Debugging (Manual Step-Through)

```bash
# Start interactive debugger
python interactive_debugger.py --model models/your_model.pt --seed 42

# Inside the debugger:
> s          # Take one step (agent chooses)
> q          # Show Q-values for all actions
> p          # Show probability heatmaps
> c          # Show confirmed tiles
> s 12       # Take specific action (tile 12)
> r 100      # Reset with new seed
> quit       # Exit
```

**Best for:**
- Inspecting specific decisions
- Comparing Q-values vs probabilities manually
- Testing hypotheses about agent behavior

### 3. Standalone Tracer (Direct Script)

```bash
# Trace with debug_tracer.py directly
python debug_tracer.py --model models/your_model.pt --seed 42

# Compare with heatmap agent
python debug_tracer.py --agent heatmap --seed 42
```

---

## What to Look For

### 1. Are Q-values Learning?

**Check in trace output:**
```
Q-Values (Top 5):
  1. Action 12 (row=2, col=2) | Q=2.34
  2. Action  7 (row=1, col=2) | Q=2.21
  3. Action 18 (row=3, col=3) | Q=1.98
  Mean: 1.85, Std: 0.42
```

**Good signs:**
- ✅ Q-values vary significantly (Std > 0.3)
- ✅ Top actions have clearly higher Q-values
- ✅ Q-values range from -5 to +15 (not all close to 0)

**Bad signs:**
- ❌ All Q-values nearly identical (Std < 0.1)
- ❌ Q-values all near zero
- ❌ Random-looking Q-values with no pattern

### 2. Does Agent Use Probability Information?

**Check alignment score:**
```
Alignment score: 0.731
```

**Interpretation:**
- **0.7 - 1.0**: Strong correlation - agent learned to use probabilities ✅
- **0.3 - 0.7**: Moderate correlation - partial learning
- **-0.3 - 0.3**: No correlation - agent ignoring probabilities ❌
- **-1.0 - -0.3**: Negative correlation - agent doing opposite! ❌

**Also check:**
```
Q-value agrees with probability: NO
  Agent picked: P=0.28 (rank #3)
  Optimal would be: Action 7 with P=0.31
```

If agent rarely picks highest probability tile, it's ignoring the probability engine.

### 3. Episode Summary Metrics

```
EPISODE SUMMARY
================================================================================
Reward:               12.10
Animals Found:        1/3
Completion Rate:      33.3%
Moves Used:           15/15

Decision Quality:
  Optimal Moves:      4/15 (26.7%)
  Wasted Moves:       6
  Alignment Score:    0.245
  Avg Q-value Std:    0.087
```

**What this means:**
- **Optimal Moves %**: How often agent picks highest probability tile
  - Good: >60%
  - Okay: 40-60%
  - Poor: <40%

- **Wasted Moves**: Empty tiles when high-probability tiles were available
  - Good: <20% of total moves
  - Poor: >40% of total moves

- **Avg Q-value Std**: How much Q-values differ
  - Good: >0.3 (agent has strong preferences)
  - Poor: <0.1 (agent can't differentiate actions)

---

## Common Problems and Diagnoses

### Problem 1: Q-values All Similar (Std < 0.1)

**Symptoms:**
```
Q-Values (Top 5):
  1. Action 12 | Q=0.023
  2. Action  7 | Q=0.021
  3. Action 18 | Q=0.019
  Mean: 0.018, Std: 0.002  <-- Very low!
```

**Causes:**
- Network not learning (check if loss is decreasing)
- Learning rate too low
- Reward signal too weak
- Network initialized poorly

**Debug:**
```bash
# Check training loss in TensorBoard or console
# Look for: Is loss decreasing over episodes?
```

### Problem 2: Agent Ignores Probability Heatmaps

**Symptoms:**
```
Alignment score: 0.05  <-- Near zero!
Q-value agrees with probability: NO (consistently)
Optimal Moves: 3/15 (20.0%)  <-- Random chance would be ~20%
```

**Causes:**
- Probability channels (7-13) not influencing network
- Network relying only on confirmed channels (0-6)
- Conv layers not processing probability information

**Debug:**
```python
# In interactive debugger:
> p   # Show probabilities - are they non-trivial?
> q   # Show Q-values - do they correlate at all?
```

### Problem 3: Agent Performs Like Random

**Symptoms:**
```
Optimal Moves: 3/17 (17.6%)  <-- ~1/6 is random chance
Animals Found: 0/3           <-- Consistently fails
Alignment score: -0.12       <-- Random/negative
```

**Causes:**
- Model hasn't learned anything (check episodes trained)
- Epsilon still high during evaluation
- Model file loaded incorrectly

**Verify:**
```bash
# Compare to baselines
python evaluate.py --trace --agent heatmap --trace-seed 42  # Optimal
python evaluate.py --trace --agent dqn --model models/your_model.pt --trace-seed 42  # Your agent

# Should see clear difference if model learned anything
```

### Problem 4: Agent Wastes Moves on Empty Tiles

**Symptoms:**
```
STEP 3: Reward: 0.0 (Empty tile)
  Highest Probability: Action 7 (P=0.65)
  Agent picked: Action 12 (P=0.08)
...
Wasted Moves: 8/15 (53.3%)  <-- Over half!
```

**Causes:**
- Not completing partially-found animals
- Exploring randomly when should exploit
- Q-values don't reflect completion bonus

**Debug:**
```bash
# Check if completing animals gives higher Q-values
# In trace, look for steps after finding partial animals
# Does agent prioritize completing vs starting new animals?
```

---

## Comparison Workflow

### Step 1: Trace Heatmap Agent (Baseline)

```bash
python evaluate.py --trace --agent heatmap --trace-seed 42
```

**Expected performance:**
- Optimal Moves: ~95% (by design)
- Alignment: 1.0 (perfect correlation)
- High completion rate

**Save this as your target.**

### Step 2: Trace Your DQN Agent

```bash
python evaluate.py --trace --model models/phase1_episode5000.pt --agent dqn --trace-seed 42
```

**Compare:**
- Is DQN alignment close to 1.0?
- Is DQN optimal move % close to heatmap?
- Are wasted moves similar?

### Step 3: Trace Multiple Seeds

```bash
# Trace 10 episodes to get average behavior
python evaluate.py --trace --model models/your_model.pt --agent dqn --trace-episodes 10
```

Look for consistency across episodes.

### Step 4: Analyze JSON Logs

All traces are saved to `results/trace_*.json`:

```python
import json
import numpy as np

# Load trace
with open('results/trace_dqn_ep1_seed42.json', 'r') as f:
    data = json.load(f)

# Analyze
summary = data['episode_summary']
steps = data['steps']

# Check alignment per step
alignments = [step['alignment_score'] for step in steps]
print(f"Mean alignment: {np.mean(alignments):.3f}")
print(f"Std alignment: {np.std(alignments):.3f}")

# Check if Q-values improve over episode
q_stds = [step['q_details']['std_valid'] for step in steps if step['q_details']]
print(f"Q-value differentiation: {np.mean(q_stds):.3f}")
```

---

## Advanced: Checking Specific Hypotheses

### Hypothesis 1: "Agent always picks center tiles"

```bash
# Trace multiple episodes and check
python evaluate.py --trace --model models/your_model.pt --trace-episodes 5

# Look for action distribution in output
# Center tiles are: 6,7,8, 11,12,13, 16,17,18
```

### Hypothesis 2: "Agent doesn't complete partially-found animals"

```python
# In interactive debugger:
> s  # Step until you find a partial animal
> q  # Check Q-values - are adjacent tiles high?
> p  # Check probabilities - are they updated correctly?
```

### Hypothesis 3: "Probability engine gives bad heatmaps"

```bash
# Trace heatmap agent - if it performs poorly, engine is the issue
python evaluate.py --trace --agent heatmap --trace-episodes 10

# Expected: >90% optimal moves, >2.0 animals/episode
```

---

## Integration with Training

### Check Progress Over Training

```bash
# Trace at different checkpoints
python evaluate.py --trace --model models/phase1_episode1000.pt --agent dqn --trace-seed 42
python evaluate.py --trace --model models/phase1_episode3000.pt --agent dqn --trace-seed 42
python evaluate.py --trace --model models/phase1_episode5000.pt --agent dqn --trace-seed 42

# Compare alignment scores and optimal move %
# Should improve over time!
```

### Diagnose Training Issues

If performance doesn't improve:

1. **Check loss is decreasing:**
   ```bash
   tensorboard --logdir logs/
   ```

2. **Check epsilon decay:**
   - At 5000 episodes, epsilon should be near 0.01
   - Training log shows epsilon per 100 episodes

3. **Check target network updates:**
   - Should update every 5000 steps
   - ~60,000 steps at 5000 episodes × 12 steps/episode
   - = 12 target updates (sufficient)

---

## Summary

**To debug poor performance after 5000 episodes:**

1. **Run traces:**
   ```bash
   python evaluate.py --trace --model models/your_model.pt --agent dqn --trace-episodes 5
   python evaluate.py --trace --agent heatmap --trace-episodes 5
   ```

2. **Check key metrics:**
   - Alignment score (should be >0.5)
   - Q-value std (should be >0.2)
   - Optimal moves % (should be >40%)

3. **Compare to baseline:**
   - Heatmap agent should perform well (~95% optimal)
   - DQN should be learning toward heatmap behavior

4. **Use interactive mode to dig deeper:**
   ```bash
   python interactive_debugger.py --model models/your_model.pt
   ```

5. **Identify root cause:**
   - Network not learning → Check loss/gradients
   - Ignoring probabilities → Network architecture issue
   - Random behavior → Model not loaded/trained correctly

Good luck debugging! The tools will show you exactly what the agent is "thinking" at each step.
