#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Any, cast

from audio_util import CHANNELS, SAMPLE_RATE, AudioPlayerAsync
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI
from openai.resources.beta.realtime.realtime import AsyncRealtimeConnection
from openai.types.beta.realtime.session import Session
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.widgets import RichLog, Static
from typing_extensions import override

load_dotenv()


class SessionDisplay(Static):
    session_id = reactive("")

    @override
    def render(self) -> str:
        return f"Session ID: {self.session_id}" if self.session_id else "Connecting..."


class AudioStatusIndicator(Static):
    is_recording = reactive(False)

    @override
    def render(self) -> str:
        return (
            "🔴 Recording... (Press K to stop)"
            if self.is_recording
            else "⚪ Press K to start recording (Q to quit)"
        )


class RealtimeApp(App[None]):
    CSS = """
        Screen { background: #1a1b26; }
        Container { border: double rgb(91, 164, 91); }
        #bottom-pane { width: 100%; height: 82%; border: round rgb(205, 133, 63); content-align: center middle; }
        #status-indicator, #session-display { height: 3; content-align: center middle; background: #2a2b36; border: solid rgb(91, 164, 91); margin: 1 1; }
        Static { color: white; }
    """

    client: AsyncAzureOpenAI
    should_send_audio: asyncio.Event
    audio_player: AudioPlayerAsync
    last_audio_item_id: str | None
    connection: AsyncRealtimeConnection | None
    session: Session | None
    connected: asyncio.Event
    conversation_log: list[tuple[str, str]]

    def __init__(self) -> None:
        super().__init__()
        self.connection = None
        self.session = None
        self.client = AsyncAzureOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version="2024-10-01-preview",
        )
        self.audio_player = AudioPlayerAsync()
        self.last_audio_item_id = None
        self.should_send_audio = asyncio.Event()
        self.connected = asyncio.Event()
        self.conversation_log = []

    @override
    def compose(self) -> ComposeResult:
        with Container():
            yield SessionDisplay(id="session-display")
            yield AudioStatusIndicator(id="status-indicator")
            yield RichLog(id="bottom-pane", wrap=True, highlight=True, markup=True)

    async def on_mount(self) -> None:
        self.run_worker(self.handle_realtime_connection())
        self.run_worker(self.send_mic_audio())

    async def handle_realtime_connection(self) -> None:
        async with self.client.beta.realtime.connect(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT")
        ) as conn:
            self.connection = conn
            self.connected.set()

            await conn.session.update(
                session={
                    "modalities": ["text", "audio"],
                    "instructions": (
                        "You are a pharmacy assistant named PharmaHero. "
                        "Greet the user warmly. Assist with appointments, prescriptions, and medication advice. "
                        "Listen carefully, avoid interrupting your own speech. Be concise, empathetic, and helpful."
                    ),
                    "temperature": 1,
                    "input_audio_transcription": {"model": "whisper-1"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.2,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 1200,  # Slightly more forgiving for natural conversations
                        "create_response": True,
                    },
                }
            )

            acc_items: dict[str, Any] = {}

            async for event in conn:
                bottom_pane = self.query_one("#bottom-pane", RichLog)

                if event.type == "session.created":
                    self.session = event.session
                    session_display = self.query_one(SessionDisplay)
                    session_display.session_id = event.session.id
                    continue

                if event.type == "session.updated":
                    self.session = event.session
                    continue

                if event.type == "conversation.item.audio_transcription.completed":
                    # USER's speech converted to text
                    user_text = event.transcription.text
                    if user_text.strip():
                        self.conversation_log.append(("User", user_text))
                        self._refresh_log(bottom_pane)
                    continue

                if event.type == "response.audio.delta":
                    if event.item_id != self.last_audio_item_id:
                        self.audio_player.reset_frame_count()
                        self.last_audio_item_id = event.item_id
                    bytes_data = base64.b64decode(event.delta)
                    self.audio_player.add_data(bytes_data)
                    continue

                if event.type == "response.audio_transcript.delta":
                    # AI's spoken words transcription
                    try:
                        text = acc_items[event.item_id]
                    except KeyError:
                        acc_items[event.item_id] = event.delta
                    else:
                        acc_items[event.item_id] = text + event.delta

                    if event.delta.strip().endswith((".", "!", "?")):
                        self.conversation_log.append(
                            ("Assistant", acc_items[event.item_id])
                        )
                        self._refresh_log(bottom_pane)
                    continue

                if event.type == "response.tool_calls":
                    for call in event.tool_calls:
                        name = call.function.name
                        args = json.loads(call.function.arguments)
                        self.conversation_log.append(("ToolCall", f"{name}({args})"))
                        self._refresh_log(bottom_pane)
                    continue

    def _refresh_log(self, pane: RichLog) -> None:
        pane.clear()
        for who, msg in self.conversation_log:
            color = (
                "cyan" if who == "User" else "green" if who == "Assistant" else "yellow"
            )
            pane.write(f"[b {color}]{who}:[/b {color}] {msg}")

    async def _get_connection(self) -> AsyncRealtimeConnection:
        await self.connected.wait()
        assert self.connection is not None
        return self.connection

    async def send_mic_audio(self) -> None:
        import sounddevice as sd

        sent_audio = False
        read_size = int(SAMPLE_RATE * 0.02)
        stream = sd.InputStream(
            channels=CHANNELS, samplerate=SAMPLE_RATE, dtype="int16"
        )
        stream.start()

        status_indicator = self.query_one(AudioStatusIndicator)

        try:
            while True:
                if stream.read_available < read_size:
                    await asyncio.sleep(0)
                    continue

                await self.should_send_audio.wait()
                status_indicator.is_recording = True
                data, _ = stream.read(read_size)
                connection = await self._get_connection()

                if not sent_audio:
                    asyncio.create_task(connection.send({"type": "response.cancel"}))
                    sent_audio = True

                await connection.input_audio_buffer.append(
                    audio=base64.b64encode(cast(Any, data)).decode("utf-8")
                )
                await asyncio.sleep(0)
        finally:
            stream.stop()
            stream.close()

    async def on_key(self, event: events.Key) -> None:
        if event.key == "q":
            self.exit()
            return

        if event.key == "k":
            status_indicator = self.query_one(AudioStatusIndicator)
            if status_indicator.is_recording:
                self.should_send_audio.clear()
                status_indicator.is_recording = False

                if self.session and self.session.turn_detection is None:
                    conn = await self._get_connection()
                    await conn.input_audio_buffer.commit()
                    await conn.response.create()
            else:
                self.should_send_audio.set()
                status_indicator.is_recording = True


if __name__ == "__main__":
    app = RealtimeApp()
    app.run()
