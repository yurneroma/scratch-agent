# scratch-agent

A coding agent built from scratch to learn how agents work. Plan: [ROADMAP.md](ROADMAP.md).

## Setup

```bash
uv sync
cp .env.example .env   # then fill in GLM_API_KEY
uv run scratch-agent --ping
```

## Layout

- `src/scratch_agent/`: agent code
- `notes/dayNN.md`: daily learning notes
- `evals/`: fixed evaluation tasks (from Day 5)
