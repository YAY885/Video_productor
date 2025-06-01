import asyncio
import os
import re
from datetime import datetime
from typing import Union, List, Dict
from xml.sax.saxutils import unescape
from pathlib import Path
import json

import edge_tts
from edge_tts import SubMaker, submaker
from loguru import logger
from moviepy.video.tools import subtitles as moviepy_subtitles

from .config_loader import get_azure_speech_key, get_azure_speech_region

# --- Utility functions (copied/adapted from voice.py) ---
def split_string_by_punctuations(s: str) -> list[str]:
    """Splits a string by common punctuations, keeping the punctuation with the preceding part."""
    if not s:
        return []
    s = re.sub(r'([,.!?。，、？！；：])\s*', r'\1<SPLIT>', s)
    parts = [part.strip() for part in s.split('<SPLIT>') if part.strip()]
    return parts

def parse_voice_name(name: str):
    name = name.replace("-Female", "").replace("-Male", "").strip()
    return name

def is_azure_v2_voice(voice_name: str):
    voice_name = parse_voice_name(voice_name)
    if voice_name.endswith("-V2"):
        return voice_name.replace("-V2", "").strip()
    return ""

def convert_rate_to_percent(rate: float) -> str:
    if rate == 1.0:
        return "+0%"
    percent = round((rate - 1.0) * 100)
    return f"+{percent}%" if percent > 0 else f"{percent}%"

async def _azure_tts_v1_async(text: str, voice_name: str, rate_str: str, voice_file: str) -> SubMaker:
    """Helper async function to perform TTS using edge-tts (using create_sub for v6.x)"""
    communicate = edge_tts.Communicate(text, voice_name, rate=rate_str)
    sub_maker = edge_tts.SubMaker()
    # No try-except here, handled by the caller loop
    with open(voice_file, "wb") as file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # Use create_sub, expected by edge-tts v6.x
                sub_maker.create_sub(
                    (chunk["offset"], chunk["duration"]), chunk["text"]
                )
    # logger.info("Audio streaming finished.") # Logging can be handled by caller
    # No need to check sub_maker.subs here, caller will do it.
    return sub_maker

def azure_tts_v1(text: str, voice_name: str, voice_rate: float, voice_file: str) -> Union[SubMaker, None]:
    voice_name = parse_voice_name(voice_name)
    text = text.strip()
    rate_str = convert_rate_to_percent(voice_rate)
    for i in range(3):
        try:
            logger.info(f"Starting Azure TTS V1 (edge-tts): voice={voice_name}, rate={rate_str}, try={i + 1}")
            sub_maker = asyncio.run(_azure_tts_v1_async(text, voice_name, rate_str, voice_file))
            if not sub_maker or not sub_maker.subs:
                logger.warning("Azure TTS V1 failed: SubMaker empty or invalid.")
                continue
            logger.info(f"Azure TTS V1 completed: {voice_file}")
            return sub_maker
        except Exception as e:
            logger.error(f"Azure TTS V1 failed on try {i+1}: {e}")
    logger.error(f"Azure TTS V1 failed after multiple retries for: {voice_file}")
    return None

def azure_tts_v2(text: str, voice_name: str, voice_file: str) -> Union[SubMaker, None]:
    voice_name_base = is_azure_v2_voice(voice_name)
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
        logger.error("Azure Speech SDK not installed. Run: pip install azure-cognitiveservices-speech")
        return None

    for i in range(3):
        try:
            logger.info(f"Starting Azure TTS V2 (SDK): voice={voice_name_base}, try={i + 1}")
            sub_maker = SubMaker()
            word_boundary_data = []
            def speech_synthesizer_word_boundary_cb(evt: speechsdk.SpeechEventArgs):
                word_boundary_data.append({
                    'offset': evt.audio_offset,
                    'duration': evt.duration.total_seconds() * 1_000_000_0,
                    'text': evt.text
                })

            speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
            speech_config.speech_synthesis_voice_name = voice_name_base
            speech_config.set_property(speechsdk.PropertyId.SpeechServiceResponse_RequestWordBoundary, "true")
            speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio48Khz192KBitRateMonoMp3)
            audio_config = speechsdk.audio.AudioOutputConfig(filename=voice_file)
            speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
            speech_synthesizer.synthesis_word_boundary.connect(speech_synthesizer_word_boundary_cb)
            result = speech_synthesizer.speak_text_async(text).get()

            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                logger.success(f"Azure V2 speech synthesis succeeded: {voice_file}")
                for word_data in word_boundary_data:
                    start_offset = word_data['offset']
                    end_offset = start_offset + word_data['duration']
                    sub_maker.create_sub((start_offset, end_offset), word_data['text'])
                if not sub_maker or not sub_maker.subs:
                    logger.warning("Azure TTS V2 succeeded but no word boundaries captured.")
                    return None
                return sub_maker
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                logger.error(f"Azure V2 speech synthesis canceled: {cancellation_details.reason}")
                if cancellation_details.reason == speechsdk.CancellationReason.Error:
                    logger.error(f"Azure V2 error details: {cancellation_details.error_details}")
            else:
                logger.error(f"Azure V2 synthesis failed with reason: {result.reason}")
        except Exception as e:
            logger.error(f"Azure TTS V2 failed on try {i+1}: {e}")
    logger.error(f"Azure TTS V2 failed after multiple retries for: {voice_file}")
    return None

def _format_text(text: str) -> str:
    text = re.sub(r'[\(\)\[\]\{\}]', ' ', text)
    text = ' '.join(text.split())
    return text.strip()

# Define the replacement timestamp formatting function
def format_time_srt(seconds: float) -> str:
    """Converts seconds to SRT time format HH:MM:SS,ms"""
    if seconds < 0: seconds = 0
    total_milliseconds = int(seconds * 1000)
    hours, remainder = divmod(total_milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds_part, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d},{milliseconds:03d}"

def get_timed_words_from_submaker(sub_maker: SubMaker) -> List[Dict[str, Union[float, str]]]:
    """
    Extracts a list of timed words (start, end in seconds) from a SubMaker object.
    Copied from utils/voice.py logic.
    """
    timed_words_list = []
    if not sub_maker or not sub_maker.subs or not sub_maker.offset:
        logger.warning("SubMaker is empty or invalid, cannot extract timed words.")
        return timed_words_list

    if len(sub_maker.subs) != len(sub_maker.offset):
        logger.warning("SubMaker subs and offset lengths do not match. Timed words may be inaccurate.")
    
    min_len = min(len(sub_maker.subs), len(sub_maker.offset))

    for i in range(min_len):
        text = unescape(sub_maker.subs[i]).strip()
        start_ns, end_ns = sub_maker.offset[i]

        start_sec = start_ns / 10_000_000.0
        end_sec = end_ns / 10_000_000.0
        
        if end_sec < start_sec:
            logger.warning(f"Word '{text}' has end time before start time. Adjusting end_sec = start_sec.")
            end_sec = start_sec

        timed_words_list.append({
            "start": round(start_sec, 3),
            "end": round(end_sec, 3),
            "text": text
        })
    return timed_words_list

def create_subtitle(sub_maker: submaker.SubMaker, text: str, subtitle_file: Path):
    if not sub_maker or not sub_maker.offset or not sub_maker.subs:
        logger.error("Cannot create subtitle: SubMaker data is invalid or empty.")
        return False # Indicate failure
    subtitle_file_str = str(subtitle_file)
    text = _format_text(text)

    def formatter(idx: int, start_time_ns: float, end_time_ns: float, sub_text: str) -> str:
        start_sec = start_time_ns / 10_000_000.0
        end_sec = end_time_ns / 10_000_000.0
        # Use the new formatting function instead of mktimestamp
        start_t = format_time_srt(start_sec)
        end_t = format_time_srt(end_sec)
        words = sub_text.split()
        lines = []
        current_line = ""
        # Simple word wrapping for SRT (approx 5 words per line)
        words_per_line_target = 5 
        for i, word in enumerate(words):
             current_line += f" {word}"
             if (i + 1) % words_per_line_target == 0 and i < len(words) - 1:
                 lines.append(current_line.strip())
                 current_line = ""
        if current_line.strip(): # Add remaining words
             lines.append(current_line.strip())
             
        formatted_text = "\n".join(l for l in lines if l)
        return f"{idx}\n{start_t} --> {end_t}\n{formatted_text}\n"

    start_time_ns = -1.0
    sub_items = []
    sub_index = 0
    current_sub_line = ""
    script_lines = split_string_by_punctuations(text)
    if not script_lines:
        logger.error("Cannot create subtitle: Could not split target text into lines.")
        return False

    word_idx = 0
    script_line_idx = 0
    processed_words = 0
    while word_idx < len(sub_maker.subs) and script_line_idx < len(script_lines):
        start_ns, end_ns = sub_maker.offset[word_idx]
        word = unescape(sub_maker.subs[word_idx]).strip()
        if not word:
            word_idx += 1
            continue
        if start_time_ns < 0:
            start_time_ns = start_ns
        current_sub_line += f" {word}"
        processed_words += 1
        ends_with_punctuation = any(word.endswith(p) for p in ",.!?。，、？！；：")
        current_script_line = script_lines[script_line_idx].strip()
        finalize_block = False
        # Condition: Match punctuation OR accumulated enough words OR last word
        if ends_with_punctuation and any(current_script_line.endswith(p) for p in ",.!?。，、？！；："):
            finalize_block = True
        elif processed_words >= 8:
            finalize_block = True
        elif word_idx == len(sub_maker.subs) - 1:
            finalize_block = True

        if finalize_block:
            aligned_text = current_script_line
            sub_index += 1
            line = formatter(sub_index, start_time_ns, end_ns, aligned_text)
            sub_items.append(line)
            start_time_ns = -1.0
            current_sub_line = ""
            script_line_idx += 1
            processed_words = 0
        word_idx += 1

    if current_sub_line.strip() and script_line_idx < len(script_lines):
        sub_index += 1
        line = formatter(sub_index, start_time_ns, sub_maker.offset[-1][1], script_lines[script_line_idx].strip())
        sub_items.append(line)
        logger.warning("Appending remaining script line due to imperfect alignment.")

    if not sub_items:
        logger.error("Failed to generate any subtitle items.")
        return False
    try:
        with open(subtitle_file_str, "w", encoding="utf-8") as file:
            file.write("\n".join(sub_items) + "\n")
        if not subtitle_file.exists() or subtitle_file.stat().st_size == 0:
            logger.error(f"Failed to write or created empty subtitle file: {subtitle_file_str}")
            return False
        try:
            sbs = moviepy_subtitles.file_to_subtitles(subtitle_file_str)
            if sbs:
                duration = max([tb for ((ta, tb), txt) in sbs])
                logger.info(f"Subtitle file created: {subtitle_file_str}, Duration: {duration:.2f}s, Lines: {len(sbs)}")
                return True # Success
            else:
                logger.warning(f"Moviepy could not parse generated SRT: {subtitle_file_str}")
                return False # Treat as failure if unparsable
        except Exception as val_e:
            logger.warning(f"Error validating SRT file {subtitle_file_str}: {val_e}")
            return False # Treat validation error as failure
    except IOError as e:
        logger.error(f"Failed to write subtitle file {subtitle_file_str}: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during subtitle writing: {e}")
        return False

def get_audio_duration(sub_maker: submaker.SubMaker) -> float:
    if not sub_maker or not sub_maker.offset:
        return 0.0
    return sub_maker.offset[-1][1] / 10_000_000.0

# --- Add the missing TTS dispatcher function ---
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
        logger.info(f"Detected V2 voice, calling azure_tts_v2 for {voice_name}")
        return azure_tts_v2(text, voice_name, voice_file_str)
    else:
        logger.info(f"Detected V1 voice, calling azure_tts_v1 for {voice_name}")
        return azure_tts_v1(text, voice_name, voice_rate, voice_file_str)
# --- End of added TTS function ---

# --- Main Function for this Module --- 
def generate_audio_fr(
    script_text: str, 
    output_audio_path: Path, 
    output_subtitle_path: Path, 
    output_captions_json_path: Path,
    voice_name: str = "fr-FR-HenriNeural-Male", # Default French voice
    voice_rate: float = 1.0
) -> bool:
    """Generates audio, an SRT subtitle file, AND a JSON file with precise word timings."""
    logger.info(f"Starting French audio generation for: {output_audio_path}")
    logger.info(f"Using voice: {voice_name}")
    
    output_audio_path.parent.mkdir(parents=True, exist_ok=True)
    output_subtitle_path.parent.mkdir(parents=True, exist_ok=True)
    output_captions_json_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Perform TTS
    sub_maker = tts(script_text, voice_name, voice_rate, output_audio_path)
    
    if not sub_maker:
        logger.error("TTS generation failed, cannot create subtitles.")
        # Clean up potentially empty audio file?
        if output_audio_path.exists() and output_audio_path.stat().st_size == 0:
             output_audio_path.unlink()
        return False
        
    # Create Subtitle File from SubMaker data
    logger.info(f"Generating SRT subtitle file: {output_subtitle_path}")
    subtitle_success = create_subtitle(sub_maker, script_text, output_subtitle_path)
    
    if not subtitle_success:
         logger.error("Subtitle file generation failed.")
         # Keep the audio file even if subtitles fail?
         return False
         
    logger.info(f"Audio file generated: {output_audio_path}")

    # Generate and save JSON with precise word timings
    json_success = False
    timed_words = get_timed_words_from_submaker(sub_maker)
    if timed_words:
        try:
            with open(output_captions_json_path, 'w', encoding='utf-8') as f:
                json.dump(timed_words, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ Timed words JSON saved to: {output_captions_json_path}")
            json_success = True
        except IOError as e:
            logger.error(f"Failed to save timed words JSON to {output_captions_json_path}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while saving timed words JSON: {e}")
    else:
        logger.warning(f"No timed words extracted from SubMaker. JSON file not saved to {output_captions_json_path}.")

    # For the function to be successful, we need the audio and the new JSON captions.
    # SRT is a bonus.
    if output_audio_path.exists() and json_success:
        logger.success("Audio and timed words JSON generation completed successfully.")
        return True
    else:
        logger.error("Audio or timed words JSON generation failed.")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    temp_dir_fr = Path("./temp_audio_fr_test")
    temp_dir_fr.mkdir(exist_ok=True)

    test_text_fr_main = "Ceci est un test principal pour le module audio français. Nous allons générer un fichier MP3 et un fichier SRT correspondants. Testons aussi les chiffres: 1, 2, 3."
    test_audio_file = temp_dir_fr / "audio_fr.mp3"
    test_subtitle_file = temp_dir_fr / "audio_fr.srt"
    test_captions_json_file = temp_dir_fr / "audio_fr_captions.json"

    print("--- Testing French Audio & Subtitle Generation --- ")
    success = generate_audio_fr(
        script_text=test_text_fr_main,
        output_audio_path=test_audio_file,
        output_subtitle_path=test_subtitle_file,
        output_captions_json_path=test_captions_json_file,
        voice_name="fr-FR-EloiseNeural-Female" # Example female voice
    )

    if success:
        print(f"Test successful. Check files in: {temp_dir_fr}")
        if test_subtitle_file.exists():
            print("--- Generated SRT --- ")
            print(test_subtitle_file.read_text(encoding='utf-8'))
            print("---------------------")
    else:
        print("Test failed.")

    # Cleanup
    # import shutil
    # shutil.rmtree(temp_dir_fr) 