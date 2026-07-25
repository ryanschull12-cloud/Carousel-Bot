"""
Design/copy feedback loop — the automated experiment engine.

This is the FULL-AUTONOMY counterpart to self_improve.py. self_improve.py
only ever emails suggestions for a human to copy in by hand. This script
actually runs the loop end to end and applies the winner itself, no human
approval step:

  1. If an experiment is currently active (experiments.json), check whether
     it has enough real Instagram data yet (per arm) to call a winner. If it
     does, PROMOTE it (commit the copy rule / design constant change live)
     or REJECT it (just close it out), and email Ryan what happened either
     way.
  2. If there's no active experiment (either there never was one, or the
     step above just closed one out), research and start exactly ONE new
     one — combining real internal performance data (performance_history.json)
     with external web research (Tavily) on what's currently working for
     other accounts, fed to Claude to propose a single testable tweak.

SCOPE, ENFORCED IN CODE, NOT JUST IN THE PROMPT:
  - copy_rule experiments may only touch content_brain_system_prompt.txt or
    critic_system_prompt.txt, and may only affect body_slides/recap_slide/
    cta_slide/cta_word/cta_promise/caption — hook_slide and bridge_slide are
    decided earlier in the pipeline (the virality-checker concept stage) and
    are off-limits to an experiment.
  - design_constant experiments may only touch a constant listed in
    carousel_engine.EXPERIMENTABLE_CONSTANTS, and only within that constant's
    own min/max bounds. Nothing about rendering/layout logic is ever
    touched — see that dict for the exact allowlist.
  - Only one experiment runs at a time, so a result is never confounded by
    a second simultaneous change.

HOW A CAROUSEL GETS INTO AN EXPERIMENT: runner.py reads whatever is in
experiments.json's "active" slot and tags exactly one of that day's
carousels with it (see pick_experiment_target_hook / the render loop in
runner.py). fetch_performance.py carries the tag through onto
performance_history.json once the post is old enough to score. This script
is the only thing that ever WRITES experiments.json's active/history and
the only thing that ever commits a promoted prompt/constant change.

Runs weekly — see .github/workflows/design_experiment_loop.yml. Safe to
re-run any time (workflow_dispatch): if the active experiment doesn't have
enough data yet, it just logs that and exits without emailing.
"""

import os
import re
import json
import datetime
import smtplib
import requests
from email.message import EmailMessage

import carousel_engine

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL = os.environ.get("TO_EMAIL", GMAIL_ADDRESS)
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"
TAVILY_URL = "https://api.tavily.com/search"

EXPERIMENTS_PATH = "experiments.json"
PERFORMANCE_PATH = "performance_history.json"
CONTENT_BRAIN_PATH = "content_brain_system_prompt.txt"
CRITIC_PATH = "critic_system_prompt.txt"
CAROUSEL_ENGINE_PATH = "carousel_engine.py"

COPY_RULE_ALLOWED_FILES = {CONTENT_BRAIN_PATH, CRITIC_PATH}
# Guards against a proposal trying to sneak past the "hook/bridge and
# rendering logic are off-limits" rule even if it ignored the instruction.
COPY_RULE_BANNED_SUBSTRINGS = (
    "hook_slide", "bridge_slide", "carousel_engine", ".py", "render",
    "layout", "font", "pixel", "px ", "color", "colour",
)

MIN_SCORED_PER_ARM = 6      # per arm, not total -- same bar self_improve.py
                             # uses for "enough signal to trust a pattern"
MIN_RELATIVE_LIFT = 0.10    # variant must beat control by >=10% to promote,
                             # or trail by >=10% to reject outright as a loss
MAX_DAYS_ACTIVE = 21        # force-resolve a stuck/inconclusive experiment
                             # after 3 weeks rather than let it run forever


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Could not read {path}, using default ({e})")
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


# ============================================================
# STEP 1: evaluate whatever experiment is currently active
# ============================================================

def arm_stats(performance, experiment_id):
    """Return (control_rates, variant_rates) -- lists of engagement_rate
    floats for scored posts tagged with this experiment id."""
    control, variant = [], []
    for p in performance.get("scored_posts", []):
        if p.get("experiment_id") != experiment_id:
            continue
        if p.get("experiment_arm") == "variant":
            variant.append(p["engagement_rate"])
        elif p.get("experiment_arm") == "control":
            control.append(p["engagement_rate"])
    return control, variant


def days_active(experiment):
    try:
        started = datetime.date.fromisoformat(experiment["started"])
    except Exception:
        return 0
    return (datetime.date.today() - started).days


def evaluate_active_experiment(experiment, performance):
    """
    Returns None if the experiment should keep running as-is. Otherwise
    returns a dict of fields to merge onto the experiment before it moves
    to history: status ("promoted"/"rejected"), note, control_avg,
    variant_avg, n_control, n_variant.
    """
    control, variant = arm_stats(performance, experiment["id"])
    n_control, n_variant = len(control), len(variant)
    age = days_active(experiment)

    have_enough = n_control >= MIN_SCORED_PER_ARM and n_variant >= MIN_SCORED_PER_ARM
    timed_out = age >= MAX_DAYS_ACTIVE

    if not have_enough and not timed_out:
        print(f"Experiment {experiment['id']}: {n_variant} variant / {n_control} control "
              f"scored post(s) so far (need {MIN_SCORED_PER_ARM} each), {age} day(s) old — "
              "still collecting data.")
        return None

    if not have_enough and timed_out:
        return {
            "status": "rejected",
            "note": f"Timed out after {age} days without reaching {MIN_SCORED_PER_ARM} scored "
                    f"posts per arm (had {n_variant} variant / {n_control} control) — closing as "
                    "inconclusive rather than leaving it stuck.",
            "control_avg": round(sum(control) / len(control), 3) if control else None,
            "variant_avg": round(sum(variant) / len(variant), 3) if variant else None,
            "n_control": n_control,
            "n_variant": n_variant,
        }

    control_avg = sum(control) / len(control)
    variant_avg = sum(variant) / len(variant)
    lift = (variant_avg - control_avg) / control_avg if control_avg else 0.0

    if lift >= MIN_RELATIVE_LIFT:
        status = "promoted"
        note = (f"Variant beat control by {lift * 100:.1f}% (variant avg {variant_avg:.2f} vs "
                f"control avg {control_avg:.2f}, n={n_variant}/{n_control}) — auto-promoted.")
    elif lift <= -MIN_RELATIVE_LIFT:
        status = "rejected"
        note = (f"Variant trailed control by {abs(lift) * 100:.1f}% (variant avg {variant_avg:.2f} "
                f"vs control avg {control_avg:.2f}, n={n_variant}/{n_control}) — rejected.")
    else:
        status = "rejected"
        note = (f"No clear winner after {n_variant}/{n_control} scored posts (variant avg "
                f"{variant_avg:.2f} vs control avg {control_avg:.2f}, {lift * 100:+.1f}%) — "
                f"under the {MIN_RELATIVE_LIFT * 100:.0f}% bar either way, rejected as inconclusive.")

    return {
        "status": status,
        "note": note,
        "control_avg": round(control_avg, 3),
        "variant_avg": round(variant_avg, 3),
        "n_control": n_control,
        "n_variant": n_variant,
    }


def apply_promotion(experiment):
    """Commits the winning change to the actual live file. Returns the
    path of the file that changed, or None if the apply failed (in which
    case the experiment is still marked rejected upstream -- a change that
    can't be safely applied should never silently vanish as a "win")."""
    if experiment["type"] == "copy_rule":
        return apply_copy_rule_promotion(experiment)
    if experiment["type"] == "design_constant":
        return apply_design_constant_promotion(experiment)
    print(f"Unknown experiment type {experiment['type']!r} -- cannot apply, treating as not applied.")
    return None


def apply_copy_rule_promotion(experiment):
    cr = experiment.get("copy_rule", {})
    target_file = cr.get("target_file")
    instruction = cr.get("instruction", "").strip()
    if target_file not in COPY_RULE_ALLOWED_FILES or not instruction:
        print(f"copy_rule promotion for {experiment['id']} has an invalid target/instruction -- not applying.")
        return None

    current = load_text(target_file)
    marker = "# --- AUTOMATED EXPERIMENT RULES (auto-promoted by experiment_loop.py, see experiments.json history for evidence) ---"
    if marker not in current:
        current = current.rstrip("\n") + "\n\n" + marker + "\n"
    today = datetime.date.today().isoformat()
    current = current.rstrip("\n") + f"\n- [{today}, {experiment['id']}] {instruction}\n"
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(current)
    print(f"Promoted copy_rule {experiment['id']} into {target_file}.")
    return target_file


def apply_design_constant_promotion(experiment):
    dc = experiment.get("design_constant", {})
    const_name = dc.get("constant")
    variant_value = dc.get("variant_value")
    bounds = carousel_engine.EXPERIMENTABLE_CONSTANTS.get(const_name)
    if not const_name or not bounds or variant_value is None or not (bounds["min"] <= variant_value <= bounds["max"]):
        print(f"design_constant promotion for {experiment['id']} names an unsafe/unknown constant -- not applying.")
        return None

    source = load_text(CAROUSEL_ENGINE_PATH)
    pattern = re.compile(rf"^({re.escape(const_name)}\s*=\s*)\d+(.*)$", re.MULTILINE)
    new_source, count = pattern.subn(lambda m: f"{m.group(1)}{int(variant_value)}{m.group(2)}", source, count=1)
    if count != 1:
        print(f"Could not find a single {const_name} assignment line in {CAROUSEL_ENGINE_PATH} -- not applying.")
        return None
    with open(CAROUSEL_ENGINE_PATH, "w", encoding="utf-8") as f:
        f.write(new_source)
    print(f"Promoted design_constant {experiment['id']}: {const_name} -> {variant_value}.")
    return CAROUSEL_ENGINE_PATH


# ============================================================
# STEP 2: research + propose a new experiment
# ============================================================

def avg_by(posts, key):
    buckets = {}
    for p in posts:
        k = p.get(key) or "unknown"
        buckets.setdefault(k, []).append(p["engagement_rate"])
    ranked = [(k, sum(v) / len(v), len(v)) for k, v in buckets.items()]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def build_internal_summary(performance):
    posts = performance.get("scored_posts", [])
    if not posts:
        return "No scored Instagram posts yet -- no internal performance signal available."
    lines = [f"{len(posts)} scored post(s) on file:"]
    for label, key in (("Niche", "niche"), ("Angle", "angle"), ("Format", "format")):
        ranked = avg_by(posts, key)
        if len(ranked) < 2:
            continue
        lines.append(f"{label}: " + "; ".join(f"{k} avg {avg:.2f} (n={n})" for k, avg, n in ranked))
    ranked_posts = sorted(posts, key=lambda p: p["engagement_rate"], reverse=True)
    lines.append("Top hooks: " + " | ".join(f"\"{p.get('hook', '')}\" [{p['engagement_rate']:.2f}]" for p in ranked_posts[:3]))
    lines.append("Bottom hooks: " + " | ".join(f"\"{p.get('hook', '')}\" [{p['engagement_rate']:.2f}]" for p in ranked_posts[-3:]))
    return "\n".join(lines)


def call_tavily(query):
    if not TAVILY_API_KEY:
        return None
    try:
        resp = requests.post(
            TAVILY_URL,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {TAVILY_API_KEY}"},
            json={
                "query": query, "topic": "general", "search_depth": "basic",
                "time_range": "month", "max_results": 4, "include_answer": True,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Tavily research skipped for {query!r} (non-fatal): {e}")
        return None
    bits = []
    if data.get("answer"):
        bits.append(data["answer"])
    for r in data.get("results", [])[:4]:
        title = r.get("title")
        if title:
            bits.append(title)
    return " | ".join(bits)[:1000] if bits else None


def build_external_summary():
    queries = [
        "Instagram carousel post design trends that increase engagement",
        "high performing Instagram caption and hook copywriting techniques",
    ]
    findings = [f for f in (call_tavily(q) for q in queries) if f]
    if not findings:
        return None
    return "\n".join(findings)


def already_tried_summary(experiments):
    history = experiments.get("history", [])
    if not history:
        return "None yet."
    lines = []
    for e in history[-15:]:
        lines.append(f"- [{e.get('status')}] ({e.get('type')}) {e.get('hypothesis', '')}")
    return "\n".join(lines)


PROPOSAL_SYSTEM_PROMPT = """You are proposing exactly ONE new experiment for an automated \
design/copy feedback loop running a small Irish marketing agency's Instagram carousel bot. You \
are given real internal engagement data, a short external web-research briefing on current \
Instagram carousel trends, the current value of every design constant you're allowed to touch, \
and a list of experiments already tried. Propose the single small, testable tweak most likely to \
lift engagement next.

Hard rules:
1. Output ONLY valid JSON, no markdown fences, no commentary, matching the schema given below.
2. Exactly one experiment. type is either "copy_rule" or "design_constant" -- nothing else.
3. copy_rule experiments may only affect body_slides, recap_slide, cta_slide, cta_word, \
cta_promise, or caption -- hook_slide and bridge_slide are decided earlier in the pipeline and \
are completely off-limits, do not reference them. target_file must be exactly \
"content_brain_system_prompt.txt" or "critic_system_prompt.txt".
4. design_constant experiments may only pick a constant from the allowlist you're given, and \
variant_value must fall within that constant's own min/max bounds shown to you. Never propose a \
constant not in the list, never propose a value outside its bounds.
5. Never propose anything touching carousel_engine.py's rendering/layout logic, a new slide type, \
new colors, or any structural change -- constants only, from the list given.
6. Do not repeat or closely rephrase anything in the "already tried" list.
7. copy_rule instructions must be ONE clear, testable behavior change, under 200 characters, \
phrased as a direct instruction (e.g. "End every CTA promise line with a concrete number, never \
a vague noun.").
8. research_note must cite the specific internal data point or external finding that motivated \
this, under 280 characters.

JSON schema:
{"type": "copy_rule" | "design_constant", "hypothesis": "short string", "source": "internal" | \
"external" | "internal+external", "research_note": "string", "copy_rule": {"target_file": \
"...", "instruction": "..."}, "design_constant": {"constant": "...", "variant_value": number}}
Include ONLY the "copy_rule" key if type is copy_rule, or ONLY the "design_constant" key if type \
is design_constant -- never both."""


def call_claude_propose(internal_summary, external_summary, tried_summary):
    constants_block = "\n".join(
        f"{name}: current={getattr(carousel_engine, name)}, min={bounds['min']}, max={bounds['max']}"
        for name, bounds in carousel_engine.EXPERIMENTABLE_CONSTANTS.items()
    )
    user_content = (
        f"INTERNAL PERFORMANCE DATA:\n{internal_summary}\n\n"
        f"EXTERNAL RESEARCH BRIEFING:\n{external_summary or '(no external research available this run)'}\n\n"
        f"DESIGN CONSTANTS YOU MAY PROPOSE CHANGING:\n{constants_block}\n\n"
        f"EXPERIMENTS ALREADY TRIED (do not repeat):\n{tried_summary}\n"
    )
    resp = requests.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": 700,
            "system": PROPOSAL_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_content}],
        },
        timeout=120,
    )
    if not resp.ok:
        raise RuntimeError(f"Anthropic API call failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    text = "".join(block.get("text", "") for block in data.get("content", []))
    return json.loads(text)


def validate_and_normalize_proposal(proposal, next_id):
    """Returns a fully-formed experiment dict, or None if the proposal
    fails any safety check -- in which case it is simply discarded, not
    force-corrected, so a borderline/misread proposal never quietly slips
    past the scope rules."""
    exp_type = proposal.get("type")
    if exp_type not in ("copy_rule", "design_constant"):
        print(f"Proposal rejected: invalid type {exp_type!r}.")
        return None

    hypothesis = str(proposal.get("hypothesis", "")).strip()[:300]
    research_note = str(proposal.get("research_note", "")).strip()[:300]
    source = proposal.get("source") if proposal.get("source") in ("internal", "external", "internal+external") else "internal"
    if not hypothesis:
        print("Proposal rejected: missing hypothesis.")
        return None

    experiment = {
        "id": next_id,
        "created": datetime.date.today().isoformat(),
        "started": datetime.date.today().isoformat(),
        "type": exp_type,
        "hypothesis": hypothesis,
        "source": source,
        "research_note": research_note,
    }

    if exp_type == "copy_rule":
        cr = proposal.get("copy_rule") or {}
        target_file = cr.get("target_file")
        instruction = str(cr.get("instruction", "")).strip()
        if target_file not in COPY_RULE_ALLOWED_FILES:
            print(f"Proposal rejected: copy_rule target_file {target_file!r} not allowed.")
            return None
        if not instruction or len(instruction) > 220:
            print("Proposal rejected: copy_rule instruction missing or too long.")
            return None
        lowered = instruction.lower()
        if any(bad in lowered for bad in COPY_RULE_BANNED_SUBSTRINGS):
            print(f"Proposal rejected: copy_rule instruction touches an off-limits area: {instruction!r}")
            return None
        experiment["copy_rule"] = {"target_file": target_file, "instruction": instruction}
        return experiment

    # design_constant
    dc = proposal.get("design_constant") or {}
    const_name = dc.get("constant")
    variant_value = dc.get("variant_value")
    bounds = carousel_engine.EXPERIMENTABLE_CONSTANTS.get(const_name)
    if not bounds:
        print(f"Proposal rejected: design_constant {const_name!r} is not in the allowlist.")
        return None
    try:
        variant_value = int(variant_value)
    except (TypeError, ValueError):
        print(f"Proposal rejected: design_constant variant_value {variant_value!r} is not a number.")
        return None
    current_value = getattr(carousel_engine, const_name)
    if not (bounds["min"] <= variant_value <= bounds["max"]):
        print(f"Proposal rejected: {const_name}={variant_value} is outside bounds {bounds}.")
        return None
    if abs(variant_value - current_value) < 2:
        print(f"Proposal rejected: {const_name}={variant_value} is barely different from current {current_value}.")
        return None
    experiment["design_constant"] = {
        "constant": const_name,
        "control_value": current_value,
        "variant_value": variant_value,
    }
    return experiment


def research_new_experiment(experiments, performance):
    internal_summary = build_internal_summary(performance)
    external_summary = build_external_summary()
    tried_summary = already_tried_summary(experiments)

    try:
        proposal = call_claude_propose(internal_summary, external_summary, tried_summary)
    except Exception as e:
        print(f"Proposal call failed, no new experiment this cycle ({e})")
        return None

    next_id = f"exp-{datetime.date.today().strftime('%Y%m%d')}-{len(experiments.get('history', [])) + 1}"
    return validate_and_normalize_proposal(proposal, next_id)


# ============================================================
# Email + main
# ============================================================

def send_email(subject, body):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def describe_experiment(e):
    if e["type"] == "copy_rule":
        cr = e["copy_rule"]
        return f'copy_rule -> {cr["target_file"]}: "{cr["instruction"]}"'
    dc = e["design_constant"]
    return f'design_constant -> {dc["constant"]}: {dc.get("control_value", "?")} -> {dc["variant_value"]}'


def main():
    experiments = load_json(EXPERIMENTS_PATH, {"active": None, "history": []})
    performance = load_json(PERFORMANCE_PATH, {"scored_posts": []})

    email_parts = []
    experiments_dirty = False

    active = experiments.get("active")
    if active:
        resolution = evaluate_active_experiment(active, performance)
        if resolution is not None:
            applied_file = None
            if resolution["status"] == "promoted":
                applied_file = apply_promotion(active)
                if applied_file is None:
                    # Couldn't safely apply -- don't claim a win that never
                    # actually shipped.
                    resolution["status"] = "rejected"
                    resolution["note"] += " (Could not be safely applied to the live file, so closed as rejected instead of promoted.)"
            active.update(resolution)
            active["resolved_date"] = datetime.date.today().isoformat()
            experiments["history"].append(active)
            experiments["active"] = None
            experiments_dirty = True
            email_parts.append(
                f"EXPERIMENT {'PROMOTED' if resolution['status'] == 'promoted' else 'REJECTED'}: {active['id']}\n"
                f"Hypothesis: {active['hypothesis']}\n"
                f"Change: {describe_experiment(active)}\n"
                f"Result: {active['note']}\n"
            )

    if not experiments.get("active"):
        new_exp = research_new_experiment(experiments, performance)
        if new_exp:
            experiments["active"] = new_exp
            experiments_dirty = True
            email_parts.append(
                f"NEW EXPERIMENT STARTED: {new_exp['id']}\n"
                f"Hypothesis: {new_exp['hypothesis']}\n"
                f"Change: {describe_experiment(new_exp)}\n"
                f"Source: {new_exp['source']}\n"
                f"Why: {new_exp['research_note']}\n"
                f"It'll run on one carousel a day until it collects {MIN_SCORED_PER_ARM} scored "
                "posts per arm (roughly a few weeks), then auto-resolve next time this runs."
            )
        else:
            print("No new experiment proposed this cycle -- will try again next run.")

    if experiments_dirty:
        save_json(EXPERIMENTS_PATH, experiments)

    if email_parts:
        subject = f"Carousel Bot design/copy experiment update — {datetime.date.today().isoformat()}"
        body = (
            "This is the fully-automated design/copy feedback loop -- changes below were applied "
            "live already, nothing is waiting on your approval.\n\n" + "\n\n".join(email_parts)
        )
        send_email(subject, body)
        print("Sent experiment update email.")
    else:
        print("Nothing to report this run (experiment still collecting data, or no valid new proposal).")


if __name__ == "__main__":
    main()
