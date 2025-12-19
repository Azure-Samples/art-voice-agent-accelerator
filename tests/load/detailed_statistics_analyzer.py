#!/usr/bin/env python3
"""
Detailed Turn-by-Turn Statistics Analyzer

Comprehensive statistical analysis for conversation load testing with
detailed per-turn metrics, percentiles, and performance insights.
Provides concurrency analysis and conversation recording capabilities.
"""

import argparse
import asyncio
import json
import random
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

from tests.load.utils.conversation_simulator import ConversationMetrics
from tests.load.utils.load_test_conversations import ConversationLoadTester, LoadTestConfig


class DetailedStatisticsAnalyzer:
    """Detailed statistics analyzer for conversation load testing with concurrency tracking."""

    def __init__(self, enable_recording: bool = False, recording_sample_rate: float = 0.1):
        """
        Initialize analyzer with optional conversation recording.

        Args:
            enable_recording: Whether to record sample conversations
            recording_sample_rate: Percentage of conversations to record (0.1 = 10%)
        """
        self.results = []
        self.enable_recording = enable_recording
        self.recording_sample_rate = recording_sample_rate
        self.recorded_conversations = []

    def calculate_comprehensive_statistics(self, values: list[float]) -> dict[str, float]:
        """Calculate comprehensive statistics including all percentiles."""
        if not values:
            return {}

        sorted_values = sorted(values)
        n = len(sorted_values)

        # Calculate percentiles
        percentiles = {}
        for p in [50, 75, 90, 95, 99, 99.9]:
            if n > 0:
                index = min(int((p / 100.0) * n), n - 1)
                percentiles[f"p{p:g}"] = sorted_values[index]

        return {
            "count": n,
            "min": min(sorted_values),
            "max": max(sorted_values),
            "mean": statistics.mean(sorted_values),
            "median": statistics.median(sorted_values),
            "stddev": statistics.stdev(sorted_values) if n > 1 else 0,
            "variance": statistics.variance(sorted_values) if n > 1 else 0,
            **percentiles,
        }

    def analyze_conversation_metrics(
        self, conversation_metrics: list[ConversationMetrics]
    ) -> dict[str, Any]:
        """Analyze detailed conversation metrics with per-turn breakdown and concurrency analysis."""

        print(f"Analyzing {len(conversation_metrics)} conversations...")

        # Sample conversations for recording if enabled
        if self.enable_recording:
            sample_size = max(1, int(len(conversation_metrics) * self.recording_sample_rate))
            self.recorded_conversations = random.sample(conversation_metrics, sample_size)
            print(f"Recording {len(self.recorded_conversations)} sample conversations for analysis")

        # Extract all turn metrics
        all_turn_metrics = []
        for conv in conversation_metrics:
            all_turn_metrics.extend(conv.turn_metrics)

        successful_turns = [t for t in all_turn_metrics if t.turn_successful]
        failed_turns = [t for t in all_turn_metrics if not t.turn_successful]

        print(f"Total turns: {len(all_turn_metrics)}")
        print(f"Successful turns: {len(successful_turns)}")
        print(f"Failed turns: {len(failed_turns)}")

        if not successful_turns:
            return {"error": "No successful turns to analyze"}

        # Analyze concurrency patterns
        concurrency_analysis = self._analyze_concurrency_patterns(conversation_metrics)

        # Collect metrics for analysis
        speech_recognition_latencies = [
            t.speech_recognition_latency_ms
            for t in successful_turns
            if t.speech_recognition_latency_ms > 0
        ]
        agent_processing_latencies = [
            t.agent_processing_latency_ms
            for t in successful_turns
            if t.agent_processing_latency_ms > 0
        ]
        end_to_end_latencies = [t.end_to_end_latency_ms for t in successful_turns]
        audio_send_durations = [t.audio_send_duration_ms for t in successful_turns]

        # Per-turn position analysis
        turn_position_analysis = {}
        max_turns = max(t.turn_number for t in all_turn_metrics) if all_turn_metrics else 0

        for turn_num in range(1, max_turns + 1):
            turn_data = [t for t in successful_turns if t.turn_number == turn_num]
            if turn_data:
                turn_position_analysis[f"turn_{turn_num}"] = {
                    "count": len(turn_data),
                    "success_rate": len(turn_data)
                    / len([t for t in all_turn_metrics if t.turn_number == turn_num])
                    * 100,
                    "speech_recognition_ms": self.calculate_comprehensive_statistics(
                        [
                            t.speech_recognition_latency_ms
                            for t in turn_data
                            if t.speech_recognition_latency_ms > 0
                        ]
                    ),
                    "agent_processing_ms": self.calculate_comprehensive_statistics(
                        [
                            t.agent_processing_latency_ms
                            for t in turn_data
                            if t.agent_processing_latency_ms > 0
                        ]
                    ),
                    "end_to_end_ms": self.calculate_comprehensive_statistics(
                        [t.end_to_end_latency_ms for t in turn_data]
                    ),
                }

        # Conversation-level analysis
        conversation_durations = []
        conversation_success_rates = []
        conversations_by_template = {}

        for conv in conversation_metrics:
            duration = conv.end_time - conv.start_time
            conversation_durations.append(duration)

            if conv.turn_metrics:
                success_rate = (
                    len([t for t in conv.turn_metrics if t.turn_successful])
                    / len(conv.turn_metrics)
                    * 100
                )
                conversation_success_rates.append(success_rate)

            # Group by template
            template = conv.template_name
            if template not in conversations_by_template:
                conversations_by_template[template] = []
            conversations_by_template[template].append(conv)

        # Template comparison
        template_analysis = {}
        for template, convs in conversations_by_template.items():
            template_turns = []
            for conv in convs:
                template_turns.extend([t for t in conv.turn_metrics if t.turn_successful])

            template_analysis[template] = {
                "conversation_count": len(convs),
                "total_turns": len([t for conv in convs for t in conv.turn_metrics]),
                "successful_turns": len(template_turns),
                "avg_conversation_duration_s": statistics.mean(
                    [conv.end_time - conv.start_time for conv in convs]
                ),
                "speech_recognition_ms": self.calculate_comprehensive_statistics(
                    [
                        t.speech_recognition_latency_ms
                        for t in template_turns
                        if t.speech_recognition_latency_ms > 0
                    ]
                ),
                "agent_processing_ms": self.calculate_comprehensive_statistics(
                    [
                        t.agent_processing_latency_ms
                        for t in template_turns
                        if t.agent_processing_latency_ms > 0
                    ]
                ),
                "end_to_end_ms": self.calculate_comprehensive_statistics(
                    [t.end_to_end_latency_ms for t in template_turns]
                ),
            }

        return {
            "summary": {
                "total_conversations": len(conversation_metrics),
                "total_turns": len(all_turn_metrics),
                "successful_turns": len(successful_turns),
                "failed_turns": len(failed_turns),
                "overall_turn_success_rate": (
                    len(successful_turns) / len(all_turn_metrics) * 100 if all_turn_metrics else 0
                ),
                "avg_conversation_duration_s": (
                    statistics.mean(conversation_durations) if conversation_durations else 0
                ),
            },
            "concurrency_analysis": concurrency_analysis,
            "overall_latency_statistics": {
                "speech_recognition_ms": self.calculate_comprehensive_statistics(
                    speech_recognition_latencies
                ),
                "agent_processing_ms": self.calculate_comprehensive_statistics(
                    agent_processing_latencies
                ),
                "end_to_end_ms": self.calculate_comprehensive_statistics(end_to_end_latencies),
                "audio_send_duration_ms": self.calculate_comprehensive_statistics(
                    audio_send_durations
                ),
            },
            "per_turn_position_analysis": turn_position_analysis,
            "per_template_analysis": template_analysis,
            "conversation_level_statistics": {
                "conversation_durations_s": self.calculate_comprehensive_statistics(
                    conversation_durations
                ),
                "conversation_success_rates": self.calculate_comprehensive_statistics(
                    conversation_success_rates
                ),
            },
            "failure_analysis": {
                "failed_turn_count": len(failed_turns),
                "failure_rate_by_turn": {
                    f"turn_{turn_num}": {
                        "failed": len([t for t in failed_turns if t.turn_number == turn_num]),
                        "total": len([t for t in all_turn_metrics if t.turn_number == turn_num]),
                        "failure_rate": len([t for t in failed_turns if t.turn_number == turn_num])
                        / max(
                            1,
                            len([t for t in all_turn_metrics if t.turn_number == turn_num]),
                        )
                        * 100,
                    }
                    for turn_num in range(1, max_turns + 1)
                },
                "common_errors": self._analyze_common_errors(failed_turns),
            },
            "recorded_conversations": (
                self._prepare_recorded_conversations() if self.enable_recording else []
            ),
        }

    def _analyze_common_errors(self, failed_turns) -> dict[str, int]:
        """Analyze common error patterns in failed turns."""
        error_counts = {}
        for turn in failed_turns:
            error = turn.error_message or "Unknown error"
            error_counts[error] = error_counts.get(error, 0) + 1

        # Sort by frequency
        return dict(sorted(error_counts.items(), key=lambda x: x[1], reverse=True))

    def _analyze_concurrency_patterns(
        self, conversation_metrics: list[ConversationMetrics]
    ) -> dict[str, Any]:
        """Analyze concurrency patterns and peak concurrent connections."""
        if not conversation_metrics:
            return {}

        # Create timeline of conversation events
        events = []
        for conv in conversation_metrics:
            events.append({"time": conv.start_time, "type": "start", "conv_id": conv.session_id})
            events.append({"time": conv.end_time, "type": "end", "conv_id": conv.session_id})

        # Sort events by time
        events.sort(key=lambda x: x["time"])

        # Track concurrent conversations over time
        concurrent_count = 0
        peak_concurrent = 0
        peak_time = None
        concurrency_timeline = []

        for event in events:
            if event["type"] == "start":
                concurrent_count += 1
                if concurrent_count > peak_concurrent:
                    peak_concurrent = concurrent_count
                    peak_time = event["time"]
            else:
                concurrent_count -= 1

            concurrency_timeline.append(
                {"time": event["time"], "concurrent_count": concurrent_count}
            )

        # Calculate average concurrency
        if concurrency_timeline:
            avg_concurrent = statistics.mean(
                [point["concurrent_count"] for point in concurrency_timeline]
            )
        else:
            avg_concurrent = 0

        return {
            "peak_concurrent_conversations": peak_concurrent,
            "peak_concurrency_time": peak_time,
            "average_concurrent_conversations": avg_concurrent,
            "concurrency_timeline_points": len(concurrency_timeline),
            "total_test_duration_s": (
                max([conv.end_time for conv in conversation_metrics])
                - min([conv.start_time for conv in conversation_metrics])
                if conversation_metrics
                else 0
            ),
        }

    def _prepare_recorded_conversations(self) -> list[dict[str, Any]]:
        """Prepare recorded conversation data for analysis including audio and text."""
        from pathlib import Path

        recorded_data = []

        # Create audio output directory
        audio_output_dir = Path("tests/load/results/conversation_audio")
        audio_output_dir.mkdir(parents=True, exist_ok=True)

        for conv in self.recorded_conversations:
            conversation_record = {
                "session_id": conv.session_id,
                "template_name": conv.template_name,
                "start_time": conv.start_time,
                "end_time": conv.end_time,
                "duration_s": conv.end_time - conv.start_time,
                "total_turns": len(conv.turn_metrics),
                "successful_turns": len([t for t in conv.turn_metrics if t.turn_successful]),
                "turns": [],
                "audio_files": [],
            }

            for turn in conv.turn_metrics:
                # Save agent audio responses to files
                turn_audio_files = []
                if turn.agent_audio_responses:
                    for i, audio_data in enumerate(turn.agent_audio_responses):
                        if audio_data:  # Only save non-empty audio
                            # Create filename for this audio chunk
                            audio_filename = (
                                f"{conv.session_id}_turn_{turn.turn_number}_chunk_{i+1}.pcm"
                            )
                            audio_file_path = audio_output_dir / audio_filename

                            try:
                                # Save audio data as PCM file
                                with open(audio_file_path, "wb") as f:
                                    f.write(audio_data)
                                turn_audio_files.append(
                                    {
                                        "filename": audio_filename,
                                        "path": str(audio_file_path),
                                        "size_bytes": len(audio_data),
                                        "duration_s": len(audio_data)
                                        / (16000 * 2),  # Assuming 16kHz, 16-bit
                                    }
                                )
                            except Exception as e:
                                print(
                                    f"      ⚠️  Failed to save audio for turn {turn.turn_number}: {e}"
                                )

                # Combine all agent audio into single file per turn
                if turn.agent_audio_responses:
                    combined_audio = b"".join(turn.agent_audio_responses)
                    if combined_audio:
                        combined_filename = (
                            f"{conv.session_id}_turn_{turn.turn_number}_combined.pcm"
                        )
                        combined_file_path = audio_output_dir / combined_filename

                        try:
                            with open(combined_file_path, "wb") as f:
                                f.write(combined_audio)
                            turn_audio_files.append(
                                {
                                    "filename": combined_filename,
                                    "path": str(combined_file_path),
                                    "size_bytes": len(combined_audio),
                                    "duration_s": len(combined_audio) / (16000 * 2),
                                    "type": "combined_response",
                                }
                            )
                        except Exception as e:
                            print(
                                f"      ⚠️  Failed to save combined audio for turn {turn.turn_number}: {e}"
                            )

                turn_record = {
                    "turn_number": turn.turn_number,
                    "user_input_text": turn.turn_text,
                    "user_speech_recognized": turn.user_speech_recognized,
                    "agent_text_responses": turn.agent_text_responses,
                    "turn_successful": turn.turn_successful,
                    "speech_recognition_latency_ms": turn.speech_recognition_latency_ms,
                    "agent_processing_latency_ms": turn.agent_processing_latency_ms,
                    "end_to_end_latency_ms": turn.end_to_end_latency_ms,
                    "audio_send_duration_ms": turn.audio_send_duration_ms,
                    "error_message": turn.error_message,
                    "audio_chunks_received": turn.audio_chunks_received,  # Use actual chunk count, not audio responses count
                    "audio_files": turn_audio_files,
                    "full_responses_received": turn.full_responses_received,  # Include raw WebSocket responses for debugging
                    "conversation_flow": {
                        "user_said": turn.turn_text,
                        "system_heard": turn.user_speech_recognized,
                        "agent_responded": turn.agent_text_responses,
                        "audio_response_available": turn.audio_chunks_received
                        > 0,  # Based on actual chunks received
                    },
                }
                conversation_record["turns"].append(turn_record)
                conversation_record["audio_files"].extend(turn_audio_files)

            recorded_data.append(conversation_record)

        return recorded_data

    def print_detailed_statistics(self, analysis: dict[str, Any]):
        """Print comprehensive statistics in a readable format."""

        print("\n" + "=" * 80)
        print("DETAILED CONVERSATION STATISTICS ANALYSIS")
        print("=" * 80)

        # Summary
        summary = analysis["summary"]
        print("\nSUMMARY")
        print(f"{'Total Conversations:':<25} {summary['total_conversations']}")
        print(f"{'Total Turns:':<25} {summary['total_turns']}")
        print(f"{'Successful Turns:':<25} {summary['successful_turns']}")
        print(f"{'Failed Turns:':<25} {summary['failed_turns']}")
        print(f"{'Turn Success Rate:':<25} {summary['overall_turn_success_rate']:.1f}%")
        print(f"{'Avg Conversation:':<25} {summary['avg_conversation_duration_s']:.2f}s")

        # Concurrency Analysis
        if "concurrency_analysis" in analysis:
            concurrency = analysis["concurrency_analysis"]
            print("\nCONCURRENCY ANALYSIS")
            print(
                f"{'Peak Concurrent:':<25} {concurrency.get('peak_concurrent_conversations', 0)} conversations"
            )
            print(
                f"{'Average Concurrent:':<25} {concurrency.get('average_concurrent_conversations', 0):.1f} conversations"
            )
            print(
                f"{'Total Test Duration:':<25} {concurrency.get('total_test_duration_s', 0):.1f}s"
            )

        # Overall latency statistics
        print("\nOVERALL LATENCY STATISTICS")
        latency_stats = analysis["overall_latency_statistics"]

        for metric_name, stats in latency_stats.items():
            if stats:
                print(f"\n{metric_name.replace('_', ' ').title()}")
                print(f"  Count: {stats['count']:>8}")
                print(f"  Mean:  {stats['mean']:>8.1f}ms")
                print(f"  P50:   {stats['median']:>8.1f}ms")
                print(f"  P95:   {stats['p95']:>8.1f}ms")
                print(f"  P99:   {stats['p99']:>8.1f}ms")
                if "p99.9" in stats:
                    print(f"  P99.9: {stats['p99.9']:>8.1f}ms")
                print(f"  Min:   {stats['min']:>8.1f}ms")
                print(f"  Max:   {stats['max']:>8.1f}ms")
                print(f"  StdDev:{stats['stddev']:>8.1f}ms")

        # Per-turn position analysis
        print("\nPER-TURN POSITION ANALYSIS")
        turn_analysis = analysis["per_turn_position_analysis"]

        print(
            f"{'Turn':<6} {'Count':<8} {'Success%':<9} {'Recognition P95':<15} {'Processing P95':<15} {'E2E P95':<10}"
        )
        print("-" * 75)

        for turn_key in sorted(turn_analysis.keys(), key=lambda x: int(x.split("_")[1])):
            turn_data = turn_analysis[turn_key]
            turn_num = turn_key.split("_")[1]

            recognition_p95 = turn_data.get("speech_recognition_ms", {}).get("p95", 0)
            processing_p95 = turn_data.get("agent_processing_ms", {}).get("p95", 0)
            e2e_p95 = turn_data.get("end_to_end_ms", {}).get("p95", 0)

            print(
                f"{turn_num:<6} "
                f"{turn_data['count']:<8} "
                f"{turn_data['success_rate']:<8.1f}% "
                f"{recognition_p95:<14.1f}ms "
                f"{processing_p95:<14.1f}ms "
                f"{e2e_p95:<9.1f}ms"
            )

        # Template comparison
        print("\nTEMPLATE COMPARISON ANALYSIS")
        template_analysis = analysis["per_template_analysis"]

        for template_name, template_data in template_analysis.items():
            print(f"\n{template_name.replace('_', ' ').title()}")
            print(f"  Conversations: {template_data['conversation_count']}")
            print(
                f"  Successful Turns: {template_data['successful_turns']}/{template_data['total_turns']}"
            )
            print(f"  Avg Duration: {template_data['avg_conversation_duration_s']:.2f}s")

            if template_data["end_to_end_ms"]:
                e2e = template_data["end_to_end_ms"]
                print(
                    f"  End-to-End: Mean={e2e.get('mean', 0):.1f}ms, P95={e2e.get('p95', 0):.1f}ms, P99={e2e.get('p99', 0):.1f}ms"
                )

        # Failure analysis
        print("\nFAILURE ANALYSIS")
        failure_analysis = analysis["failure_analysis"]

        if failure_analysis["failed_turn_count"] > 0:
            print(f"Total Failed Turns: {failure_analysis['failed_turn_count']}")

            print("\nFailure Rate by Turn Position:")
            for turn_key, failure_data in failure_analysis["failure_rate_by_turn"].items():
                if failure_data["total"] > 0:
                    turn_num = turn_key.split("_")[1]
                    print(
                        f"  Turn {turn_num}: {failure_data['failed']}/{failure_data['total']} ({failure_data['failure_rate']:.1f}%)"
                    )

            print("\nCommon Error Messages:")
            for error, count in list(failure_analysis["common_errors"].items())[:5]:
                print(f"  {count}x: {error}")
        else:
            print("No failures detected")

        # Recorded conversations summary
        if "recorded_conversations" in analysis and analysis["recorded_conversations"]:
            print("\nRECORDED CONVERSATIONS")
            print(
                f"Recorded {len(analysis['recorded_conversations'])} sample conversations for detailed analysis"
            )

            # Show conversation flow summary
            for i, conv in enumerate(
                analysis["recorded_conversations"][:2]
            ):  # Show first 2 conversations
                print(f"\nConversation {i+1} ({conv['session_id'][:8]}...):")
                print(f"  Template: {conv['template_name']}")
                print(f"  Duration: {conv['duration_s']:.1f}s")
                print(f"  Audio files saved: {len(conv['audio_files'])}")

                # Show conversation flow for first few turns
                for turn in conv["turns"][:3]:  # Show first 3 turns
                    flow = turn["conversation_flow"]
                    print(f"  Turn {turn['turn_number']}:")
                    print(
                        f"    User said: '{flow['user_said'][:60]}{'...' if len(flow['user_said']) > 60 else ''}'"
                    )
                    if flow["system_heard"]:
                        print(
                            f"    System heard: '{flow['system_heard'][:60]}{'...' if len(flow['system_heard']) > 60 else ''}'"
                        )
                    if flow["agent_responded"]:
                        for resp in flow["agent_responded"][:1]:  # Show first response
                            print(f"    Agent said: '{resp[:60]}{'...' if len(resp) > 60 else ''}'")
                    print(
                        f"    Audio available: {'Yes' if flow['audio_response_available'] else 'No'}"
                    )

                if len(conv["turns"]) > 3:
                    print(f"  ... and {len(conv['turns']) - 3} more turns")

            print("Conversation records and audio files saved for manual review")

    def save_detailed_analysis(self, analysis: dict[str, Any], filename: str | None = None) -> str:
        """Save detailed analysis to JSON file."""

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"detailed_conversation_analysis_{timestamp}.json"

        # Create output directory
        output_dir = Path("tests/load/results")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / filename

        with open(output_file, "w") as f:
            json.dump(analysis, f, indent=2)

        print(f"\nDetailed analysis saved to: {output_file}")

        # Save recorded conversations separately if available
        if "recorded_conversations" in analysis and analysis["recorded_conversations"]:
            recordings_file = (
                output_dir
                / f"recorded_conversations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            with open(recordings_file, "w") as f:
                json.dump(analysis["recorded_conversations"], f, indent=2)
            print(f"Recorded conversations saved to: {recordings_file}")

        return str(output_file)


async def run_detailed_load_test(
    url: str = "ws://localhost:8010/api/v1/media/stream",
    conversation_turns: int = 5,
    total_conversations: int = 20,
    concurrent_conversations: int = 5,
    enable_recording: bool = True,
    recording_sample_rate: float = 0.2,
) -> dict[str, Any]:
    """Run a load test specifically designed for detailed statistics collection."""

    print("Running Detailed Statistics Load Test")
    print(f"Turns per conversation: {conversation_turns}")
    print(f"Total conversations: {total_conversations}")
    print(f"Concurrent conversations: {concurrent_conversations}")
    print(f"Target URL: {url}")
    if enable_recording:
        print(f"Recording {recording_sample_rate*100:.0f}% of conversations for analysis")
    print("=" * 70)

    # Configure for detailed analysis - use fixed turn count for consistent statistics
    config = LoadTestConfig(
        max_concurrent_conversations=concurrent_conversations,
        total_conversations=total_conversations,
        ramp_up_time_s=10.0,
        test_duration_s=600.0,  # 10 minutes max
        conversation_templates=[
            "insurance_inquiry",
            "quick_question",
        ],  # Simplified scenarios
        ws_url=url,
        output_dir="tests/load/results",
        max_conversation_turns=conversation_turns,
        min_conversation_turns=conversation_turns,  # Fixed turn count for consistent analysis
        turn_variation_strategy="fixed",
    )

    # Run load test
    tester = ConversationLoadTester(config)
    results = await tester.run_load_test()

    # Analyze detailed statistics
    analyzer = DetailedStatisticsAnalyzer(
        enable_recording=enable_recording, recording_sample_rate=recording_sample_rate
    )
    detailed_analysis = analyzer.analyze_conversation_metrics(results.conversation_metrics)

    # Print detailed results
    analyzer.print_detailed_statistics(detailed_analysis)

    # Save results
    filename = (
        f"detailed_stats_{conversation_turns}turns_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    analysis_file = analyzer.save_detailed_analysis(detailed_analysis, filename)

    return {
        "config": config,
        "load_test_results": results,
        "detailed_analysis": detailed_analysis,
        "analysis_file": analysis_file,
    }


async def main():
    """Main entry point for detailed statistics load testing."""

    parser = argparse.ArgumentParser(description="Detailed Turn-by-Turn Statistics Load Testing")
    parser.add_argument(
        "--url",
        default="ws://localhost:8010/api/v1/media/stream",
        help="WebSocket URL to test",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=5,
        help="Fixed number of turns per conversation (default: 5)",
    )
    parser.add_argument(
        "--conversations",
        type=int,
        default=20,
        help="Total number of conversations to run (default: 20)",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=5,
        help="Number of concurrent conversations (default: 5)",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        default=True,
        help="Enable conversation recording for analysis (default: True)",
    )
    parser.add_argument(
        "--record-rate",
        type=float,
        default=0.2,
        help="Percentage of conversations to record (default: 0.2 = 20%%)",
    )

    args = parser.parse_args()

    # Run detailed load test
    results = await run_detailed_load_test(
        url=args.url,
        conversation_turns=args.turns,
        total_conversations=args.conversations,
        concurrent_conversations=args.concurrent,
        enable_recording=args.record,
        recording_sample_rate=args.record_rate,
    )

    print("\nDetailed statistics analysis completed!")
    print(f"Analysis saved to: {results['analysis_file']}")

    # Show peak concurrency information
    concurrency = results["detailed_analysis"].get("concurrency_analysis", {})
    if concurrency:
        print("\nKey Performance Indicators:")
        print(
            f"Peak Concurrent Conversations: {concurrency.get('peak_concurrent_conversations', 0)}"
        )
        print(f"Average Concurrent: {concurrency.get('average_concurrent_conversations', 0):.1f}")
        print(f"Total Test Duration: {concurrency.get('total_test_duration_s', 0):.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
