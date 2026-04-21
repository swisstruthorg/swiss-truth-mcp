# swiss-truth-crewai

CrewAI integration for [Swiss Truth MCP](https://swisstruth.org) — verified facts for AI agent crews.

## Installation

```bash
pip install swiss-truth-crewai
```

## Usage

```python
from crewai import Agent, Task, Crew
from swiss_truth_crewai import SwissTruthSearchTool, SwissTruthVerifyTool

# Create tools
search = SwissTruthSearchTool()
verify = SwissTruthVerifyTool()

# Create agent with Swiss Truth tools
researcher = Agent(
    role="Fact Checker",
    goal="Verify all claims against certified knowledge",
    tools=[search, verify],
)

# Create task
task = Task(
    description="Verify: 'The Swiss Federal Council has 7 members'",
    agent=researcher,
)

# Run crew
crew = Crew(agents=[researcher], tasks=[task])
result = crew.kickoff()
```

## Available Tools

| Tool | Description |
|------|-------------|
| `SwissTruthSearchTool` | Search verified claims by natural language query |
| `SwissTruthVerifyTool` | Fact-check a statement (supported/contradicted/unknown) |
| `SwissTruthSubmitTool` | Submit a new claim for expert review |

## Configuration

```bash
export SWISS_TRUTH_URL="https://swisstruth.org"  # default
export SWISS_TRUTH_API_KEY="sk-..."               # optional
```
