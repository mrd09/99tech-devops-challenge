# DevOps Challenge

Five submissions are organized under [`src/`](src/). Start with each **SOLUTION.md** for the approach, assumptions, trade-offs and validation results; supporting diagrams and evidence are linked below.

## Solutions

| Problem / brief | Submission | Focus | Status |
| --- | --- | --- | --- |
| [1 — Building Castle in the Cloud](src/problem1/problem1.md) | [Solution](src/problem1/SOLUTION.md) | AWS trading architecture: ECS Fargate, DynamoDB, SQS and Valkey; availability, cost and elastic scaling | Design proposal; capacity and latency unmeasured |
| [2 — Diagnose Me Doctor](src/problem2/problem2.md) | [Solution](src/problem2/SOLUTION.md) | NGINX VM at 99% disk usage: protect traffic, identify the writer, recover and prevent recurrence | Troubleshooting plan; no production VM inspected |
| [3 — Debugging issues within system](src/problem3/README.md) | [Solution](src/problem3/SOLUTION.md) | Compose/NGINX/API fixes, connection handling, dependency readiness and monitoring | Fixes locally exercised; original intermittent outage unconfirmed |
| [4 — Ship It Twice](src/problem4/problem4.md) | [Solution](src/problem4/SOLUTION.md) | GitHub Actions: build once, promote backend/frontend through staging and production, verify and roll back | Inactive demo; no GitHub or AWS deployment executed |
| [5 — Fortify the Castle](src/problem5/problem5.md) | [Solution](src/problem5/SOLUTION.md) | Harden Problem 1: identity, network isolation, CI security, protected evidence and recovery | Security design; controls not deployed |

## Diagrams and evidence

| Problem | Supporting material |
| --- | --- |
| 1 | AWS architecture: [PNG](src/problem1/01.diagram/01.aws-architecture.png) / [Mermaid](src/problem1/01.diagram/01.aws-architecture.mmd); order flow: [PNG](src/problem1/01.diagram/02.logic-flow.png) / [Mermaid](src/problem1/01.diagram/02.logic-flow.mmd) |
| 2 | Troubleshooting flow: [PNG](src/problem2/01.diagram/01.troubleshooting-flow.png) / [Mermaid](src/problem2/01.diagram/01.troubleshooting-flow.mmd) |
| 3 | [Runtime commands, outputs and limitations](src/problem3/evidence/01.runtime-checks.md); [Compose configuration](src/problem3/docker-compose.yml) |
| 4 | [Pipeline and AWS diagrams](src/problem4/01.diagrams/README.md); [demo workflows](src/problem4/.github/workflows/) |
| 5 | Marked security architecture: [PNG](src/problem5/01.diagram/01.security-architecture.png) / [Mermaid](src/problem5/01.diagram/01.security-architecture.mmd) |

SVG versions are linked from the solutions. Problem 1's [database/scaling debate](interview-coaching/problem1/01.database-and-scaling-verification.md) and [financial-processing notes](interview-coaching/problem1/02.financial-processing.md) provide optional technical depth.
