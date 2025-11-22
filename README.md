# AEGIS-K8s  
### Autonomous Evolutionary Governance Intelligence Guardian for Kubernetes  
### Forge Edition with Forge Excalibur logic  
*Design-level README. System is not built yet.*

**Author:** Bradley R. Kinnard  
**Status:** Open source (license to be added)  

---

## Overview
AEGIS-K8s is an offline AI SRE system designed to learn how to operate a synthetic Kubernetes cluster.  
It diagnoses failures, creates multiple recovery plans, simulates their futures, evaluates resilience, and selects the safest plan.  
The system also learns from past runs, including misdiagnoses and suboptimal choices.

This README describes the design structure only. Functionality will be added as development progresses.

---

## 1. Concept and Core Constraints

### Purpose
Build an offline AI SRE engine that practices inside a controlled Kubernetes simulator and improves using feedback loops.

### Hard Constraints
- Runs fully local  
- No real Kubernetes cluster  
- Uses a controlled simulation environment  
- Real LangGraph agents  
- Local vector store and LLM backend  
- Minimal dependency footprint  
- Tiered operation model:  
  - **Tier 1:** Sentinel  
  - **Tier 2:** Legion  
  - **Tier 3:** Evo (optional)

---

## 2. Tech Stack

### Backend
- Python  
- FastAPI  
- pydantic v2  
- LangGraph 0.2+  
- multiprocessing  
- Chroma (local)  
- SQLite  
- JSON structured logs  

### Frontend
- Vite  
- React 19  
- TypeScript  
- TanStack Query  
- Zod  
- shadcn/ui  
- Recharts  

### Dev & Infrastructure
- Docker Compose (LLM, Chroma, backend, frontend)  
- pytest  
- uv or pip  
- mkdocs (optional)  

---

## 3. Repository Structure

## Repository Structure

```plaintext
aegis-k8s/
  backend/
    app/
      main.py
      config.py
      websocket.py
      graphs/
        sentinel_graph.py
        legion_graph.py
    core/
      simulator/
        engine.py
        state.py
        scheduler.py
        chaos.py
        scenarios_loader.py
      reasoning/
        observers.py
        planners.py
        critics.py
        shadowing.py
        propagation_risk.py
        selector.py
        reflectors.py
      memory/
        working_memory.py
        episodic.py
        beliefs.py
        semantic.py
      models/
        state_models.py
        diagnosis_models.py
        plan_models.py
        simulation_models.py
        selector_models.py
        reflection_models.py
        run_models.py
      evolution/
        genome.py
        mutate.py
        evolution_runner.py
    api/
      v1/
        runs.py
        scenarios.py
        system.py
        beliefs.py
        analysis.py
    prompts/
      diagnosis.jinja2
      planning.jinja2
      critic.jinja2
      reflection.jinja2
    tests/
      test_simulator_basic.py
      test_shadowing_logic.py
      test_propagation_risk.py
      test_selector_pareto.py
      test_reflection_rules.py
      test_api_runs.py
      test_memory_roundtrip.py
    pyproject.toml

  frontend/
    src/
      api/
        client.ts
      pages/
        LiveRunPage.tsx
        ScenarioListPage.tsx
        EvolutionPage.tsx
      components/
        layout/
          AppShell.tsx
          Sidebar.tsx
          Topbar.tsx
        runs/
          RunSummary.tsx
          RunList.tsx
        live/
          ClusterView.tsx
          HotspotList.tsx
          PlanTournament.tsx
          PlanDetailsPanel.tsx
          ShadowOutcomeGrid.tsx
          ParetoFrontView.tsx
          BeliefUpdates.tsx
          ReflectionPanel.tsx
        scenarios/
          ScenarioCard.tsx
          ScenarioFilterBar.tsx
        evolution/
          EvolutionSummary.tsx
          GenerationChart.tsx
          ParamTuningTable.tsx
      hooks/
        useLiveRun.ts
        useScenarios.ts
        useBeliefs.ts
      App.tsx
      main.tsx
    package.json
    vite.config.ts

  scenarios/
    smoke/
    full/

  eval/
    smoke_suite/
    full_suite/
    evolution.py

  scripts/
    demo.sh
    test.sh
    evolve.sh

  docs/
    index.md
    tier1_core.md
    tier2_legion.md
    tier3_evo.md
    simulator_design.md
    cognitive_loop.md
    excalibur_logic.md
    api_reference.md
    interview_walkthrough.md

  docker-compose.yml
  .env.example
  README.md
```

---

## 4. Simulator Design

The simulator represents a synthetic Kubernetes cluster.

### Core Entities
- **Node:** CPU, memory, labels, taints, allocations  
- **Pod:** requests, limits, usage, phase, restarts  
- **Workload:** Deployments, StatefulSets, desired replicas  
- **HPA:** metrics, min/max replicas  
- **NetworkPolicy:** ingress rules  

### Chaos Events
- `node_drain`  
- `oom_storm`  
- `burst_traffic`  
- `probe_failure`  
- `netpol_lockout`

### Tick Loop
Each tick applies chaos, updates metrics, runs scheduler, adjusts HPAs, evaluates pod health, and updates state.

### Scenarios
Defined as YAML files with initial state, workloads, HPAs, network policies, chaos schedules, and objectives.

---

## 5. Cognitive Engine & Graphs

### SentinelGraph (Tier 1)
- Generates 3 plans  
- Uses full Excalibur logic  
- Fast and lightweight

### LegionGraph (Tier 2)
- Generates 9 plans  
- Adds critic and debate loop  
- Uses same shared reasoning modules

### Pipeline
1. Observe  
2. Recall  
3. Diagnose  
4. Plan Generation  
5. Propagation Risk  
6. Cascade Shadowing  
7. Pareto Selection  
8. Apply Plan  
9. Reflect  
10. Preemptive Rules

---

## 6. Forge Excalibur Logic

### Cascade Shadowing
Each plan is tested in three futures:
- Main branch  
- Likely-next-chaos branch  
- Worst-historical-chaos branch  
Resilience leans toward the worst-case outcome.

### Propagation Decay Risk
Risk accumulates across steps, exposing brittle multi-step plans.

### Diagnosis Echo Rejection
Incorrect past diagnoses become forbidden hypotheses. Confidence is zeroed if they reappear.

### Hybrid Pareto Selection
Plan selection considers:
- Stability  
- Cost  
- Resilience  
- Negative propagation risk  
Tie-breaking uses propagation risk.

### Procedural Preemption
If another plan would have performed better, a rule is created to bias future planning toward that pattern.

---

## 7. API Design

All endpoints live under `/api/v1`.

### Runs
- Start run  
- Get run details  
- Stream live events  

### Scenarios
- List scenarios  
- Start scenario runs  

### System
- Get current mode  
- Set mode  

### Beliefs
- List beliefs and procedural rules  
- Export beliefs  

### Analysis
- View Pareto vectors, forbidden hypotheses, reflections  

### Evolution (Tier 3 only)
- Start evolution  
- Check status  

---

## 8. Modes & Tiers

### Sentinel
Fast, 3 plans, full Excalibur logic.

### Legion
9 plans, critic and debate.  
Designed for harder scenarios.

### Evo
Optional mode that evolves numeric parameters across generations.

---

## 9. Build Guide (High-Level Summary)

### Tier 1: Weeks 1–4
Simulator → SentinelGraph skeleton → memory and echo rejection → propagation risk → Excalibur logic → frontend basics → smoke suite.

### Tier 2: Weeks 5–6
LegionGraph → critic → debate rounds → UI enhancements → more scenarios.

### Tier 3: Weeks 7–9 (Optional)
Evolution runner → genome design → evolution UI → controlled experiments.

---

## 10. Documentation Set
The `docs/` directory includes:
- Simulator design  
- Tier 1–3 docs  
- Cognitive loop  
- Excalibur logic  
- API reference  
- Interview walkthrough  

These will be filled in during development.

---

## Status
AEGIS-K8s is in design phase only.  
All structures, directories, logic flows, and modes are defined.  
Implementation will follow this layout exactly.

---
