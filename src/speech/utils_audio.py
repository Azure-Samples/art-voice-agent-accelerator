import wave

from utils.ml_logging import get_logger

logger = get_logger(__name__)


def check_audio_file(file_path: str) -> bool:
    """
    Checks the format of the audio stream from the provided WAV file and logs the details.
    Returns False if any of the required conditions are not met. Otherwise, returns True.

    Required conditions for the audio format:
    - PCM format (int-16, signed)
    - One channel (mono)
    - 16 bits per sample
    - 8,000 or 16,000 samples per second (16,000 bytes or 32,000 bytes per second)
    - Two-block aligned (16 bits including padding for a sample)

    Parameters:
    file_path (str): Path to the WAV file to be checked.
    """
    with wave.open(file_path, "rb") as wav_file:
        (
            n_channels,
            sampwidth,
            framerate,
            nframes,
            comptype,
            compname,
        ) = wav_file.getparams()

        # Check PCM format (int-16)
        is_pcm_format = comptype == "NONE" and sampwidth == 2
        logger.info(f"PCM Format (int-16): {is_pcm_format}")

        # Check if it's mono
        is_mono = n_channels == 1
        logger.info(f"One Channel (Mono): {is_mono}")

        # Check sample rate
        is_valid_sample_rate = framerate in [8000, 16000]
        logger.info(f"Valid Sample Rate (8000 or 16000 Hz): {is_valid_sample_rate}")

        # Calculate bytes per second
        bytes_per_second = framerate * sampwidth * n_channels
        logger.info(f"Bytes Per Second (16000 or 32000): {bytes_per_second}")

        # Check two-block alignment
        is_two_block_aligned = wav_file.getsampwidth() * n_channels == 2
        logger.info(f"Two-block Aligned: {is_two_block_aligned}")

        # Return False if any condition is not met
        return (
            is_pcm_format and is_mono and is_valid_sample_rate and is_two_block_aligned
        )


def log_audio_characteristics(file_path: str):
    """
    Logs the format of the audio stream from the provided WAV file.
    Parameters:
    file_path (str): Path to the WAV file to be checked.
    """
    with wave.open(file_path, "rb") as wav_file:
        (
            n_channels,
            sampwidth,
            framerate,
            nframes,
            comptype,
            compname,
        ) = wav_file.getparams()

        logger.info(f"Number of Channels: {n_channels}")
        logger.info(f"Sample Width: {sampwidth}")
        logger.info(f"Frame Rate: {framerate}")
        logger.info(f"Number of Frames: {nframes}")
        logger.info(f"Compression Type: {comptype}")
        logger.info(f"Compression Name: {compname}")

        # Calculate bytes per second
        bytes_per_second = framerate * sampwidth * n_channels
        logger.info(f"Bytes Per Second: {bytes_per_second}")
