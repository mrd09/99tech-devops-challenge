const express = require("express");
const { Pool } = require("pg");
const Redis = require("ioredis");
const { randomUUID } = require("node:crypto");

const app = express();
app.disable("x-powered-by");
let draining = false;

const poolMax = Number(process.env.DB_POOL_MAX || 10);
if (!Number.isSafeInteger(poolMax) || poolMax < 1) {
  throw new Error("DB_POOL_MAX must be a positive integer");
}

const pool = new Pool({
  host: process.env.DB_HOST,
  user: process.env.DB_USER || "postgres",
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME || "postgres",
  port: 5432,
  max: poolMax,
  connectionTimeoutMillis: 1000,
  idleTimeoutMillis: 10000,
  statement_timeout: 1000,
  query_timeout: 1500,
  application_name: "problem3-api",
});

const redis = new Redis({
  host: process.env.REDIS_HOST,
  port: 6379,
  connectTimeout: 1000,
  commandTimeout: 1000,
  enableOfflineQueue: false,
  maxRetriesPerRequest: 1,
  autoResendUnfulfilledCommands: false,
  retryStrategy: (attempt) => Math.min(attempt * 100, 1000),
});

function logFailure(event, err, requestId) {
  console.error(JSON.stringify({
    event,
    request_id: requestId,
    code: err.code,
    message: err.message,
  }));
}

pool.on("error", (err) => logFailure("postgres_idle_error", err));
redis.on("error", (err) => logFailure("redis_connection_error", err));

app.use((req, res, next) => {
  const incoming = req.get("X-Request-ID");
  req.requestId = incoming && /^[A-Za-z0-9_-]{1,64}$/.test(incoming)
    ? incoming : randomUUID();
  res.set("X-Request-ID", req.requestId);
  next();
});

app.get("/livez", (_req, res) => {
  res.json({ status: "alive" });
});

app.get("/api/users", async (req, res) => {
  if (draining) {
    return res.status(503).json({ ok: false, error: "draining" });
  }
  try {
    // One statement: pool.query() releases/removes its client on every outcome.
    const result = await pool.query("SELECT NOW()");
    await redis.set("last_call", String(Date.now()));
    res.json({ ok: true, time: result.rows[0] });
  } catch (err) {
    logFailure("users_dependency_failure", err, req.requestId);
    res.status(503).json({
      ok: false,
      error: "dependency_unavailable",
      request_id: req.requestId,
    });
  }
});

app.get("/status", async (req, res) => {
  if (draining) {
    return res.status(503).json({ status: "not_ready", reason: "draining" });
  }
  // The users route requires a Redis write, so PING alone is insufficient.
  const checks = await Promise.allSettled([
    pool.query("SELECT 1"),
    redis.set("__health:api", "ready", "EX", 15),
  ]);
  const dependencies = {};
  for (const [index, dependency] of ["postgres", "redis"].entries()) {
    const check = checks[index];
    dependencies[dependency] = check.status === "fulfilled" ? "ok" : "unavailable";
    if (check.status === "rejected") {
      logFailure(`${dependency}_readiness_failure`, check.reason, req.requestId);
    }
  }
  const ready = checks.every((check) => check.status === "fulfilled");
  res.status(ready ? 200 : 503).json({
    status: ready ? "ready" : "not_ready",
    dependencies,
  });
});

const server = app.listen(3000, () => {
  console.log(JSON.stringify({ event: "api_listening", port: 3000 }));
});

function shutdown(signal) {
  if (draining) return;
  draining = true;
  console.log(JSON.stringify({ event: "api_draining", signal }));
  const deadline = setTimeout(() => {
    redis.disconnect();
    process.exit(1);
  }, 10000);
  deadline.unref();
  server.close(async (err) => {
    try {
      await pool.end();
      await redis.quit();
    } catch (closeError) {
      logFailure("shutdown_error", closeError);
      err = closeError;
    } finally {
      redis.disconnect();
      clearTimeout(deadline);
      process.exit(err ? 1 : 0);
    }
  });
  server.closeIdleConnections();
}

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
