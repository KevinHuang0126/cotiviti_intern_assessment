"""Gradio demo UI — Compile, Self-verify, Version diff tabs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import gradio as gr

from src.diff import diff_report, format_diff_highlights
from src.engine import RuleEngine
from src.fixtures_loader import load_rule, load_test_suite
from src.llm import get_client
from src.loop import run_compile_loop_streaming

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

FOOTER_CSS = "footer {display: none !important;}"


def load_policy(version: str) -> tuple[str, str, str]:
    if version == "v1":
        path = DATA / "coverage_section_v1.md"
        return (
            "NCD-210.14-COVERAGE-V1",
            "CAG-00439N",
            path.read_text(encoding="utf-8"),
        )
    path = DATA / "coverage_section_v2.md"
    return (
        "NCD-210.14-COVERAGE-V2",
        "CAG-00439R",
        path.read_text(encoding="utf-8"),
    )


def run_compile(self_verify: bool, seed_defect: bool, demo_mode: str):
    client = get_client(demo_mode if demo_mode != "replay" else "fixture")
    version = "v1" if seed_defect else "v2"
    section_id, policy_version, policy_text = load_policy(version)

    if not self_verify:
        from src.compiler import compile_rule

        rule = compile_rule(
            client, section_id, policy_version, policy_text, validate_cites=False
        )
        yield (
            policy_text,
            json.dumps(rule, indent=2),
            "Single-shot compile complete.",
            rule,
            None,
        )
        return

    transcript_md = ""
    final_rule = None
    for event_type, payload in run_compile_loop_streaming(
        client, section_id, policy_version, policy_text, seed_defect=seed_defect
    ):
        if event_type == "status":
            transcript_md += f"\n**{payload}**\n"
            yield policy_text, "", transcript_md, None, None
        elif event_type == "round":
            transcript_md += (
                f"\n### Round {payload['round']}\n"
                f"- Failures: {payload['failure_count']}\n"
                f"- Rule hash: `{payload['rule_hash']}`\n"
            )
            if payload.get("changelog"):
                for c in payload["changelog"]:
                    transcript_md += f"  - Fix: {c.get('change', '')}\n"
            yield policy_text, "", transcript_md, None, None
        elif event_type == "done":
            final_rule = payload["rule"]
            banner = (
                f"✅ Rule converged in {len(payload['transcripts'])} rounds"
                if payload["converged"]
                else f"⚠️ Stopped: {payload['stopped_reason']}"
            )
            transcript_md += f"\n**{banner}**\n"
            yield (
                policy_text,
                json.dumps(final_rule, indent=2),
                transcript_md,
                final_rule,
                payload,
            )


def run_version_diff(demo_mode: str):
    client = get_client(demo_mode if demo_mode != "replay" else "fixture")
    engine = RuleEngine()

    rule_v1 = load_rule("v1")
    rule_v2 = load_rule("v2")
    suite_v1 = load_test_suite("v1")
    suite_v2 = load_test_suite("v2")

    report = diff_report(rule_v1, rule_v2, suite_v1, suite_v2)
    highlights = format_diff_highlights(report["structural_changes"])

    diff_md = "## Structural changes\n\n"
    for c in report["structural_changes"]:
        if c["change_type"] == "Modified":
            diff_md += f"- **Modified** ({c['leaf_type']}): {c['summary']}\n"
        else:
            diff_md += f"- **{c['change_type']}** ({c.get('leaf_type', '')}): {c.get('summary', '')}\n"

    diff_md += f"\n**{report['modified_count']} modified leaves**\n\n"
    diff_md += "## Flipped claims\n\n"
    for f in report["flipped_claims"]:
        diff_md += (
            f"- `{f['id']}`: v1 **{f['decision_v1'].upper()}** → "
            f"v2 **{f['decision_v2'].upper()}**\n"
        )

    headline = report.get("headline_claim")
    headline_text = ""
    if headline:
        m = headline["claim"]["member"]
        headline_text = (
            f"Headline: {m.get('age_years')}yo, {m.get('pack_years')} pack-years → "
            f"v1 {headline['decision_v1'].upper()} / v2 {headline['decision_v2'].upper()}"
        )

    return (
        json.dumps(rule_v1, indent=2),
        json.dumps(rule_v2, indent=2),
        highlights,
        diff_md,
        headline_text,
        report["flipped_claims"],
    )


def evaluate_claim(age, pack_years, px_code, demo_mode: str):
    engine = RuleEngine()
    rule_v1 = load_rule("v1")
    rule_v2 = load_rule("v2")

    claim = {
        "member": {
            "age_years": float(age),
            "pack_years": float(pack_years),
            "smoker_status": "former",
            "years_since_quit": 8,
            "asymptomatic": True,
        },
        "px_codes": [px_code],
        "sdm_visit_completed": True,
        "written_order": True,
        "documentation": {},
    }

    d1 = engine.run_rule_on_claim(rule_v1, claim)
    d2 = engine.run_rule_on_claim(rule_v2, claim)

    return (
        f"**[SYNTHETIC]** {int(age)}yo, {pack_years} pack-years, code {px_code}\n\n"
        f"| Version | Decision |\n|---------|----------|\n"
        f"| v1 (2015) | **{d1.upper()}** |\n"
        f"| v2 (2022) | **{d2.upper()}** |"
    )


def build_app(demo_mode: str = "fixture") -> gr.Blocks:
    with gr.Blocks(
        theme=gr.themes.Soft(primary_hue="emerald"),
        css=FOOTER_CSS,
        title="policy-as-rule POC",
    ) as demo:
        gr.Markdown(
            "# Self-Critiquing LLM Compiler for Healthcare Coverage Policies\n"
            "**Demo policy:** NCD 210.14 — Lung Cancer Screening with LDCT"
        )

        with gr.Tab("Compile"):
            # Stacked (not in a Row): an empty gr.Code inside a flex Row
            # collapses to zero width and never renders. Full width also
            # makes the JSON readable on video.
            policy_out = gr.Textbox(label="Policy text", lines=10)
            rule_out = gr.Code(
                label="Compiled rule (JSON)",
                language="json",
                value="// Click Run to compile the policy into a rule.",
                lines=18,
            )
            self_verify = gr.Checkbox(label="Self-verify (compile + critique loop)", value=True)
            seed_defect = gr.Checkbox(
                label="Seed defect (wrong age threshold for demo)", value=False
            )
            compile_btn = gr.Button("Run", variant="primary")
            compile_status = gr.Markdown()

        with gr.Tab("Self-verify loop"):
            loop_transcript = gr.Markdown(label="Loop transcript")

        with gr.Tab("Version diff"):
            with gr.Row():
                rule_v1_view = gr.Code(
                    label="Rule v1 (2015)",
                    language="json",
                    value="// Click 'Load version diff' below.",
                )
                rule_v2_view = gr.Code(
                    label="Rule v2 (2022)",
                    language="json",
                    value="// Click 'Load version diff' below.",
                )
            diff_highlights = gr.HighlightedText(
                label="Structural diff",
                color_map={"+": "#16a34a", "-": "#dc2626"},
                show_legend=True,
            )
            diff_summary = gr.Markdown()
            headline_box = gr.Markdown()
            with gr.Row():
                age_input = gr.Number(label="Age (years)", value=52)
                pack_input = gr.Number(label="Pack-years", value=22)
                code_input = gr.Textbox(label="Procedure code", value="71271")
            eval_btn = gr.Button("Evaluate claim flip")
            eval_out = gr.Markdown()
            diff_btn = gr.Button("Load version diff", variant="primary")

        def _run_compile(sv, sd):
            # Must be a generator function (not a lambda returning a generator)
            # so Gradio streams the yielded stages into the output components.
            yield from run_compile(sv, sd, demo_mode)

        compile_btn.click(
            fn=_run_compile,
            inputs=[self_verify, seed_defect],
            outputs=[policy_out, rule_out, compile_status, gr.State(), gr.State()],
        ).then(
            fn=lambda _, __, transcript, ___, ____ : transcript,
            inputs=[policy_out, rule_out, compile_status, gr.State(), gr.State()],
            outputs=[loop_transcript],
        )

        diff_btn.click(
            fn=lambda: run_version_diff(demo_mode),
            outputs=[rule_v1_view, rule_v2_view, diff_highlights, diff_summary, headline_box, gr.State()],
        )

        eval_btn.click(
            fn=lambda a, p, c: evaluate_claim(a, p, c, demo_mode),
            inputs=[age_input, pack_input, code_input],
            outputs=[eval_out],
        )

        demo.queue(default_concurrency_limit=1)

    return demo


def main() -> None:
    parser = argparse.ArgumentParser(description="policy-as-rule Gradio demo")
    parser.add_argument(
        "--demo-mode",
        choices=["live", "replay", "fixture"],
        default="fixture",
        help="live=API, replay=cache, fixture=offline fixtures",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()

    app = build_app(demo_mode=args.demo_mode)
    app.launch(server_name=args.host, server_port=args.port)


if __name__ == "__main__":
    main()
