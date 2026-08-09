#!/usr/bin/env python3
"""Fail if a workflow step runs a script that reads env vars the step cannot see.

WHY THIS EXISTS
---------------
On 2026-08-09 the rendered reel MP4 had never once been emailed. instagram_reel_post.py
reads GMAIL_ADDRESS and GMAIL_APP_PASSWORD, email() returns when they are absent, and the
"Render reel" step -- the step that sends the attachment -- was the only step in all three
reel workflows with no env block. No error, no warning, green workflow, every single run.
It surfaced only because Ryan went looking for a file and could not find one.

The same sweep then found that tiktok-batch-post.yml had no reference to
TIKTOK_POSTING_PAUSED anywhere: pausing TikTok stopped the three scheduled workflows and
left the batch one able to post.

Both are the same fault -- a script quietly depending on configuration the workflow never
supplies -- and both are mechanically detectable, which is why this is a script and not a
note in a handoff. Run it in CI on any workflow or Python change.

WHAT IT CANNOT SEE
------------------
It matches os.environ reads statically and follows local imports one level. It will not
catch a name built at runtime, and it does not know whether a missing var is fatal or
merely degrades something. That is the point: it reports the gap and a human decides. A
var that is genuinely optional goes in OPTIONAL below WITH A REASON, so the next person
knows it was considered rather than overlooked.
"""
import os, re, sys, glob
import yaml

# Provided by GitHub to every step, or genuinely optional with a safe default.
# Each entry needs a reason.
OPTIONAL = {
    "GITHUB_REPOSITORY": "GitHub default env var, present in every step",
    "GITHUB_EVENT_NAME": "GitHub default env var, present in every step",
    "GITHUB_SHA": "GitHub default env var",
    "GITHUB_REF": "GitHub default env var",
    "GITHUB_RUN_ID": "GitHub default env var",
    "GITHUB_ACTOR": "GitHub default env var",
    "RUNNER_OS": "GitHub default env var",
    "CI": "GitHub default env var",
    "HOME": "shell default",
    "PATH": "shell default",
    "TZ": "only set locally when testing timezone gates",
    "INTER_FONT_DIR": "local-testing override; CI installs fonts-inter via apt",
    "IG_ACCESS_TOKEN": "read at module scope but only used on the publish path; "
                       "render-only steps do not need it",
    "IG_BUSINESS_ACCOUNT_ID": "same as IG_ACCESS_TOKEN -- publish path only",
}


def env_reads(pyfile, seen=None):
    if seen is None:
        seen = set()
    if pyfile in seen or not os.path.exists(pyfile):
        return set()
    seen.add(pyfile)
    src = open(pyfile, encoding="utf-8").read()
    names = set(re.findall(r'os\.environ\.get\(\s*["\']([A-Z_0-9]+)["\']', src))
    names |= set(re.findall(r'os\.environ\[\s*["\']([A-Z_0-9]+)["\']', src))
    names |= set(re.findall(r'os\.getenv\(\s*["\']([A-Z_0-9]+)["\']', src))
    for a, b in re.findall(r'^\s*import\s+(\w+)|^\s*from\s+(\w+)\s+import', src, re.M):
        mod = a or b
        if mod and os.path.exists(mod + ".py"):
            names |= env_reads(mod + ".py", seen)
    return names


def main():
    problems = []
    for wf in sorted(glob.glob(".github/workflows/*.yml")):
        doc = yaml.safe_load(open(wf, encoding="utf-8"))
        wf_env = set((doc.get("env") or {}).keys())
        for job in (doc.get("jobs") or {}).values():
            job_env = set((job.get("env") or {}).keys())
            for step in job.get("steps") or []:
                run = step.get("run") or ""
                avail = wf_env | job_env | set((step.get("env") or {}).keys())
                for script in re.findall(r'python3?\s+([\w/]+\.py)', run):
                    missing = sorted(env_reads(script) - set(OPTIONAL) - avail)
                    if missing:
                        problems.append(
                            f"{os.path.basename(wf)} :: {step.get('name','?')} :: "
                            f"{script} cannot see {', '.join(missing)}")

    if problems:
        print("Workflow steps missing env vars their script reads:\n")
        for p in problems:
            print("  x " + p)
        print("\nEither add the var to that step's env, or add it to OPTIONAL in "
              "check_workflow_env.py WITH A REASON.")
        return 1
    print("Every workflow step can see the env vars its script reads.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
