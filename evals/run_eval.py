#!/usr/bin/env python3
"""
evals/run_eval.py
=================
CLI entry point for running the evaluation suite.

Usage:
    python evals/run_eval.py                    # Run all tests, save JSON + HTML
    python evals/run_eval.py --quick            # Run first 5 tests only
    python evals/run_eval.py --session my-eval  # Custom session ID
    python evals/run_eval.py --model llama-3.1 # Custom model
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure the project root is in the path
import os
sys.path.insert(0, str(Path(__file__).parent.parent))

from evals.evaluator import run_evaluation, summary_to_dict


def generate_html_report(summary_dict: dict) -> str:
    """Generate an HTML report from the evaluation summary."""

    summary = summary_dict["summary"]
    by_category = summary_dict["by_category"]
    results = summary_dict["results"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AgenticSQL Evaluation Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1, h2, h3 {{ color: #333; }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
        }}
        .header h1 {{ margin: 0; }}
        .header p {{ margin: 10px 0 0 0; opacity: 0.9; }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .metric-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }}
        .metric-label {{
            color: #666;
            font-size: 0.9em;
            margin-top: 5px;
        }}
        .section {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        .pass {{ color: #28a745; }}
        .fail {{ color: #dc3545; }}
        .category-tag {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            background: #e9ecef;
            color: #495057;
        }}
        .category-safety {{ background: #f8d7da; color: #721c24; }}
        .category-aggregation {{ background: #d4edda; color: #155724; }}
        .category-join {{ background: #cce5ff; color: #004085; }}
        .category-cross_db {{ background: #fff3cd; color: #856404; }}
        .category-filter {{ background: #e2e3e5; color: #383d41; }}
        .category-general_chat {{ background: #d1ecf1; color: #0c5460; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>AgenticSQL Evaluation Report</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <div class="metrics-grid">
        <div class="metric-card">
            <div class="metric-value">{summary['total']}</div>
            <div class="metric-label">Total Test Cases</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{summary['passed']}</div>
            <div class="metric-label">Passed</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{summary['pass_rate']:.1%}</div>
            <div class="metric-label">Pass Rate</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{summary['intent_accuracy']:.1%}</div>
            <div class="metric-label">Intent Accuracy</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{summary['valid_sql_rate']:.1%}</div>
            <div class="metric-label">Valid SQL Rate</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{summary['avg_latency_seconds']:.2f}s</div>
            <div class="metric-label">Avg Latency</div>
        </div>
    </div>

    <div class="section">
        <h2>Results by Category</h2>
        <table>
            <thead>
                <tr>
                    <th>Category</th>
                    <th>Tests</th>
                    <th>Passed</th>
                    <th>Intent Accuracy</th>
                    <th>Valid SQL</th>
                    <th>Avg Latency</th>
                </tr>
            </thead>
            <tbody>
"""

    for cat, cat_metrics in by_category.items():
        html += f"""                <tr>
                    <td><span class="category-tag category-{cat.split('_')[0]}">{cat}</span></td>
                    <td>{cat_metrics['total']}</td>
                    <td>{cat_metrics['passed']}</td>
                    <td>{cat_metrics['intent_accuracy']:.1%}</td>
                    <td>{cat_metrics['valid_sql_rate']:.1%}</td>
                    <td>{cat_metrics['avg_latency']:.2f}s</td>
                </tr>
"""

    html += """            </tbody>
        </table>
    </div>

    <div class="section">
        <h2>Individual Test Results</h2>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Category</th>
                    <th>Intent</th>
                    <th>Latency</th>
                    <th>Result</th>
                </tr>
            </thead>
            <tbody>
"""

    for r in results:
        status_class = "pass" if r["passed"] else "fail"
        status_text = "PASS" if r["passed"] else "FAIL"
        html += f"""                <tr>
                    <td>{r['test_id']}</td>
                    <td><span class="category-tag category-{r['category'].split('_')[0]}">{r['category']}</span></td>
                    <td>{r['intent_actual']} (exp: {r['intent_expected']})</td>
                    <td>{r['latency_seconds']:.2f}s</td>
                    <td class="{status_class}">{status_text}</td>
                </tr>
"""

    html += """            </tbody>
        </table>
    </div>
</body>
</html>
"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Run AgenticSQL evaluation suite")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only the first 5 test cases (for quick testing)",
    )
    parser.add_argument(
        "--session",
        default="eval-session",
        help="Session ID for this evaluation run",
    )
    parser.add_argument(
        "--model",
        default="llama-3.3-70b-versatile",
        help="Groq model to use",
    )
    parser.add_argument(
        "--output-dir",
        default="evals",
        help="Directory to save reports",
    )
    args = parser.parse_args()

    # Load test cases and optionally truncate
    from evals.evaluator import load_test_cases, run_evaluation

    test_cases = load_test_cases()
    if args.quick:
        test_cases = test_cases[:5]
        print(f"Quick mode: running {len(test_cases)} test cases")

    print(f"Starting evaluation with {len(test_cases)} test cases...")
    print(f"Session: {args.session}")
    print(f"Model: {args.model}")
    print("-" * 50)

    summary = run_evaluation(
        test_cases_path=None,
        session_id=args.session,
        model=args.model,
        _test_cases_override=test_cases,
    )

    summary_dict = summary_to_dict(summary)

    # Save JSON report
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"eval_report_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump(summary_dict, f, indent=2)
    print(f"\nJSON report saved to: {json_path}")

    # Save HTML report
    html_path = output_dir / f"eval_report_{timestamp}.html"
    with open(html_path, "w") as f:
        f.write(generate_html_report(summary_dict))
    print(f"HTML report saved to: {html_path}")

    # Print summary
    print("\n" + "=" * 50)
    print("EVALUATION SUMMARY")
    print("=" * 50)
    print(f"Total:         {summary_dict['summary']['total']}")
    print(f"Passed:        {summary_dict['summary']['passed']}")
    print(f"Pass Rate:     {summary_dict['summary']['pass_rate']:.1%}")
    print(f"Intent Acc:    {summary_dict['summary']['intent_accuracy']:.1%}")
    print(f"Valid SQL:     {summary_dict['summary']['valid_sql_rate']:.1%}")
    print(f"Avg Latency:  {summary_dict['summary']['avg_latency_seconds']:.2f}s")
    print("=" * 50)


if __name__ == "__main__":
    main()
