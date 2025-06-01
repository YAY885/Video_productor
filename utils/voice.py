import asyncio
import os
import re
from datetime import datetime
from typing import Union, List, Dict
from xml.sax.saxutils import unescape
from pathlib import Path # Use Path for paths

import edge_tts
from edge_tts import SubMaker, submaker
from edge_tts.submaker import mktimestamp
from loguru import logger
from moviepy.video.tools import subtitles as moviepy_subtitles # Alias to avoid conflict

# Import the new config loader
from .config_loader import get_azure_speech_key, get_azure_speech_region

# Remove direct config dependency
# from app.config import config

# Remove app.utils dependency - reimplement or remove functions needed
# from app.utils import utils 

# Basic utility function replacement (if needed)
def split_string_by_punctuations(s: str) -> list[str]:
    """Splits a string by common punctuations, keeping the punctuation with the preceding part."""
    if not s:
        return []
    # Enhanced regex to handle various punctuation and keep them temporarily marked
    s = re.sub(r'([,.!?。，、？！；：])\s*', r'\1<SPLIT>', s)
    parts = [part.strip() for part in s.split('<SPLIT>') if part.strip()]
    return parts

# --- Azure Voices (Keep as is, no config dependency) --- 
def get_all_azure_voices(filter_locals=None) -> list[str]:
    # ... (existing code for voices_str and parsing)
    if filter_locals is None:
        filter_locals = ["fr-FR", "en-US", "es-ES"] # Defaulting to FR/EN/ES
    voices_str = """ 
    Name: af-ZA-AdriNeural
    Gender: Female

    Name: af-ZA-WillemNeural
    # ... (rest of the voice list) ...
    Name: zu-ZA-ThembaNeural
    Gender: Male
    """
    # ... (rest of the parsing logic)
    voices = []
    pattern = re.compile(r"Name:\s*(.+)\s*Gender:\s*(.+)\s*", re.MULTILINE)
    matches = pattern.findall(voices_str)
    for name, gender in matches:
        if filter_locals and any(
            name.lower().startswith(fl.lower()) for fl in filter_locals
        ):
            voices.append(f"{name}-{gender}")
        elif not filter_locals:
            voices.append(f"{name}-{gender}")
    voices.sort()
    return voices
    
def parse_voice_name(name: str):
    # ... (existing code)
    name = name.replace("-Female", "").replace("-Male", "").strip()
    return name

def is_azure_v2_voice(voice_name: str):
    # ... (existing code)
    voice_name = parse_voice_name(voice_name)
    if voice_name.endswith("-V2"):
        return voice_name.replace("-V2", "").strip()
    return ""
# --- End Azure Voices ---


def tts(
    text: str, 
    voice_name: str, 
    voice_rate: float, # Rate for v1 only
    voice_file: Path # Expect Path object
) -> Union[SubMaker, None]:
    """Generates TTS audio using Azure V1 (edge-tts) or V2 (SDK)."""
    voice_file_str = str(voice_file)
    if is_azure_v2_voice(voice_name):
        # V2 doesn't use rate parameter in this implementation
        return azure_tts_v2(text, voice_name, voice_file_str) 
    return azure_tts_v1(text, voice_name, voice_rate, voice_file_str)


def convert_rate_to_percent(rate: float) -> str:
    # ... (existing code)
    if rate == 1.0:
        return "+0%"
    percent = round((rate - 1.0) * 100)
    if percent > 0:
        return f"+{percent}%"
    else:
        return f"{percent}%"

async def _azure_tts_v1_async(
    text: str, voice_name: str, rate_str: str, voice_file: str
) -> SubMaker:
    """Async helper for edge-tts V1 generation."""
    communicate = edge_tts.Communicate(text, voice_name, rate=rate_str)
    sub_maker = edge_tts.SubMaker()
    with open(voice_file, "wb") as file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                sub_maker.create_sub(
                    (chunk["offset"], chunk["duration"]), chunk["text"]
                )
    return sub_maker

def azure_tts_v1(
    text: str, voice_name: str, voice_rate: float, voice_file: str
) -> Union[SubMaker, None]:
    voice_name = parse_voice_name(voice_name)
    text = text.strip()
    rate_str = convert_rate_to_percent(voice_rate)
    for i in range(3): # Retry logic
        try:
            logger.info(f"Starting Azure TTS V1 (edge-tts): voice={voice_name}, rate={rate_str}, try={i + 1}")
            
            sub_maker = asyncio.run(_azure_tts_v1_async(text, voice_name, rate_str, voice_file))

            if not sub_maker or not sub_maker.subs:
                logger.warning("Azure TTS V1 failed: SubMaker empty or invalid.")
                # Optional: Add a small delay before retrying
                # asyncio.run(asyncio.sleep(1))
                continue

            logger.info(f"Azure TTS V1 completed: {voice_file}")
            return sub_maker
        except Exception as e:
            logger.error(f"Azure TTS V1 failed on try {i+1}: {e}")
            # Optional: Add a small delay before retrying
            # asyncio.run(asyncio.sleep(1))
            
    logger.error(f"Azure TTS V1 failed after multiple retries for: {voice_file}")
    return None


def azure_tts_v2(text: str, voice_name: str, voice_file: str) -> Union[SubMaker, None]:
    voice_name_base = is_azure_v2_voice(voice_name) # Get base name like zh-CN-XiaoxiaoMultilingualNeural
    if not voice_name_base:
        msg = f"Invalid Azure V2 voice name format: {voice_name}"
        logger.error(msg)
        raise ValueError(msg)
        
    text = text.strip()

    speech_key = get_azure_speech_key()
    service_region = get_azure_speech_region()

    if not speech_key or not service_region:
        logger.error("Azure Speech Key or Region not configured in my_config.json")
        return None

    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError:
        logger.error("Azure Speech SDK not installed. Please install with: pip install azure-cognitiveservices-speech")
        return None

    def _format_duration_to_offset(duration) -> int:
        # ... (existing code)
        if isinstance(duration, str):
            try:
                 time_obj = datetime.strptime(duration, "%H:%M:%S.%f")
                 milliseconds = (
                    (time_obj.hour * 3600000)
                    + (time_obj.minute * 60000)
                    + (time_obj.second * 1000)
                    + (time_obj.microsecond // 1000)
                 )
                 return milliseconds * 10000 # Convert ms to 100ns ticks
            except ValueError:
                 logger.warning(f"Could not parse duration string: {duration}")
                 return 0
        elif isinstance(duration, int):
             return duration # Assume it's already in 100ns ticks if int
        return 0

    for i in range(3): # Retry logic
        try:
            logger.info(f"Starting Azure TTS V2 (SDK): voice={voice_name_base}, try={i + 1}")
            sub_maker = SubMaker() # Reset sub_maker for each retry
            word_boundary_data = [] # Store word boundary events temporarily

            def speech_synthesizer_word_boundary_cb(evt: speechsdk.SpeechEventArgs):
                # Store event data instead of directly modifying sub_maker here
                word_boundary_data.append({
                    'offset': evt.audio_offset, # Already in 100ns ticks
                    'duration': evt.duration.total_seconds() * 1_000_000_0, # Convert timedelta to 100ns ticks
                    'text': evt.text
                })

            speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
            # Use the original full voice name (including -V2-Gender) for configuration if needed by SDK
            # Let's stick to the base name as per typical usage examples
            speech_config.speech_synthesis_voice_name = voice_name_base 
            speech_config.set_property(
                property_id=speechsdk.PropertyId.SpeechServiceResponse_RequestWordBoundary,
                value="true",
            )
            # High quality MP3 format
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Audio48Khz192KBitRateMonoMp3
            )

            # Configure audio output
            audio_config = speechsdk.audio.AudioOutputConfig(filename=voice_file)

            speech_synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=speech_config, audio_config=audio_config
            )
            
            # Connect the event handler
            speech_synthesizer.synthesis_word_boundary.connect(speech_synthesizer_word_boundary_cb)

            # Synthesize the text
            result = speech_synthesizer.speak_text_async(text).get()

            # Check the result
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                logger.success(f"Azure V2 speech synthesis succeeded: {voice_file}")
                # Process stored word boundary data *after* synthesis is complete
                for word_data in word_boundary_data:
                    start_offset = word_data['offset']
                    end_offset = start_offset + word_data['duration']
                    sub_maker.create_sub((start_offset, end_offset), word_data['text'])
                    
                if not sub_maker or not sub_maker.subs:
                     logger.warning("Azure TTS V2 succeeded but no word boundaries captured.")
                     # Still return None or an empty SubMaker?
                     # Let's return None as subtitles won't work.
                     return None 
                return sub_maker 
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                logger.error(f"Azure V2 speech synthesis canceled: {cancellation_details.reason}")
                if cancellation_details.reason == speechsdk.CancellationReason.Error:
                    logger.error(f"Azure V2 error details: {cancellation_details.error_details}")
                # Retry if possible
            else:
                logger.error(f"Azure V2 synthesis failed with unexpected reason: {result.reason}")
                
        except Exception as e:
            logger.error(f"Azure TTS V2 failed on try {i+1}: {e}")
            # Optional delay
            # asyncio.run(asyncio.sleep(1))
            
    logger.error(f"Azure TTS V2 failed after multiple retries for: {voice_file}")
    return None

def _format_text(text: str) -> str:
    # ... (existing code)
    text = re.sub(r'[\(\)\[\]\{\}]', ' ', text) # Remove brackets
    text = ' '.join(text.split()) # Normalize whitespace
    return text.strip()


def create_subtitle(sub_maker: submaker.SubMaker, text: str, subtitle_file: Path):
    """
    Generates an SRT subtitle file from SubMaker data, aligning with text segments.
    Expects subtitle_file as a Path object.
    """
    if not sub_maker or not sub_maker.offset or not sub_maker.subs:
        logger.error("Cannot create subtitle: SubMaker data is invalid or empty.")
        return
        
    subtitle_file_str = str(subtitle_file)
    text = _format_text(text)

    def formatter(idx: int, start_time: float, end_time: float, sub_text: str) -> str:
        # Convert 100ns ticks to seconds for mktimestamp
        start_sec = start_time / 10_000_000.0
        end_sec = end_time / 10_000_000.0
        start_t = mktimestamp(start_sec).replace(".", ",")
        end_t = mktimestamp(end_sec).replace(".", ",")
        # Max 2 lines per subtitle block seems reasonable for TikTok
        words = sub_text.split()
        lines = []
        current_line = ""
        for i, word in enumerate(words):
             if i > 0 and i % 5 == 0: # Break roughly every 5 words
                 lines.append(current_line.strip())
                 current_line = word
             else:
                 current_line += f" {word}"
        lines.append(current_line.strip()) # Add the last line
        formatted_text = "\n".join(l for l in lines if l)
        
        return f"{idx}\n{start_t} --> {end_t}\n{formatted_text}\n"

    start_time_ns = -1.0
    sub_items = []
    sub_index = 0
    current_sub_line = ""

    # Split target script text into manageable lines/phrases
    script_lines = split_string_by_punctuations(text)
    if not script_lines:
         logger.error("Cannot create subtitle: Could not split target text into lines.")
         return

    # --- Alignment Logic --- 
    # This part is complex. A simpler approach for now:
    # Group SubMaker words until the next punctuation roughly matches script_lines
    # This avoids complex similarity matching for speed.

    word_idx = 0
    script_line_idx = 0
    processed_words = 0
    
    while word_idx < len(sub_maker.subs) and script_line_idx < len(script_lines):
        start_ns, end_ns = sub_maker.offset[word_idx]
        word = unescape(sub_maker.subs[word_idx]).strip()
        
        if not word: # Skip empty words if any
             word_idx += 1
             continue
             
        if start_time_ns < 0:
            start_time_ns = start_ns

        current_sub_line += f" {word}"
        processed_words += 1
        
        # Check if current word ends with punctuation similar to script line end
        # Or if we have accumulated a reasonable number of words for the line
        ends_with_punctuation = any(word.endswith(p) for p in ",.!?。，、？！；：")
        current_script_line = script_lines[script_line_idx].strip()
        
        # Condition to finalize a subtitle block
        # 1. Match punctuation at end? (approximate) 
        # 2. Accumulated enough words? (e.g., > 7 words) 
        # 3. Reached end of SubMaker words? 
        finalize_block = False
        if ends_with_punctuation and any(current_script_line.endswith(p) for p in ",.!?。，、？！；：") :
             # Simple punctuation check - might need improvement
             finalize_block = True 
        elif processed_words >= 8: # Arbitrary word limit per block
             finalize_block = True
        elif word_idx == len(sub_maker.subs) - 1: # Last word
             finalize_block = True
             
        if finalize_block:
            # Use the corresponding script line text for better accuracy
            aligned_text = current_script_line
            sub_index += 1
            line = formatter(
                idx=sub_index,
                start_time=start_time_ns,
                end_time=end_ns, # Use the end time of the last word in the block
                sub_text=aligned_text,
            )
            sub_items.append(line)
            
            # Reset for next block
            start_time_ns = -1.0
            current_sub_line = ""
            script_line_idx += 1
            processed_words = 0
            
        word_idx += 1
        
    # Handle any remaining words or script lines if alignment wasn't perfect
    if current_sub_line.strip() and script_line_idx < len(script_lines):
         sub_index += 1
         line = formatter(
                idx=sub_index,
                start_time=start_time_ns,
                end_time=sub_maker.offset[-1][1], # Use last word's end time
                sub_text=script_lines[script_line_idx].strip(),
            )
         sub_items.append(line)
         logger.warning("Appending remaining script line due to imperfect alignment.")

    if not sub_items:
         logger.error("Failed to generate any subtitle items.")
         return
         
    # Write the final SRT file
    try:
        with open(subtitle_file_str, "w", encoding="utf-8") as file:
            file.write("\n".join(sub_items) + "\n")
            
        # Verify the created file
        if not subtitle_file.exists() or subtitle_file.stat().st_size == 0:
             logger.error(f"Failed to write or created empty subtitle file: {subtitle_file_str}")
             return
             
        # Optional: Use moviepy to validate SRT format
        try:
            sbs = moviepy_subtitles.file_to_subtitles(subtitle_file_str, encoding="utf-8")
            if sbs:
                duration = max([tb for ((ta, tb), txt) in sbs])
                logger.info(f"Subtitle file created: {subtitle_file_str}, Duration: {duration:.2f}s, Lines: {len(sbs)}")
            else:
                logger.warning(f"Moviepy could not parse generated SRT: {subtitle_file_str}")
        except Exception as val_e:
            logger.warning(f"Error validating SRT file {subtitle_file_str} with moviepy: {val_e}")

    except IOError as e:
        logger.error(f"Failed to write subtitle file {subtitle_file_str}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during subtitle writing: {e}")


def get_audio_duration(sub_maker: submaker.SubMaker) -> float:
    """Gets the audio duration in seconds from SubMaker data."""
    if not sub_maker or not sub_maker.offset:
        return 0.0
    # Last offset's end time is in 100ns ticks
    return sub_maker.offset[-1][1] / 10_000_000.0

def get_timed_words_from_submaker(sub_maker: SubMaker) -> List[Dict[str, Union[float, str]]]:
    """
    Extracts a list of timed words (start, end in seconds) from a SubMaker object.
    """
    timed_words_list = []
    if not sub_maker or not sub_maker.subs or not sub_maker.offset:
        logger.warning("SubMaker is empty or invalid, cannot extract timed words.")
        return timed_words_list

    if len(sub_maker.subs) != len(sub_maker.offset):
        logger.warning("SubMaker subs and offset lengths do not match. Timed words may be inaccurate.")
        # Proceeding with the shorter length to avoid IndexError
    
    min_len = min(len(sub_maker.subs), len(sub_maker.offset))

    for i in range(min_len):
        text = unescape(sub_maker.subs[i]).strip()
        start_ns, end_ns = sub_maker.offset[i] # These are (start_time_100ns, end_time_100ns)

        # Convert 100ns ticks to seconds
        start_sec = start_ns / 10_000_000.0
        end_sec = end_ns / 10_000_000.0
        
        # Ensure end_sec is not before start_sec (can happen with very short words or edge cases)
        if end_sec < start_sec:
            logger.warning(f"Word '{text}' has end time before start time. Adjusting end_sec = start_sec.")
            end_sec = start_sec

        timed_words_list.append({
            "start": round(start_sec, 3),
            "end": round(end_sec, 3),
            "text": text
        })
    return timed_words_list

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Setup a temporary directory for testing
    temp_dir = Path("./temp_tts_test")
    temp_dir.mkdir(exist_ok=True)
    
    test_voice_v1 = "fr-FR-EloiseNeural-Female"  # Example French V1 voice
    test_voice_v2 = "fr-FR-VivienneMultilingualNeural-V2-Female" # Example French V2 voice
    test_text_fr = "Bonjour tout le monde. Ceci est un test de la synthèse vocale en français. J'espère que ça fonctionne bien! Point final."
    
    print(f"--- Testing Azure TTS V1 ({test_voice_v1}) ---")
    voice_file_v1 = temp_dir / "test_v1.mp3"
    subtitle_file_v1 = temp_dir / "test_v1.srt"
    sub_maker_v1 = tts(test_text_fr, test_voice_v1, 1.0, voice_file_v1)
    if sub_maker_v1:
        print(f"Audio duration (V1): {get_audio_duration(sub_maker_v1):.2f}s")
        create_subtitle(sub_maker_v1, test_text_fr, subtitle_file_v1)
        if subtitle_file_v1.exists():
             print(f"Subtitle V1 created: {subtitle_file_v1}")
             # print(subtitle_file_v1.read_text(encoding='utf-8'))
        else:
             print("Subtitle V1 creation failed.")
    else:
        print("TTS V1 generation failed.")

    print(f"\n--- Testing Azure TTS V2 ({test_voice_v2}) ---")
    # Ensure Azure keys are in my_config.json for this test
    try:
        voice_file_v2 = temp_dir / "test_v2.mp3"
        subtitle_file_v2 = temp_dir / "test_v2.srt"
        sub_maker_v2 = tts(test_text_fr, test_voice_v2, 1.0, voice_file_v2) # Rate ignored for V2
        if sub_maker_v2:
            print(f"Audio duration (V2): {get_audio_duration(sub_maker_v2):.2f}s")
            create_subtitle(sub_maker_v2, test_text_fr, subtitle_file_v2)
            if subtitle_file_v2.exists():
                 print(f"Subtitle V2 created: {subtitle_file_v2}")
                 # print(subtitle_file_v2.read_text(encoding='utf-8'))
            else:
                 print("Subtitle V2 creation failed.")
        else:
            print("TTS V2 generation failed (check Azure keys/SDK installation).")
    except ValueError as ve:
         print(f"Value Error during V2 test (likely config issue): {ve}")
    except Exception as e:
         print(f"Unexpected error during V2 test: {e}")
         
    # print(f"\nCleanup: Consider deleting {temp_dir}")
    # import shutil
    # shutil.rmtree(temp_dir) 