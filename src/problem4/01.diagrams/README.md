# Problem 4 — Diagram references

Read the [submission](../SOLUTION.md) first. These diagrams describe the inactive demo and its assumed AWS setup.

| Order | Review question | Mermaid | PNG / SVG |
| --- | --- | --- | --- |
| 01. Pipeline/promotion | How do checks, stages and approvals order the release? | [Code](01.pipeline-and-promotion.mmd) | [PNG](01.pipeline-and-promotion.png) · [SVG](01.pipeline-and-promotion.svg) |
| 02. AWS deployment/traffic | What do OIDC, roles, CodeDeploy, EC2, S3 and CloudFront do? | [Code](02.aws-deployment-and-traffic.mmd) | [PNG](02.aws-deployment-and-traffic.png) · [SVG](02.aws-deployment-and-traffic.svg) |

The pipeline gate is the first deploy job's condition; `needs:` sets promotion order. AWS roles distinguish GitHub deployment access, CodeDeploy rollout control and EC2 artifact/secret retrieval. Staging/production use separate destinations.

See [required setup](../SOLUTION.md#required-setup) and [scope/limitations](../SOLUTION.md#deliberately-left-out). The two applications are promoted in order; their release is not atomic.
