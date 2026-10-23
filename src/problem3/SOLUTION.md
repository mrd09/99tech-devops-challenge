# Problem 3 — Debugging report

**Outcome:** the supplied copy already includes the historical proxy-port correction. Healthy short load tests did not reproduce the reported intermittent server outage. Code review and a controlled SQL-error probe identified a connection-leak pattern; the submitted fixes add safe queries, meaningful readiness and bounded dependency failures.

## Problems found

### Infrastructure config — examine first

| Finding | Evidence / consequence |
| --- | --- |
| Historical upstream/listener mismatch | The earlier transcript records `api:3001` versus Node's `3000`, causing 502. the current baseline returned 200. |
| Startup order without readiness | `depends_on` alone did not wait for usable dependencies. No health checks or restart policy were configured. These are resilience gaps, not a demonstrated intermittent-incident cause. |
| Unclear persistence/configuration | No explicit named PostgreSQL volume. `postgres/init.sql` is unmounted: its `max_connections=20` is inactive; runtime reports **100**. The empty local `nginx/nginx.conf` is also unmounted. |
| Incomplete health routing | NGINX returned 404 for `/status`; `/` returns its own welcome text and does not exercise the API. |

### App code

- A successful `pool.connect()` followed by a failed query skips `db.release()`. Repetition can exhaust the pool. The normal `SELECT NOW()` path releases successfully, which explains why healthy traffic need not expose this bug.
- `/status` always returned 200 without checking PostgreSQL or Redis. The users endpoint requires both a SQL read and a Redis write.
- No explicit pool-acquisition/query/Redis command deadlines; Redis could queue work during disconnection. Missing idle-pool error handling could also leave dependency interruptions unhandled.
- Errors exposed internal messages to clients. This sample endpoint returns a database timestamp, not user records.

### Diagnosis from real running

From `src/problem3`:

```sh
docker compose -f docker-compose.yml up --build -d
curl -i http://127.0.0.1:8080/api/users
wrk -t2 -c50 -d5s --latency http://127.0.0.1:8080/api/users
```

The actual review added `-p challenge-p3-review` to isolate its containers.

| Executed check | Observed result |
| --- | --- |
| Baseline load | **4,985 requests; 990.28 RPS**, p99 253.02 ms; no socket/HTTP errors reported by wrk. |
| Fixed-stack load, same parameters | **4,279 requests; 850.45 RPS**, p99 411.98 ms; no socket/HTTP errors reported by wrk. |
| Controlled SQL-error probe | Original release pattern held two clients and timed out on the next acquisition; `pool.query()` recovered with zero checked-out clients. This used intentional SQL errors outside the API handler. |
| Controlled dependency failures | PostgreSQL stopped, Redis stopped, or Redis rejecting writes: `/status` and `/api/users` returned **503**, `/livez` stayed **200**. Recovery required no API restart. |

NGINX recorded client-disconnect 499s around load-test termination. The [historical 400-connection run](../../tasks/problem3/inventory/evidence/01.record-steps.md) separately recorded **157 connect / 25 read errors**; it was not error-free. Neither short run establishes capacity or the original failure's cause. The slower fixed run is not evidence of a performance improvement.

Coordinate the user's exact route, timestamp, timeout and request ID, then correlate client/server evidence. [Commands, outputs and limitations](evidence/01.runtime-checks.md).

## Fixes applied

### Infrastructure

- [Compose](docker-compose.yml): dependency health checks and healthy-start conditions, restart policies, bounded container logs, named PostgreSQL data volume, and localhost-only ingress. The existing data needs migration before changing a production volume.
- [NGINX](nginx/conf.d/default.conf): API port 3000, `/status` and `/livez` routes, explicit proxy timeouts, Docker DNS re-resolution and a read-only configuration mount.
- Health conditions gate Compose startup. An unhealthy flag alone does not restart a container or remove it from NGINX traffic.

### Application code

- [API handler](api/src/index.js): use [`pool.query()`](https://node-postgres.com/features/pooling) for single statements; add pool/error handling, PostgreSQL acquisition/statement/query limits and Redis command/connect limits. Disable Redis offline queuing; retain background reconnection.
- **`/status` = readiness:** bounded PostgreSQL query plus a short-lived Redis **write**, returning 200/503. A Redis `PING` can succeed while required writes fail; the controlled test verified this distinction.
- **`/livez` = liveness:** process response independent of dependency health. Dependency failures return generic 503s with correlated internal logs.
- [Container build](api/Dockerfile): committed dependency lockfile, `npm ci` and non-root execution. The API handles SIGTERM/SIGINT with bounded draining and dependency cleanup.

### Monitoring and alerts

**Implemented:** NGINX JSON logs include normalized endpoint, HTTP status, total/upstream duration, upstream outcome and request ID. API failure logs use the same ID; intentional 503s were correlated across both layers.

**Proposed, not deployed:** ship logs through the existing collector or Alloy → Loki/Grafana. Alert on endpoint 5xx **>1% over five minutes with ≥100 requests**, two consecutive external-probe failures, latency deterioration, pool waits, dependency latency, resource pressure and restarts. Track 499 separately; connection failures may never reach access logs. Probe `/api/users` and `/status` externally.

### Production prevention

Recommended controls beyond this local submission:

- Gate CI/releases on the real proxied route, [readiness](https://docs.docker.com/compose/how-tos/startup-order/), dependency failure/recovery and sustained-load checks. Agree an availability/latency objective; none is supplied here.
- Budget aggregate API pools against PostgreSQL capacity, including admin/probe headroom; tune from measurements. The unused 20-connection SQL sample needs review before activation.
- Test backups/restores, volume migration and rollback. A named volume is not a backup; one Compose host remains a failure boundary.

## Additional suggestions

- Replace supplied local-demo credentials with runtime secrets and a least-privilege database role.
- Refresh supported base images, pin deployment digests, and scan dependencies/images in CI. Set CPU/memory limits from profiling.
- Use multiple application/router instances with readiness-based traffic admission for production availability.
- Decide whether `last_call` tracking is essential. If optional, define degraded behavior so that telemetry failure need not reject otherwise valid reads.

**Verification:** Compose configuration, Node syntax, container build, NGINX syntax, HTTP/load, controlled dependency checks and clean shutdown passed. Review containers were removed afterward; database volumes were retained. Sustained capacity and the original intermittent report remain unresolved. [Full evidence](evidence/01.runtime-checks.md) · [Task](README.md).
