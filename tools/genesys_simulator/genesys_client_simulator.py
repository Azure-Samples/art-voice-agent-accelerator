"""
Genesys Cloud Audio Connector Client Simulator

This script simulates a Genesys Cloud Audio Connector client that:
1. Captures audio from the microphone
2. Sends it to the AudioConnector server via WebSocket
3. Receives audio responses and plays them through speakers

Protocol: AudioHook v2
Audio Format: PCMU (µ-law) at 8000 Hz
"""

import json
import uuid
import time
import threading
import queue
import struct
import sys
import os
from datetime import datetime

import websocket
import sounddevice as sd
import numpy as np
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# ============== Configuration ==============
SERVER_URL = os.getenv("SIMULATOR_SERVER_URL", "ws://localhost:8081")
SAMPLE_RATE = 8000  # Hz - AudioConnector uses 8kHz
CHANNELS = 1  # Mono
CHUNK_SIZE = 1600  # 200ms of audio at 8kHz (8000 * 0.2 = 1600 samples)
AUDIO_DTYPE = np.int16  # 16-bit PCM for capture/playback
PROMPT_NAME = os.getenv("PROMPT_NAME", "Invoices")

# Session configuration
ORGANIZATION_ID = os.getenv("SIMULATOR_ORG_ID", str(uuid.uuid4()))
CONVERSATION_ID = os.getenv("SIMULATOR_CONV_ID", str(uuid.uuid4()))
SESSION_ID = str(uuid.uuid4())

# ============== µ-law Encoding/Decoding ==============

# µ-law compression lookup table
ULAW_ENCODE_TABLE = [
    0, 0, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3,
    4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7
]

# µ-law decompression lookup table
ULAW_DECODE_TABLE = [
    -32124, -31100, -30076, -29052, -28028, -27004, -25980, -24956,
    -23932, -22908, -21884, -20860, -19836, -18812, -17788, -16764,
    -15996, -15484, -14972, -14460, -13948, -13436, -12924, -12412,
    -11900, -11388, -10876, -10364, -9852, -9340, -8828, -8316,
    -7932, -7676, -7420, -7164, -6908, -6652, -6396, -6140,
    -5884, -5628, -5372, -5116, -4860, -4604, -4348, -4092,
    -3900, -3772, -3644, -3516, -3388, -3260, -3132, -3004,
    -2876, -2748, -2620, -2492, -2364, -2236, -2108, -1980,
    -1884, -1820, -1756, -1692, -1628, -1564, -1500, -1436,
    -1372, -1308, -1244, -1180, -1116, -1052, -988, -924,
    -876, -844, -812, -780, -748, -716, -684, -652,
    -620, -588, -556, -524, -492, -460, -428, -396,
    -372, -356, -340, -324, -308, -292, -276, -260,
    -244, -228, -212, -196, -180, -164, -148, -132,
    -120, -112, -104, -96, -88, -80, -72, -64,
    -56, -48, -40, -32, -24, -16, -8, 0,
    32124, 31100, 30076, 29052, 28028, 27004, 25980, 24956,
    23932, 22908, 21884, 20860, 19836, 18812, 17788, 16764,
    15996, 15484, 14972, 14460, 13948, 13436, 12924, 12412,
    11900, 11388, 10876, 10364, 9852, 9340, 8828, 8316,
    7932, 7676, 7420, 7164, 6908, 6652, 6396, 6140,
    5884, 5628, 5372, 5116, 4860, 4604, 4348, 4092,
    3900, 3772, 3644, 3516, 3388, 3260, 3132, 3004,
    2876, 2748, 2620, 2492, 2364, 2236, 2108, 1980,
    1884, 1820, 1756, 1692, 1628, 1564, 1500, 1436,
    1372, 1308, 1244, 1180, 1116, 1052, 988, 924,
    876, 844, 812, 780, 748, 716, 684, 652,
    620, 588, 556, 524, 492, 460, 428, 396,
    372, 356, 340, 324, 308, 292, 276, 260,
    244, 228, 212, 196, 180, 164, 148, 132,
    120, 112, 104, 96, 88, 80, 72, 64,
    56, 48, 40, 32, 24, 16, 8, 0
]


def linear_to_ulaw(sample: int) -> int:
    """Convert a 16-bit linear PCM sample to 8-bit µ-law."""
    BIAS = 0x84
    CLIP = 32635
    
    sign = (sample >> 8) & 0x80
    if sign:
        sample = -sample
    if sample > CLIP:
        sample = CLIP
    
    sample = sample + BIAS
    exponent = ULAW_ENCODE_TABLE[(sample >> 7) & 0xFF]
    mantissa = (sample >> (exponent + 3)) & 0x0F
    
    ulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
    return ulaw_byte


def ulaw_to_linear(ulaw_byte: int) -> int:
    """Convert an 8-bit µ-law sample to 16-bit linear PCM."""
    return ULAW_DECODE_TABLE[ulaw_byte]


def pcm16_to_ulaw(pcm_data: bytes) -> bytes:
    """Convert PCM16 audio data to µ-law encoded data."""
    samples = struct.unpack(f'<{len(pcm_data)//2}h', pcm_data)
    ulaw_bytes = bytes([linear_to_ulaw(s) for s in samples])
    return ulaw_bytes


def ulaw_to_pcm16(ulaw_data: bytes) -> bytes:
    """Convert µ-law encoded data to PCM16 audio data."""
    samples = [ulaw_to_linear(b) for b in ulaw_data]
    pcm_data = struct.pack(f'<{len(samples)}h', *samples)
    return pcm_data


# ============== AudioConnector Protocol ==============

class AudioConnectorProtocol:
    """Handles the AudioHook v2 protocol messages."""
    
    def __init__(self, session_id: str, organization_id: str, conversation_id: str):
        self.session_id = session_id
        self.organization_id = organization_id
        self.conversation_id = conversation_id
        self.client_seq = 0
        self.server_seq = 0
        self.start_time = time.time()
    
    def get_position(self) -> str:
        """Get the current position as ISO8601 duration."""
        elapsed = time.time() - self.start_time
        return f"PT{elapsed:.3f}S"
    
    def create_message(self, msg_type: str, parameters: dict) -> dict:
        """Create a client message following the AudioHook v2 protocol."""
        self.client_seq += 1
        return {
            "version": "2",
            "id": self.session_id,
            "type": msg_type,
            "seq": self.client_seq,
            "serverseq": self.server_seq,
            "position": self.get_position(),
            "parameters": parameters
        }
    
    def create_open_message(self, input_variables: dict = None) -> dict:
        """Create the initial 'open' message to establish the session."""
        parameters = {
            "organizationId": self.organization_id,
            "conversationId": self.conversation_id,
            "participant": {
                "id": str(uuid.uuid4()),
                "ani": "+34666123456",
                "aniName": "Simulator User",
                "dnis": "+34900123456"
            },
            "media": [
                {
                    "type": "audio",
                    "format": "PCMU",
                    "channels": ["external"],
                    "rate": 8000
                }
            ],
            "language": "en-US"
        }
        
        if input_variables:
            parameters["inputVariables"] = input_variables
        
        return self.create_message("open", parameters)
    
    def create_ping_message(self) -> dict:
        """Create a 'ping' message for keep-alive."""
        return self.create_message("ping", {})
    
    def create_close_message(self, reason: str = "end") -> dict:
        """Create a 'close' message to end the session."""
        return self.create_message("close", {"reason": reason})
    
    def create_playback_started_message(self) -> dict:
        """Create a 'playback_started' message."""
        return self.create_message("playback_started", {})
    
    def create_playback_completed_message(self) -> dict:
        """Create a 'playback_completed' message."""
        return self.create_message("playback_completed", {})
    
    def update_server_seq(self, seq: int):
        """Update the last received server sequence number."""
        self.server_seq = seq


# ============== Genesys Client Simulator ==============

class GenesysClientSimulator:
    """
    Simulates a Genesys Cloud Audio Connector client.
    Captures audio from microphone, sends to server, plays back responses.
    """
    
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.ws = None
        self.protocol = AudioConnectorProtocol(SESSION_ID, ORGANIZATION_ID, CONVERSATION_ID)
        
        # Audio
        self.input_stream = None
        self.output_stream = None
        self.audio_output_queue = queue.Queue()
        
        # State
        self.running = False
        self.connected = False
        self.session_opened = False
        self.is_playing = False
        
        # Threads
        self.audio_capture_thread = None
        self.audio_playback_thread = None
        self.ping_thread = None
    
    def log(self, message: str):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] {message}")
    
    def connect(self):
        """Connect to the AudioConnector server."""
        headers = {
            "audiohook-session-id": self.protocol.session_id,
            "audiohook-organization-id": self.protocol.organization_id,
            "audiohook-correlation-id": str(uuid.uuid4()),
            "x-api-key": "ApiKey1"  # Matches the mock secret in SecretService
        }
        
        self.log(f"Connecting to {self.server_url}...")
        self.log(f"Session ID: {self.protocol.session_id}")
        self.log(f"Organization ID: {self.protocol.organization_id}")
        self.log(f"Correlation ID: {headers['audiohook-correlation-id']}")
        
        self.ws = websocket.WebSocketApp(
            self.server_url,
            header=headers,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        
        # Run WebSocket in a separate thread
        ws_thread = threading.Thread(target=self.ws.run_forever)
        ws_thread.daemon = True
        ws_thread.start()
        
        # Wait for connection
        timeout = 10
        start = time.time()
        while not self.connected and (time.time() - start) < timeout:
            time.sleep(0.1)
        
        if not self.connected:
            self.log("ERROR: Failed to connect to server")
            return False
        
        return True
    
    def on_open(self, ws):
        """Handle WebSocket connection opened."""
        self.log("WebSocket connected!")
        self.connected = True
        
        # Send the 'open' message to establish session
        # Booking example input variables
        '''
        input_vars = {
            "phoneNumber": "+34666123456",
            "emailAddress": "test@example.com",
            "storedCardPresent": "false",
            "CURRENT_DATE": datetime.now().strftime("%Y-%m-%d"),
            "promptName": PROMPT_NAME #"NewBookingPrompt"
        }
        '''
        # Invoices example input variables
        input_vars = {
            "phoneNumber": "+34666123456",
            "emailAddress": "test@example.com",
            "accountId": "false",
            "CURRENT_DATE": datetime.now().strftime("%Y-%m-%d"),
            "promptName": PROMPT_NAME
        }
        
        open_msg = self.protocol.create_open_message(input_vars)
        self.log(f"Sending OPEN message...")
        ws.send(json.dumps(open_msg))
    
    def on_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        if isinstance(message, bytes):
            # Binary message - audio data from server
            self.handle_audio_response(message)
        else:
            # Text message - protocol message
            self.handle_protocol_message(message)
    
    def handle_protocol_message(self, message: str):
        """Handle a protocol message from the server."""
        try:
            msg = json.loads(message)
            msg_type = msg.get("type", "unknown")
            
            # Update server sequence number
            if "seq" in msg:
                self.protocol.update_server_seq(msg["seq"])
            
            self.log(f"Received [{msg_type}]: {json.dumps(msg.get('parameters', {}), indent=2)[:200]}")
            
            if msg_type == "opened":
                self.log("✓ Session opened successfully!")
                self.session_opened = True
                self.start_audio_capture()
                self.start_audio_playback()
                self.start_ping_thread()
                
            elif msg_type == "disconnect":
                reason = msg.get("parameters", {}).get("reason", "unknown")
                info = msg.get("parameters", {}).get("info", "")
                self.log(f"Server disconnected: {reason} - {info}")
                self.stop()
                
            elif msg_type == "pong":
                pass  # Keep-alive response
                
            elif msg_type == "event":
                entities = msg.get("parameters", {}).get("entities", [])
                for entity in entities:
                    entity_type = entity.get("type", "unknown")
                    self.log(f"  Event: {entity_type}")
                    
                    if entity_type == "transcript":
                        # Log transcript from the conversation
                        data = entity.get("data", {})
                        for alt in data.get("alternatives", []):
                            for interp in alt.get("interpretations", []):
                                text = interp.get("transcript", "")
                                if text:
                                    channel = data.get("channel", "?")
                                    self.log(f"  📝 [{channel}]: {text}")
                    
                    elif entity_type == "barge_in":
                        self.log("  ⚡ Barge-in detected - stopping playback")
                        self.clear_audio_queue()
                        
        except json.JSONDecodeError as e:
            self.log(f"ERROR parsing message: {e}")
    
    def handle_audio_response(self, audio_data: bytes):
        """Handle incoming audio data from the server."""
        # Convert µ-law to PCM16 for playback
        pcm_data = ulaw_to_pcm16(audio_data)
        self.audio_output_queue.put(pcm_data)
        
        # Send playback_started on first audio
        if not self.is_playing:
            self.is_playing = True
            msg = self.protocol.create_playback_started_message()
            self.ws.send(json.dumps(msg))
            self.log("🔊 Audio playback started")
    
    def on_error(self, ws, error):
        """Handle WebSocket errors."""
        self.log(f"WebSocket ERROR: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket connection closed."""
        self.log(f"WebSocket closed: {close_status_code} - {close_msg}")
        self.connected = False
        self.stop()
    
    def start_audio_capture(self):
        """Start capturing audio from the microphone."""
        self.log("🎤 Starting microphone capture...")
        
        self.running = True
        self.audio_capture_thread = threading.Thread(target=self._audio_capture_loop)
        self.audio_capture_thread.daemon = True
        self.audio_capture_thread.start()
    
    def _audio_capture_loop(self):
        """Continuously capture and send audio from microphone."""
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=AUDIO_DTYPE, blocksize=CHUNK_SIZE) as stream:
                self.log("🎤 Microphone stream opened")
                while self.running and self.connected:
                    try:
                        # Read PCM16 audio from microphone
                        audio_data, overflowed = stream.read(CHUNK_SIZE)
                        if overflowed:
                            self.log("Warning: Audio input overflowed")
                        
                        # Convert numpy array to bytes
                        pcm_data = audio_data.tobytes()
                        
                        # Convert to µ-law
                        ulaw_data = pcm16_to_ulaw(pcm_data)
                        
                        # Send binary audio to server
                        if self.ws and self.session_opened:
                            self.ws.send(ulaw_data, opcode=websocket.ABNF.OPCODE_BINARY)
                            
                    except Exception as e:
                        if self.running:
                            self.log(f"Audio capture error: {e}")
                        break
        except Exception as e:
            self.log(f"Failed to open microphone: {e}")
    
    def start_audio_playback(self):
        """Start the audio playback thread."""
        self.log("🔊 Starting audio playback...")
        
        self.audio_playback_thread = threading.Thread(target=self._audio_playback_loop)
        self.audio_playback_thread.daemon = True
        self.audio_playback_thread.start()
    
    def _audio_playback_loop(self):
        """Continuously play audio from the output queue."""
        silence_count = 0
        
        try:
            with sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=AUDIO_DTYPE) as stream:
                self.log("🔊 Audio output stream opened")
                while self.running:
                    try:
                        # Get audio data with timeout
                        pcm_data = self.audio_output_queue.get(timeout=0.5)
                        # Convert bytes to numpy array for sounddevice
                        audio_array = np.frombuffer(pcm_data, dtype=AUDIO_DTYPE).reshape(-1, CHANNELS)
                        stream.write(audio_array)
                        silence_count = 0
                        
                    except queue.Empty:
                        # No audio to play
                        if self.is_playing:
                            silence_count += 1
                            if silence_count > 2:  # 1 second of silence
                                self.is_playing = False
                                # Send playback_completed
                                if self.ws and self.session_opened:
                                    msg = self.protocol.create_playback_completed_message()
                                    self.ws.send(json.dumps(msg))
                                    self.log("🔇 Audio playback completed")
                        continue
                    except Exception as e:
                        if self.running:
                            self.log(f"Audio playback error: {e}")
                        break
        except Exception as e:
            self.log(f"Failed to open audio output: {e}")
    
    def clear_audio_queue(self):
        """Clear the audio output queue (for barge-in)."""
        while not self.audio_output_queue.empty():
            try:
                self.audio_output_queue.get_nowait()
            except queue.Empty:
                break
        self.is_playing = False
    
    def start_ping_thread(self):
        """Start a thread to send periodic ping messages."""
        self.ping_thread = threading.Thread(target=self._ping_loop)
        self.ping_thread.daemon = True
        self.ping_thread.start()
    
    def _ping_loop(self):
        """Send periodic ping messages for keep-alive."""
        while self.running and self.connected:
            time.sleep(15)  # Send ping every 15 seconds
            if self.ws and self.session_opened:
                try:
                    msg = self.protocol.create_ping_message()
                    self.ws.send(json.dumps(msg))
                except Exception as e:
                    self.log(f"Ping error: {e}")
    
    def stop(self):
        """Stop the simulator and clean up resources."""
        self.log("Stopping simulator...")
        self.running = False
        
        # Send close message
        if self.ws and self.connected and self.session_opened:
            try:
                close_msg = self.protocol.create_close_message("end")
                self.ws.send(json.dumps(close_msg))
                time.sleep(0.5)
            except:
                pass
        
        # Close WebSocket
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        
        # Wait for audio threads to finish
        if self.audio_capture_thread and self.audio_capture_thread.is_alive():
            self.audio_capture_thread.join(timeout=1.0)
        if self.audio_playback_thread and self.audio_playback_thread.is_alive():
            self.audio_playback_thread.join(timeout=1.0)
        
        self.log("Simulator stopped.")
    
    def run(self):
        """Run the simulator."""
        print("\n" + "=" * 60)
        print("  GENESYS CLOUD AUDIO CONNECTOR - CLIENT SIMULATOR")
        print("=" * 60)
        print(f"\nServer URL: {self.server_url}")
        print("\nThis simulator will:")
        print("  1. Connect to the AudioConnector server")
        print("  2. Capture audio from your microphone")
        print("  3. Send it to the Voice AI agent")
        print("  4. Play back the agent's audio responses")
        print("\nPress Ctrl+C to stop.\n")
        print("=" * 60 + "\n")
        
        if not self.connect():
            return
        
        # Wait for session to be opened
        timeout = 10
        start = time.time()
        while not self.session_opened and (time.time() - start) < timeout:
            time.sleep(0.1)
        
        if not self.session_opened:
            self.log("ERROR: Session was not opened")
            self.stop()
            return
        
        # Keep running until interrupted
        try:
            while self.running and self.connected:
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.log("\nInterrupted by user")
        finally:
            self.stop()


# ============== Main ==============

def main():
    """Main entry point."""
    # Get server URL from environment or command line
    server_url = SERVER_URL
    
    if len(sys.argv) > 1:
        server_url = sys.argv[1]
    
    # Create and run simulator
    simulator = GenesysClientSimulator(server_url)
    simulator.run()


if __name__ == "__main__":
    main()
