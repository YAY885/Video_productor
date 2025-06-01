import os
import json
import re
import logging
from pathlib import Path
from typing import List, Dict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Remove whisper dependency
# import whisper
# import subprocess 

# def check_ffmpeg_installed() -> bool:
#     try:
#         result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
#         logging.info("ffmpeg found.")
#         return True
#     except (FileNotFoundError, subprocess.CalledProcessError) as e:
#         logging.error(f"ffmpeg not found or ffmpeg command failed: {e}")
#         logging.error("Please install ffmpeg and ensure it's in your system's PATH.")
#         return False

def parse_srt_time(time_str: str) -> float:
    """Converts SRT time format (HH:MM:SS,ms) to seconds."""
    try:
        parts = time_str.split(',')
        h, m, s = map(int, parts[0].split(':'))
        ms = int(parts[1])
        return h * 3600 + m * 60 + s + ms / 1000.0
    except Exception as e:
        logging.warning(f"Could not parse SRT time '{time_str}': {e}")
        return 0.0

def convert_srt_to_timed_words(
    srt_path: Path, 
    output_json_path: Path
) -> bool:
    """Reads an SRT file and converts it into a JSON list of words with approximate timestamps.

    Args:
        srt_path: Path to the input SRT file.
        output_json_path: Path to save the output JSON file.

    Returns:
        True if successful, False otherwise.
    """
    if not srt_path.is_file():
        logging.error(f"SRT file not found: {srt_path}")
        return False

    timed_words = []
    try:
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Regex to find index, timestamp line, and text blocks
        # Handles multi-line text blocks
        pattern = re.compile(r"(\d+)\s*\n([\d:,]+)\s*-->\s*([\d:,]+)\s*\n((?:.+\n?)+)", re.MULTILINE)
        matches = pattern.findall(content)

        if not matches:
            logging.error(f"Could not find valid subtitle blocks in {srt_path}")
            return False

        for index, start_str, end_str, text_block in matches:
            start_time = parse_srt_time(start_str)
            end_time = parse_srt_time(end_str)
            duration = end_time - start_time
            if duration <= 0:
                 logging.warning(f"Skipping block {index} due to zero or negative duration.")
                 continue
                 
            # Clean and split text block into words
            text = ' '.join(text_block.strip().splitlines()).strip()
            words = text.split()
            if not words:
                 continue
                 
            num_words = len(words)
            # Distribute duration approximately based on number of words
            # This is a simplification! Assumes equal time per word.
            time_per_word = duration / num_words 
            
            current_word_start_time = start_time
            for i, word in enumerate(words):
                 # Clean the word itself (remove trailing punctuation for matching? maybe not needed here)
                 cleaned_word = word # Keep punctuation for display
                 
                 word_end_time = current_word_start_time + time_per_word
                 # Ensure end time doesn't exceed block end time (especially for last word)
                 word_end_time = min(word_end_time, end_time)
                 
                 timed_words.append({
                     "start": round(current_word_start_time, 3),
                     "end": round(word_end_time, 3),
                     "text": cleaned_word
                 })
                 current_word_start_time = word_end_time # Start of next word is end of current

    except Exception as e:
        logging.error(f"Error processing SRT file {srt_path}: {e}")
        return False

    # Save the result to JSON
    try:
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(timed_words, f, indent=2, ensure_ascii=False)
        logging.info(f"✅ Timed words JSON saved to: {output_json_path}")
        return True
    except IOError as e:
        logging.error(f"Failed to save timed words JSON to {output_json_path}: {e}")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred while saving timed words JSON: {e}")
        return False


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Create a dummy SRT file for testing
    dummy_srt_content = """
1
00:00:01,500 --> 00:00:04,000
Bonjour tout le monde.
Ceci est un test.

2
00:00:04,500 --> 00:00:07,800
J'espère que ça fonctionne bien!
Point final.

3
00:00:08,000 --> 00:00:09,000
Test: 1, 2, 3.
"""
    dummy_srt_path = Path("dummy_test.srt")
    dummy_json_path = Path("dummy_test_captions.json")
    
    try:
        with open(dummy_srt_path, "w", encoding='utf-8') as f:
            f.write(dummy_srt_content)
        print(f"Created dummy SRT file: {dummy_srt_path}")
        
        print("\n--- Testing SRT to Timed Words Conversion ---")
        success = convert_srt_to_timed_words(dummy_srt_path, dummy_json_path)
        
        if success and dummy_json_path.exists():
            print(f"Conversion successful. Output JSON: {dummy_json_path}")
            # Print the JSON content
            # with open(dummy_json_path, 'r', encoding='utf-8') as f:
            #     print(f.read())
        else:
            print("Conversion failed.")
            
    except Exception as e:
        print(f"An error occurred during testing: {e}")
    finally:
        # Clean up dummy files
        if dummy_srt_path.exists():
            os.remove(dummy_srt_path)
        if dummy_json_path.exists():
             os.remove(dummy_json_path)
        print("\nCleaned up dummy files.")

    print("--- End Test --- ") 