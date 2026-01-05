"""
TTS Text Processing Utilities
==============================

Extracted from CascadeOrchestratorAdapter as part of Priority 3 refactoring.

Handles:
- Markdown sanitization for TTS
- Sentence boundary detection
- Text buffer splitting

Original location: orchestrator.py lines 1199-1242
"""

import re


class TTSTextProcessor:
    """
    Utility class for processing text for Text-to-Speech (TTS) output.

    Handles markdown removal, sentence boundary detection, and buffer splitting
    to enable smooth streaming TTS with natural sentence breaks.
    """

    # Sentence boundary punctuation
    PRIMARY_TERMS = ".!?"

    @staticmethod
    def sanitize_tts_text(text: str) -> str:
        """
        Remove markdown formatting so TTS only speaks plain text.

        Removes:
        - Links: [text](url) → text
        - Code blocks: `code` → code
        - Formatting: *, _, ~, `
        - Newlines and extra whitespace

        Args:
            text: Raw text with potential markdown

        Returns:
            Sanitized plain text suitable for TTS
        """
        if not text:
            return ""

        sanitized = text

        # Remove markdown links [text](url) → text
        sanitized = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", sanitized)

        # Remove code blocks `code` or ```code``` → code
        sanitized = re.sub(r"`{1,3}([^`]+)`{1,3}", r"\1", sanitized)

        # Replace newlines with spaces
        sanitized = sanitized.replace("\r", " ").replace("\n", " ")

        # Remove formatting characters
        sanitized = sanitized.replace("*", " ").replace("_", " ")
        sanitized = sanitized.replace("~", " ").replace("`", " ")

        # Normalize whitespace
        sanitized = re.sub(r"\s+", " ", sanitized)

        return sanitized

    @staticmethod
    def find_tts_boundary(text: str, terms: str | None = None, min_index: int = 0) -> int:
        """
        Find the first punctuation boundary that is safe to split on.

        Looks for sentence endings (., !, ?) that are followed by whitespace
        or closing punctuation, avoiding false positives like:
        - Numbers: 3.14
        - Abbreviations: Dr. Smith
        - URLs: example.com

        Args:
            text: Text to search for boundaries
            terms: Punctuation characters to search for (default: .!?)
            min_index: Minimum index to start searching from

        Returns:
            Index of the boundary, or -1 if no suitable boundary found
        """
        if not text:
            return -1

        if terms is None:
            terms = TTSTextProcessor.PRIMARY_TERMS

        for match in re.finditer(rf"[{re.escape(terms)}]", text):
            idx = match.start()

            # Skip if before minimum index
            if idx < min_index:
                continue

            # Check character after punctuation
            next_char = text[idx + 1 : idx + 2]

            # If there's a next character and it's not whitespace
            if next_char and not next_char.isspace():
                # Allow closing punctuation like ".", ").", "]."
                if next_char in "\"')]}":
                    # Check character after closing punctuation
                    after = text[idx + 2 : idx + 3]
                    if after and not after.isspace():
                        continue  # Not a sentence boundary
                else:
                    continue  # Not a sentence boundary

            # Special case for periods: avoid splitting numbers like 3.14
            if text[idx] == ".":
                prev_char = text[idx - 1 : idx]
                if prev_char.isdigit() and next_char.isdigit():
                    continue  # This is likely a decimal number

            # Found a valid boundary!
            return idx

        return -1

    @staticmethod
    def split_tts_buffer(text: str, end_index: int) -> tuple[str, str]:
        """
        Split text at end_index, keeping trailing whitespace with the left chunk.

        This ensures TTS chunks end cleanly without cutting words.

        Args:
            text: Text to split
            end_index: Index to split at (punctuation position)

        Returns:
            Tuple of (left_chunk, right_chunk)
        """
        if not text:
            return "", ""

        # Clamp end_index to valid range
        end = max(0, min(end_index, len(text)))

        # Include trailing whitespace in left chunk
        while end < len(text) and text[end].isspace():
            end += 1

        return text[:end], text[end:]

    @classmethod
    def process_streaming_text(
        cls, text_chunk: str, sentence_buffer: str
    ) -> tuple[list[str], str]:
        """
        Process a streaming text chunk and extract complete sentences.

        This is a higher-level helper that combines sanitization, boundary
        detection, and splitting for easy streaming TTS integration.

        Args:
            text_chunk: New text chunk from LLM stream
            sentence_buffer: Accumulated text from previous chunks

        Returns:
            Tuple of (complete_sentences, remaining_buffer)
        """
        # Sanitize and add to buffer
        sanitized = cls.sanitize_tts_text(text_chunk)
        sentence_buffer += sanitized

        # Extract complete sentences
        complete_sentences = []

        while True:
            # Find next sentence boundary
            boundary_idx = cls.find_tts_boundary(sentence_buffer, cls.PRIMARY_TERMS, 0)

            if boundary_idx < 0:
                # No complete sentence yet
                break

            # Split at boundary
            sentence, sentence_buffer = cls.split_tts_buffer(
                sentence_buffer, boundary_idx + 1
            )

            if sentence.strip():
                complete_sentences.append(sentence)

        return complete_sentences, sentence_buffer

    @classmethod
    def flush_buffer(cls, sentence_buffer: str) -> str | None:
        """
        Flush any remaining text in buffer (called at end of stream).

        Args:
            sentence_buffer: Accumulated text buffer

        Returns:
            Buffer contents if non-empty, None otherwise
        """
        if sentence_buffer and sentence_buffer.strip():
            return sentence_buffer
        return None
