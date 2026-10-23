"""Deploy a versioned CodeDeploy revision; restore the prior revision on failure."""
import json
import os
from pathlib import Path
import re
import sys
import time

from aws_common import aws, catch_termination, fetch, public_url, record, required, retry


def wait(deployment_id):
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        info = aws("deploy", "get-deployment", "--deployment-id", deployment_id)["deploymentInfo"]
        if info["status"] == "Succeeded":
            return info
        if info["status"] in ("Failed", "Stopped"):
            raise RuntimeError(f'CodeDeploy {deployment_id}: {info["status"]}')
        time.sleep(10)
    raise TimeoutError(f"CodeDeploy {deployment_id} exceeded 15 minutes")


def smoke(url, commit):
    fetch(url + "/health/ready")
    if json.loads(fetch(url + "/version"))["commit"] != commit:
        raise ValueError("Public API serves a different commit")


def main():
    directory = Path(sys.argv[1])
    release = json.loads((directory / "release.json").read_text())
    environment = required("DEPLOY_ENVIRONMENT")
    bucket = required("ARTIFACT_BUCKET")
    application = required("CODEDEPLOY_APPLICATION")
    group = required("CODEDEPLOY_GROUP")
    url = public_url()
    evidence = {"application": "backend", "environment": environment, "release": release}
    record(evidence, status="preflight")
    previous = None
    previous_commit = None
    deployment_id = None
    try:
        settings = aws("deploy", "get-deployment-group", "--application-name", application,
                       "--deployment-group-name", group)["deploymentGroupInfo"]
        style = settings.get("deploymentStyle", {})
        alarms = settings.get("alarmConfiguration", {})
        rollback = settings.get("autoRollbackConfiguration", {})
        if style.get("deploymentType") != "IN_PLACE" or style.get("deploymentOption") != "WITH_TRAFFIC_CONTROL":
            raise ValueError("CodeDeploy group must use in-place deployment with ALB traffic control")
        if not settings.get("loadBalancerInfo", {}).get("targetGroupInfoList"):
            raise ValueError("Missing ALB target group")
        if settings.get("deploymentConfigName") != "CodeDeployDefault.OneAtATime":
            raise ValueError("Expected OneAtATime deployment configuration")
        events = set(rollback.get("events", []))
        if not rollback.get("enabled") or not {"DEPLOYMENT_FAILURE", "DEPLOYMENT_STOP_ON_ALARM"} <= events:
            raise ValueError("Required automatic rollback settings are absent")
        if not alarms.get("enabled") or not alarms.get("alarms") or alarms.get("ignorePollAlarmFailure", False):
            raise ValueError("Required fail-closed deployment alarms are absent")
        last = settings.get("lastSuccessfulDeployment", {}).get("deploymentId")
        if last:
            previous_info = aws("deploy", "get-deployment", "--deployment-id", last)["deploymentInfo"]
            previous = previous_info["revision"]
            if previous.get("revisionType") != "S3":
                raise ValueError("Previous revision must be a retained versioned S3 bundle")
            match = re.search(r"commit=([0-9a-f]{40})(?:\s|$)", previous_info.get("description", ""))
            previous_commit = match.group(1) if match else None
            if not previous.get("s3Location", {}).get("version"):
                raise ValueError("Previous S3 revision must reference an explicit object version")
        if environment.endswith("production") and not previous:
            raise ValueError("Bootstrap a known-good CodeDeploy revision before production promotion")
        record(evidence, previous_revision=previous, previous_deployment=last)
        if aws("s3api", "get-bucket-versioning", "--bucket", bucket).get("Status") != "Enabled":
            raise ValueError("Artifact bucket must have versioning enabled")
        key = f'backend/{environment}/{release["release_id"]}/bundle.tgz'
        upload = aws("s3api", "put-object", "--bucket", bucket, "--key", key,
                     "--body", directory / "bundle.tgz", "--server-side-encryption", "AES256", timeout=240)
        revision = {"revisionType": "S3", "s3Location": {
            "bucket": bucket, "key": key, "bundleType": "tgz",
            "version": upload["VersionId"], "eTag": upload["ETag"].strip('"'),
        }}
        created = aws("deploy", "create-deployment", "--application-name", application,
                      "--deployment-group-name", group, "--revision", json.dumps(revision),
                      "--description", f'release={release["release_id"]} commit={release["commit"]}')
        deployment_id = created["deploymentId"]
        record(evidence, status="deploying", deployment_id=deployment_id, revision=revision)
        wait(deployment_id)
        # Multiple requests improve sampling; ALB instance hooks are the per-host gate.
        for _ in range(3):
            retry(lambda: smoke(url, release["commit"]))
        record(evidence, status="succeeded")
    except BaseException as failure:
        record(evidence, status="failed", error=str(failure))
        if deployment_id:
            try:
                info = aws("deploy", "get-deployment", "--deployment-id", deployment_id)["deploymentInfo"]
                if info["status"] not in ("Succeeded", "Failed", "Stopped"):
                    aws("deploy", "stop-deployment", "--deployment-id", deployment_id, "--auto-rollback-enabled")
                    # Poll until terminal before creating another deployment.
                    try:
                        wait(deployment_id)
                    except RuntimeError:
                        pass
                    info = aws("deploy", "get-deployment", "--deployment-id", deployment_id)["deploymentInfo"]
                automatic = info.get("rollbackInfo", {}).get("rollbackDeploymentId")
                if info["status"] in ("Failed", "Stopped") and not automatic:
                    # Rollback metadata can lag the failed deployment status.
                    for _ in range(12):
                        time.sleep(5)
                        info = aws("deploy", "get-deployment", "--deployment-id", deployment_id)["deploymentInfo"]
                        automatic = info.get("rollbackInfo", {}).get("rollbackDeploymentId")
                        if automatic:
                            break
                if automatic:
                    record(evidence, rollback_id=automatic, recovery="automatic rollback running")
                    wait(automatic)
                    if previous_commit:
                        retry(lambda: smoke(url, previous_commit))
                    record(evidence, recovery="automatic rollback succeeded")
                elif previous:
                    # Recovery deployment bypasses the triggering alarm only. ALB
                    # readiness and all instance hooks still run; no bounce back
                    # to the failed revision if recovery itself fails.
                    recovered = aws("deploy", "create-deployment", "--application-name", application,
                                    "--deployment-group-name", group, "--revision", json.dumps(previous),
                                    "--description", f'recovery commit={previous_commit or "unknown"}',
                                    "--auto-rollback-configuration", '{"enabled":false}',
                                    "--override-alarm-configuration", '{"enabled":false}')
                    rollback_id = recovered["deploymentId"]
                    record(evidence, rollback_id=rollback_id, recovery="previous revision deploying")
                    wait(rollback_id)
                    if previous_commit:
                        retry(lambda: smoke(url, previous_commit))
                    record(evidence, recovery="previous revision restored")
                else:
                    record(evidence, recovery="no previous revision: operator action required")
            except BaseException as recovery_failure:
                record(evidence, recovery="unconfirmed: operator action required", recovery_error=str(recovery_failure))
        raise


if __name__ == "__main__":
    catch_termination()
    main()
