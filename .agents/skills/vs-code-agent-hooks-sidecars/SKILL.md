---
name: vs-code-agent-hooks-sidecars
description: Understanding VS Code agent framework hooks and sidecars for automation
applyTo:
  - pattern: "(hooks|sidecars|hook|sidecar)"
    context: "agent automation, agent framework, workflow"
keywords:
  - hooks
  - sidecars
  - PreToolCall
  - PostToolCall
  - PreInvocation
  - PostInvocation
  - cron
  - automation
---

# VS Code Agent Hooks & Sidecars

## Overview
Hooks and sidecars are VS Code agent framework features for automation and background execution.

## Hooks
**Definition:** Script triggers that execute at specific points in the agent evaluation lifecycle.

### Hook Types
| Hook | Timing | Use Case |
|------|--------|----------|
| **PreToolCall** | Before agent calls a tool | Validate inputs, log parameters |
| **PostToolCall** | After tool completes, before processing results | Transform output, trigger downstream tasks |
| **PreInvocation** | Before agent starts evaluating a user request | Initialize context, load resources |
| **PostInvocation** | After agent completes the full turn | Cleanup, save state, trigger sidecars |
| **STOP** | When agent ends turn (final state) | Final logging, report generation |

### Example: Auto-generate plots after SPICE simulation
```bash
# PostToolCall hook
# Trigger: After run_spice.py completes
# Action: Automatically run plot_exponential_results.py
if [ "$TOOL_NAME" = "run_in_terminal" ] && [ "$COMMAND_CONTAINS" = "run_spice.py" ]; then
  cd hardwired/exponential/simple_vpo
  python plot_exponential_results.py
fi
```

## Sidecars
**Definition:** Background jobs managed by VS Code agent manager. Can run on schedule (cron) or perpetually.

### Sidecar Modes
- **Cron-scheduled:** Run at intervals (e.g., every 5 minutes, hourly)
- **Perpetual:** Keep running continuously in background

### Example: Auto-simulate on file changes
```yaml
# Sidecar definition
name: exponential-converter-auto-sim
type: file-watcher
path: hardwired/exponential/simple_vpo/*.cir
trigger: on-change
action: |
  python scripts/run_spice.py $CHANGED_FILE
  cd $(dirname $CHANGED_FILE)
  python plot_exponential_results.py
```

### Example: Periodic simulation audit
```yaml
# Cron-based sidecar
name: nightly-validation
type: cron
schedule: "0 2 * * *"  # 2 AM daily
action: |
  cd hardwired/exponential/simple_vpo
  python scripts/run_spice.py exponential_converter.cir
  python plot_exponential_results.py
  # Report results
```

## Hardwired-Design Applications

### For Exponential Converter Workflow
1. **PostToolCall hook** → After `run_spice.py`, auto-run `plot_exponential_results.py`
2. **Sidecar watcher** → Monitor `.cir` file changes, re-simulate on save
3. **PostInvocation hook** → Update SIMULATION_RESULTS.md with latest metrics

### For Multi-Subsystem Design
- **Sidecar cron** → Nightly full-circuit validation
- **PreToolCall hook** → Check BOM consistency before netlist saves
- **PostToolCall hook** → Regenerate design documentation

## Configuration
Hooks and sidecars are typically configured in:
- `.agent.md` or `.agents/AGENTS.md`
- VS Code workspace settings
- Agent custom instructions

## Best Practices
- Use **PostToolCall** for immediate downstream tasks (plotting, validation)
- Use **sidecars** for periodic checks or long-running background tasks
- Keep hook scripts lightweight to avoid blocking agent evaluation
- Log sidecar execution for debugging
- Test hooks locally before deploying to agent

---
*Reference: VS Code Agent Framework documentation*
