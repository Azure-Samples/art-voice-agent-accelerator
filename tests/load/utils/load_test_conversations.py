#!/usr/bin/env python3
"""
Conversation-Based Load Testing Framework
=========================================

Runs concurrent realistic conversations to test system performance 
and evaluate agent flows under load.
"""

import asyncio
import json
import time
import random
import uuid
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import statistics
from pathlib import Path

from utils.conversation_simulator import (
    ConversationSimulator, 
    ConversationTemplates, 
    ConversationMetrics,
    ConversationTemplate,
)


@dataclass
class LoadTestConfig:
    """Configuration for load testing with enhanced conversation control."""

    max_concurrent_conversations: int = 10
    total_conversations: int = 50
    ramp_up_time_s: float = 30.0  # Time to reach max concurrency
    test_duration_s: float = 300.0  # Total test duration
    conversation_templates: List[str] = field(
        default_factory=lambda: ["insurance_inquiry", "quick_question"]
    )
    ws_url: str = "ws://localhost:8010/api/v1/media/stream"
    output_dir: str = "load_test_results"

    # Enhanced conversation control
    max_conversation_turns: int = 5  # Maximum turns per conversation
    min_conversation_turns: int = 1  # Minimum turns per conversation
    turn_variation_strategy: str = "random"  # "random", "fixed", "increasing"


@dataclass
class LoadTestResults:
    """Results from load testing."""

    start_time: float
    end_time: float
    config: LoadTestConfig

    # High-level metrics
    total_conversations_attempted: int = 0
    total_conversations_completed: int = 0
    total_conversations_failed: int = 0

    # Performance metrics
    conversation_metrics: List[ConversationMetrics] = field(default_factory=list)
    connection_times_ms: List[float] = field(default_factory=list)
    conversation_durations_s: List[float] = field(default_factory=list)

    # Detailed metrics
    concurrent_conversations_peak: int = 0
    errors: List[str] = field(default_factory=list)

    # Agent performance
    agent_response_times_ms: List[float] = field(default_factory=list)
    speech_recognition_times_ms: List[float] = field(default_factory=list)

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the load test results."""
        duration = self.end_time - self.start_time
        success_rate = (
            self.total_conversations_completed
            / max(1, self.total_conversations_attempted)
        ) * 100

        summary = {
            "test_duration_s": duration,
            "success_rate_percent": success_rate,
            "conversations_attempted": self.total_conversations_attempted,
            "conversations_completed": self.total_conversations_completed,
            "conversations_failed": self.total_conversations_failed,
            "peak_concurrency": self.concurrent_conversations_peak,
            "error_count": len(self.errors),
        }

        # Connection metrics
        if self.connection_times_ms:
            summary["connection_times_ms"] = {
                "avg": statistics.mean(self.connection_times_ms),
                "min": min(self.connection_times_ms),
                "max": max(self.connection_times_ms),
                "p50": statistics.median(self.connection_times_ms),
                "p95": statistics.quantiles(self.connection_times_ms, n=20)[18]
                if len(self.connection_times_ms) >= 20
                else max(self.connection_times_ms),
            }

        # Conversation duration metrics
        if self.conversation_durations_s:
            summary["conversation_durations_s"] = {
                "avg": statistics.mean(self.conversation_durations_s),
                "min": min(self.conversation_durations_s),
                "max": max(self.conversation_durations_s),
                "p50": statistics.median(self.conversation_durations_s),
                "p95": statistics.quantiles(self.conversation_durations_s, n=20)[18]
                if len(self.conversation_durations_s) >= 20
                else max(self.conversation_durations_s),
            }

        # Agent performance metrics
        if self.agent_response_times_ms:
            summary["agent_response_times_ms"] = {
                "avg": statistics.mean(self.agent_response_times_ms),
                "min": min(self.agent_response_times_ms),
                "max": max(self.agent_response_times_ms),
                "p50": statistics.median(self.agent_response_times_ms),
                "p95": statistics.quantiles(self.agent_response_times_ms, n=20)[18]
                if len(self.agent_response_times_ms) >= 20
                else max(self.agent_response_times_ms),
            }

        return summary


class ConversationLoadTester:
    """Load testing framework for conversation simulations."""

    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.results = LoadTestResults(start_time=0, end_time=0, config=config)
        self.active_conversations = 0
        self.max_active_conversations = 0

        # Get conversation templates
        self.templates = {
            template.name: template
            for template in ConversationTemplates.get_all_templates()
        }

    async def run_single_conversation(
        self,
        template: ConversationTemplate,
        conversation_id: int,
        semaphore: asyncio.Semaphore,
    ) -> Optional[ConversationMetrics]:
        """Run a single conversation with concurrency control and configurable turn depth."""

        async with semaphore:
            self.active_conversations += 1
            self.max_active_conversations = max(
                self.max_active_conversations, self.active_conversations
            )

            # Determine number of turns for this conversation based on strategy
            if self.config.turn_variation_strategy == "random":
                num_turns = random.randint(
                    self.config.min_conversation_turns,
                    self.config.max_conversation_turns,
                )
            elif self.config.turn_variation_strategy == "increasing":
                # Gradually increase turns as conversations progress
                progress = min(1.0, conversation_id / self.config.total_conversations)
                range_size = (
                    self.config.max_conversation_turns
                    - self.config.min_conversation_turns
                )
                num_turns = self.config.min_conversation_turns + int(
                    progress * range_size
                )
            else:  # "fixed"
                num_turns = self.config.max_conversation_turns

            simulator = ConversationSimulator(
                ws_url=self.config.ws_url, conversation_turns=num_turns
            )
            session_id = f"load-test-{uuid.uuid4().hex}"

            try:
                print(
                    f"🎭 Starting conversation {conversation_id} ({template.name}, {num_turns} turns)"
                )

                metrics = await simulator.simulate_conversation(
                    template=template, session_id=session_id, max_turns=num_turns
                )

                # Update results
                self.results.total_conversations_completed += 1
                self.results.conversation_metrics.append(metrics)
                self.results.connection_times_ms.append(metrics.connection_time_ms)

                duration = metrics.end_time - metrics.start_time
                self.results.conversation_durations_s.append(duration)

                # Add agent performance metrics
                if metrics.total_agent_processing_time_ms > 0:
                    avg_agent_time = metrics.total_agent_processing_time_ms / max(
                        1, metrics.user_turns
                    )
                    self.results.agent_response_times_ms.append(avg_agent_time)

                if metrics.total_speech_recognition_time_ms > 0:
                    avg_speech_time = metrics.total_speech_recognition_time_ms / max(
                        1, metrics.user_turns
                    )
                    self.results.speech_recognition_times_ms.append(avg_speech_time)

                print(f"✅ Conversation {conversation_id} completed in {duration:.2f}s")
                return metrics

            except Exception as e:
                error_msg = f"Conversation {conversation_id} failed: {str(e)}"
                print(f"❌ {error_msg}")
                self.results.errors.append(error_msg)
                self.results.total_conversations_failed += 1
                return None

            finally:
                self.active_conversations -= 1

    async def run_load_test(self) -> LoadTestResults:
        """Run the complete load test."""

        print(f"🚀 Starting conversation load test")
        print(
            f"📊 Config: {self.config.max_concurrent_conversations} max concurrent, {self.config.total_conversations} total"
        )
        print(
            f"⏰ Duration: {self.config.test_duration_s}s with {self.config.ramp_up_time_s}s ramp-up"
        )
        print(f"🎭 Templates: {self.config.conversation_templates}")
        print("=" * 70)

        self.results.start_time = time.time()

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.config.max_concurrent_conversations)

        # Track active tasks
        active_tasks = set()
        conversation_counter = 0

        try:
            test_end_time = self.results.start_time + self.config.test_duration_s

            while (
                time.time() < test_end_time
                and conversation_counter < self.config.total_conversations
            ):
                # Calculate current target concurrency (ramp-up)
                elapsed = time.time() - self.results.start_time
                if elapsed < self.config.ramp_up_time_s:
                    # Linear ramp-up
                    target_concurrency = int(
                        (elapsed / self.config.ramp_up_time_s)
                        * self.config.max_concurrent_conversations
                    )
                    target_concurrency = max(1, target_concurrency)  # At least 1
                else:
                    target_concurrency = self.config.max_concurrent_conversations

                # Start new conversations if below target concurrency
                current_active = len([t for t in active_tasks if not t.done()])

                while (
                    current_active < target_concurrency
                    and conversation_counter < self.config.total_conversations
                    and time.time() < test_end_time
                ):
                    # Select template
                    template_name = random.choice(self.config.conversation_templates)
                    template = self.templates[template_name]

                    # Start conversation
                    conversation_counter += 1
                    self.results.total_conversations_attempted += 1

                    task = asyncio.create_task(
                        self.run_single_conversation(
                            template, conversation_counter, semaphore
                        )
                    )
                    active_tasks.add(task)
                    current_active += 1

                    # Small delay between starts to avoid thundering herd
                    await asyncio.sleep(0.1)

                # Clean up completed tasks
                completed_tasks = [t for t in active_tasks if t.done()]
                for task in completed_tasks:
                    active_tasks.remove(task)

                # Update peak concurrency
                self.results.concurrent_conversations_peak = max(
                    self.results.concurrent_conversations_peak,
                    self.max_active_conversations,
                )

                # Brief pause before next iteration
                await asyncio.sleep(1.0)

                # Progress update
                remaining_time = test_end_time - time.time()
                print(
                    f"⏱️  Active: {len(active_tasks)}, Completed: {self.results.total_conversations_completed}, "
                    f"Failed: {self.results.total_conversations_failed}, Time remaining: {remaining_time:.1f}s"
                )

            # Wait for remaining conversations to complete
            print(
                f"⏳ Waiting for {len(active_tasks)} remaining conversations to complete..."
            )
            if active_tasks:
                await asyncio.gather(*active_tasks, return_exceptions=True)

        except KeyboardInterrupt:
            print(f"\n🛑 Load test interrupted by user")
            # Cancel remaining tasks
            for task in active_tasks:
                task.cancel()

        except Exception as e:
            print(f"❌ Load test error: {e}")
            self.results.errors.append(f"Load test error: {str(e)}")

        finally:
            self.results.end_time = time.time()

        print(f"\n✅ Load test completed")
        return self.results

    def save_results(
        self, results: LoadTestResults, filename: Optional[str] = None
    ) -> str:
        """Save results to JSON file."""

        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"conversation_load_test_{timestamp}.json"

        # Create output directory
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(exist_ok=True)

        output_file = output_dir / filename

        # Prepare data for serialization
        results_data = {
            "config": {
                "max_concurrent_conversations": results.config.max_concurrent_conversations,
                "total_conversations": results.config.total_conversations,
                "ramp_up_time_s": results.config.ramp_up_time_s,
                "test_duration_s": results.config.test_duration_s,
                "conversation_templates": results.config.conversation_templates,
                "ws_url": results.config.ws_url,
            },
            "summary": results.get_summary(),
            "detailed_metrics": {
                "connection_times_ms": results.connection_times_ms,
                "conversation_durations_s": results.conversation_durations_s,
                "agent_response_times_ms": results.agent_response_times_ms,
                "speech_recognition_times_ms": results.speech_recognition_times_ms,
                "errors": results.errors,
            },
            "conversation_details": [
                {
                    "session_id": m.session_id,
                    "template_name": m.template_name,
                    "duration_s": m.end_time - m.start_time,
                    "connection_time_ms": m.connection_time_ms,
                    "user_turns": m.user_turns,
                    "agent_turns": m.agent_turns,
                    "audio_chunks_received": m.audio_chunks_received,
                    "errors": m.errors,
                }
                for m in results.conversation_metrics
            ],
        }

        with open(output_file, "w") as f:
            json.dump(results_data, f, indent=2)

        print(f"💾 Results saved to: {output_file}")
        return str(output_file)

    def print_summary(self, results: LoadTestResults):
        """Print a detailed summary of the test results."""
        summary = results.get_summary()

        print(f"\n📊 CONVERSATION LOAD TEST SUMMARY")
        print(f"=" * 70)
        print(summary)
        # Overall results
        print(f"🎯 Overall Results:")
        print(f"   Success Rate: {summary['success_rate_percent']:.1f}%")
        print(
            f"   Conversations: {summary['conversations_completed']}/{summary['conversations_attempted']}"
        )
        print(f"   Failed: {summary['conversations_failed']}")
        print(f"   Peak Concurrency: {summary['peak_concurrency']}")
        print(f"   Test Duration: {summary['test_duration_s']:.1f}s")

        # Connection performance
        if "connection_times_ms" in summary:
            conn = summary["connection_times_ms"]
            print(f"\n🔌 Connection Performance:")
            print(f"   Average: {conn['avg']:.1f}ms")
            print(f"   Median (P50): {conn['p50']:.1f}ms")
            print(f"   95th Percentile: {conn['p95']:.1f}ms")
            print(f"   Range: {conn['min']:.1f}ms - {conn['max']:.1f}ms")

        # Conversation duration
        if "conversation_durations_s" in summary:
            dur = summary["conversation_durations_s"]
            print(f"\n⏱️  Conversation Durations:")
            print(f"   Average: {dur['avg']:.2f}s")
            print(f"   Median (P50): {dur['p50']:.2f}s")
            print(f"   95th Percentile: {dur['p95']:.2f}s")
            print(f"   Range: {dur['min']:.2f}s - {dur['max']:.2f}s")

        # Agent performance
        if "agent_response_times_ms" in summary:
            agent = summary["agent_response_times_ms"]
            print(f"\n🤖 Agent Response Performance:")
            print(f"   Average: {agent['avg']:.1f}ms")
            print(f"   Median (P50): {agent['p50']:.1f}ms")
            print(f"   95th Percentile: {agent['p95']:.1f}ms")
            print(f"   Range: {agent['min']:.1f}ms - {agent['max']:.1f}ms")

        # Errors
        if summary["error_count"] > 0:
            print(f"\n❌ Errors ({summary['error_count']}):")
            for i, error in enumerate(results.errors[:5], 1):  # Show first 5 errors
                print(f"   {i}. {error}")
            if len(results.errors) > 5:
                print(f"   ... and {len(results.errors) - 5} more errors")
        else:
            print(f"\n✅ No errors detected")


async def main():
    """Example usage of the conversation load tester."""

    # Configure load test
    config = LoadTestConfig(
        max_concurrent_conversations=5,
        total_conversations=15,
        ramp_up_time_s=10.0,
        test_duration_s=60.0,
        conversation_templates=[
            "insurance_inquiry",
            "quick_question",
            "confused_customer",
        ],
    )

    # Run load test
    tester = ConversationLoadTester(config)
    results = await tester.run_load_test()

    # Display and save results
    tester.print_summary(results)
    results_file = tester.save_results(results)

    print(f"\n🎉 Load test complete! Results saved to {results_file}")


if __name__ == "__main__":
    asyncio.run(main())
