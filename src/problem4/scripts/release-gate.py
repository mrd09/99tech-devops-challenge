"""Fail closed before OIDC if this is stale or environment protection is absent."""
import json
import os
from urllib.request import Request, urlopen


def api(path):
    request = Request(f'https://api.github.com/repos/{os.environ["GITHUB_REPOSITORY"]}/{path}', headers={
        "Authorization": f'Bearer {os.environ["GH_TOKEN"]}',
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urlopen(request, timeout=20) as response:
        return json.load(response)


if os.environ["GITHUB_REF"] != "refs/heads/main" or os.environ["GITHUB_EVENT_NAME"] not in ("push", "workflow_dispatch"):
    raise ValueError("Only trusted main releases may deploy")
environment = os.environ["DEPLOY_ENVIRONMENT"]
if environment not in ("backend-staging", "backend-production", "frontend-staging", "frontend-production"):
    raise ValueError("Unexpected deployment environment")
if api("git/ref/heads/main")["object"]["sha"] != os.environ["GITHUB_SHA"]:
    raise ValueError("This release is stale: main has advanced; release the latest successful run")
settings = api(f"environments/{environment}")
if not (settings.get("deployment_branch_policy") or {}).get("custom_branch_policies"):
    raise ValueError("Environment must select main as its only deployment branch")
policies = api(f"environments/{environment}/deployment-branch-policies")["branch_policies"]
if len(policies) != 1 or policies[0]["name"] != "main" or policies[0].get("type", "branch") != "branch":
    raise ValueError("Environment must allow exactly the main branch, with no tag policy")
if environment.endswith("production"):
    reviewers = [rule for rule in settings.get("protection_rules", []) if rule["type"] == "required_reviewers"]
    if not reviewers or not reviewers[0].get("reviewers") or not reviewers[0].get("prevent_self_review"):
        raise ValueError("Production requires reviewers and prevention of self approval")
print(f"Release gate accepted {environment}")
