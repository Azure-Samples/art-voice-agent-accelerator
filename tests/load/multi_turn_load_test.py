#!/usr/bin/env python3
"""
Multi-Turn Conversation Load Testing
====================================

Enhanced load testing framework with configurable conversation turn depth
for realistic multi-turn conversation simulation.
"""

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from tests.load.utils.load_test_conversations import ConversationLoadTester, LoadTestConfig


class MultiTurnLoadTest:
    """Load testing with configurable conversation turn depth."""

    def __init__(self, base_url: str = "ws://localhost:8010/api/v1/media/stream"):
        self.base_url = base_url

    async def run_single_turn_test(self) -> dict:
        """Test with single-turn conversations only."""
        print("🔵 Running SINGLE-TURN test...")

        config = LoadTestConfig(
            max_concurrent_conversations=5,
            total_conversations=10,
            ramp_up_time_s=10.0,
            test_duration_s=120.0,
            conversation_templates=["quick_question"],
            ws_url=self.base_url,
            output_dir="tests/load/results",
            max_conversation_turns=1,
            min_conversation_turns=1,
            turn_variation_strategy="fixed",
        )

        tester = ConversationLoadTester(config)
        results = await tester.run_load_test()

        print("📊 SINGLE-TURN RESULTS:")
        tester.print_summary(results)

        filename = f"single_turn_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        results_file = tester.save_results(results, filename)

        return {
            "test_type": "single_turn",
            "config": config,
            "results": results,
            "results_file": results_file,
            "summary": results.get_summary(),
        }

    async def run_multi_turn_test(self, max_turns: int = 5) -> dict:
        """Test with multi-turn conversations."""
        print(f"🟠 Running MULTI-TURN test (up to {max_turns} turns)...")

        config = LoadTestConfig(
            max_concurrent_conversations=5,
            total_conversations=10,
            ramp_up_time_s=10.0,
            test_duration_s=180.0,
            conversation_templates=[
                "insurance_inquiry",
                "confused_customer",
                "claim_filing",
            ],
            ws_url=self.base_url,
            output_dir="tests/load/results",
            max_conversation_turns=max_turns,
            min_conversation_turns=2,
            turn_variation_strategy="random",
        )

        tester = ConversationLoadTester(config)
        results = await tester.run_load_test()

        print(f"📊 MULTI-TURN RESULTS ({max_turns} max turns):")
        tester.print_summary(results)

        filename = f"multi_turn_{max_turns}_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        results_file = tester.save_results(results, filename)

        return {
            "test_type": f"multi_turn_{max_turns}",
            "config": config,
            "results": results,
            "results_file": results_file,
            "summary": results.get_summary(),
        }

    async def run_escalating_turn_test(self, max_turns: int = 10) -> dict:
        """Test with escalating conversation complexity (increasing turns)."""
        print(f"🟣 Running ESCALATING-TURN test (up to {max_turns} turns)...")

        config = LoadTestConfig(
            max_concurrent_conversations=3,
            total_conversations=15,
            ramp_up_time_s=15.0,
            test_duration_s=300.0,
            conversation_templates=[
                "insurance_inquiry",
                "claim_filing",
                "policy_update",
            ],
            ws_url=self.base_url,
            output_dir="tests/load/results",
            max_conversation_turns=max_turns,
            min_conversation_turns=1,
            turn_variation_strategy="increasing",  # Gradually increase complexity
        )

        tester = ConversationLoadTester(config)
        results = await tester.run_load_test()

        print(f"📊 ESCALATING-TURN RESULTS (up to {max_turns} turns):")
        tester.print_summary(results)

        filename = (
            f"escalating_turn_{max_turns}_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        results_file = tester.save_results(results, filename)

        return {
            "test_type": f"escalating_turn_{max_turns}",
            "config": config,
            "results": results,
            "results_file": results_file,
            "summary": results.get_summary(),
        }

    def compare_turn_complexity_results(self, test_results: list) -> dict:
        """Compare results across different turn complexity levels."""

        print("\n📈 TURN COMPLEXITY COMPARISON")
        print("=" * 70)

        comparison = {"test_count": len(test_results), "tests": {}, "turn_analysis": {}}

        # Extract metrics for each test
        for test_result in test_results:
            test_type = test_result["test_type"]
            summary = test_result["summary"]
            config = test_result["config"]

            comparison["tests"][test_type] = {
                "success_rate": summary.get("success_rate_percent", 0),
                "max_turns": config.max_conversation_turns,
                "min_turns": config.min_conversation_turns,
                "avg_connection_ms": summary.get("connection_times_ms", {}).get("avg", 0),
                "avg_agent_response_ms": summary.get("agent_response_times_ms", {}).get("avg", 0),
                "avg_conversation_duration_s": summary.get("conversation_durations_s", {}).get(
                    "avg", 0
                ),
                "conversations_completed": summary.get("conversations_completed", 0),
                "error_count": summary.get("error_count", 0),
            }

        # Print comparison table
        print(
            f"{'Test Type':<20} {'Max Turns':<10} {'Success%':<8} {'Avg Duration(s)':<15} {'Avg Response(ms)':<15} {'Errors':<7}"
        )
        print("-" * 85)

        for test_type, metrics in comparison["tests"].items():
            print(
                f"{test_type:<20} "
                f"{metrics['max_turns']:<10} "
                f"{metrics['success_rate']:<8.1f} "
                f"{metrics['avg_conversation_duration_s']:<15.1f} "
                f"{metrics['avg_agent_response_ms']:<15.0f} "
                f"{metrics['error_count']:<7}"
            )

        # Analyze turn complexity impact
        turn_counts = [m["max_turns"] for m in comparison["tests"].values()]
        success_rates = [m["success_rate"] for m in comparison["tests"].values()]
        durations = [
            m["avg_conversation_duration_s"]
            for m in comparison["tests"].values()
            if m["avg_conversation_duration_s"] > 0
        ]

        if len(turn_counts) > 1:
            comparison["turn_analysis"] = {
                "turn_range": f"{min(turn_counts)} - {max(turn_counts)} turns",
                "success_rate_trend": (
                    "stable" if max(success_rates) - min(success_rates) < 15 else "degrading"
                ),
                "duration_scalability": (
                    "linear"
                    if durations and max(durations) / min(durations) < 3.0
                    else "exponential"
                ),
                "complexity_tolerance": "good" if min(success_rates) > 80 else "concerning",
            }

        print("\n🔍 TURN COMPLEXITY ANALYSIS:")
        for analysis_name, analysis_value in comparison.get("turn_analysis", {}).items():
            status_emoji = "✅" if analysis_value in ["stable", "linear", "good"] else "⚠️"
            print(f"   {status_emoji} {analysis_name.replace('_', ' ').title()}: {analysis_value}")

        return comparison

    async def run_turn_complexity_suite(self, max_turns_list: list = None) -> list:
        """Run a comprehensive suite testing different turn complexities."""

        if max_turns_list is None:
            max_turns_list = [1, 3, 5, 8, 10]

        print("🚀 Starting turn complexity testing suite")
        print(f"🔄 Turn counts to test: {max_turns_list}")
        print(f"🎯 Target URL: {self.base_url}")
        print("=" * 70)

        results = []

        # Run single turn test
        try:
            single_result = await self.run_single_turn_test()
            results.append(single_result)
            print("✅ Single-turn test completed")
            await asyncio.sleep(10)  # Brief pause
        except Exception as e:
            print(f"❌ Single-turn test failed: {e}")

        # Run multi-turn tests for each specified turn count
        for turn_count in max_turns_list[1:]:  # Skip 1 since we already did single-turn
            try:
                print(f"\n🔄 Running {turn_count}-turn test...")

                if turn_count <= 5:
                    result = await self.run_multi_turn_test(max_turns=turn_count)
                else:
                    result = await self.run_escalating_turn_test(max_turns=turn_count)

                results.append(result)
                print(f"✅ {turn_count}-turn test completed")

                # Pause between tests
                if turn_count < max(max_turns_list):
                    await asyncio.sleep(15)

            except Exception as e:
                print(f"❌ {turn_count}-turn test failed: {e}")

        # Generate comparison report
        if len(results) > 1:
            comparison = self.compare_turn_complexity_results(results)

        print("\n🎉 Turn complexity testing suite completed!")
        print(f"📊 Tests completed: {len(results)}/{len(max_turns_list)}")

        return results


async def main():
    """Main entry point for multi-turn load testing."""

    parser = argparse.ArgumentParser(description="Multi-Turn Conversation Load Testing")
    parser.add_argument(
        "--url",
        default="ws://localhost:8010/api/v1/media/stream",
        help="WebSocket URL to test",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=5,
        help="Maximum conversation turns to test (default: 5)",
    )
    parser.add_argument(
        "--turn-counts",
        nargs="+",
        type=int,
        default=[1, 3, 5],
        help="Specific turn counts to test (default: 1 3 5)",
    )
    parser.add_argument(
        "--test-type",
        choices=["single", "multi", "escalating", "suite"],
        default="suite",
        help="Type of test to run",
    )

    args = parser.parse_args()

    # Create results directory
    results_dir = Path("tests/load/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    # Run tests
    tester = MultiTurnLoadTest(args.url)

    if args.test_type == "single":
        results = [await tester.run_single_turn_test()]
    elif args.test_type == "multi":
        results = [await tester.run_multi_turn_test(args.max_turns)]
    elif args.test_type == "escalating":
        results = [await tester.run_escalating_turn_test(args.max_turns)]
    else:  # suite
        results = await tester.run_turn_complexity_suite(args.turn_counts)

    # Save overall summary
    overall_summary = {
        "timestamp": datetime.now().isoformat(),
        "url_tested": args.url,
        "test_type": args.test_type,
        "max_turns_tested": max(args.turn_counts) if args.test_type == "suite" else args.max_turns,
        "results": [
            {
                "test_type": r["test_type"],
                "success": "error" not in r,
                "summary": r.get("summary", {}),
                "results_file": r.get("results_file"),
            }
            for r in results
        ],
    }

    summary_file = (
        results_dir / f"multi_turn_test_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(summary_file, "w") as f:
        import json

        json.dump(overall_summary, f, indent=2)

    print(f"\n💾 Overall summary saved to: {summary_file}")


if __name__ == "__main__":
    asyncio.run(main())
