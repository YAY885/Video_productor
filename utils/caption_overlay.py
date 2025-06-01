import os
from pathlib import Path
from typing import List, Dict
import json
import logging
import shutil
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from moviepy.config import change_settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configure ImageMagick if needed
try:
    # Adjust this path if necessary for your system
    change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"})
    logging.info("ImageMagick path configured (if available).")
except Exception as e:
     logging.warning(f"Could not configure ImageMagick path: {e}. Ensure ImageMagick is installed and path is correct for custom fonts/complex text.")

DEFAULT_FONT = "Arial" # Use a commonly available font as default

def load_captions(captions_path: Path) -> List[Dict]:
    """Load captions (list of timed words) from a JSON file."""
    try:
        with open(captions_path, "r", encoding='utf-8') as f:
            # Expecting format: [{ "start": float, "end": float, "text": str }]
            data = json.load(f)
            if not isinstance(data, list):
                 raise ValueError("Invalid format: captions JSON should be a list.")
            # Ensure start/end times are present and are numbers for all words
            for i, word_info in enumerate(data):
                if not all(k in word_info for k in ["start", "end", "text"]):
                    raise ValueError(f"Missing keys in word {i+1}. Expected 'start', 'end', 'text'. Got: {word_info.keys()}")
                if not isinstance(word_info["start"], (int, float)) or not isinstance(word_info["end"], (int, float)):
                    raise ValueError(f"Invalid start/end time for word {i+1} ('{word_info['text']}'). Must be numbers. Got start: {type(word_info['start'])}, end: {type(word_info['end'])}")
            return data
    except FileNotFoundError:
         logging.error(f"Captions JSON file not found: {captions_path}")
         raise
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON in captions file: {captions_path}")
        raise
    except ValueError as ve: # Catch specific ValueError from our checks
        logging.error(f"Invalid data format in captions file {captions_path}: {ve}")
        raise
    except Exception as e:
        logging.error(f"Failed to load captions from {captions_path}: {e}")
        raise RuntimeError(f"Failed to load captions: {str(e)}")

def group_words_into_captions(timed_words: List[Dict], max_words_per_caption: int = 4, max_duration_per_caption: float = 4.0) -> List[Dict]:
    """
    Group individual timed words into larger caption blocks for display.
    Combines words up to max_words_per_caption or max_duration_per_caption,
    and preferably splits at punctuation.
    """
    if not timed_words:
        return []

    grouped_captions = []
    current_group_words = []
    # Initialize current_start_time with the start of the first word.
    # last_word_end_time will also be initialized based on the first word.
    current_start_time = timed_words[0]["start"]
    last_word_end_time = timed_words[0]["end"] # Initialize to ensure it's not None

    for i, word_info in enumerate(timed_words):
        word_text = word_info["text"]
        word_start = word_info["start"]
        word_end = word_info["end"]

        # If starting a new group (current_group_words is empty), set its start time.
        if not current_group_words:
            current_start_time = word_start
            # last_word_end_time will be updated as words are added to this new group.

        # Check if adding this word exceeds limits or if it ends with punctuation
        exceeds_word_limit = len(current_group_words) >= max_words_per_caption
        
        # Ensure current_start_time is valid before subtraction
        if current_start_time is None: # Should ideally not happen with the logic above
            logging.warning("current_start_time became None unexpectedly. Resetting with current word.")
            current_start_time = word_start
            
        exceeds_duration = (word_end - current_start_time) > max_duration_per_caption
        ends_with_punctuation = any(word_text.endswith(p) for p in [".", ",", "!", "?", ";", ":"])
        is_last_word = (i == len(timed_words) - 1)

        should_finalize = False
        if current_group_words: # Only finalize if there's something in the current group
            if exceeds_word_limit or exceeds_duration or ends_with_punctuation or is_last_word:
                 should_finalize = True
        
        if should_finalize:
            # Determine if the current word should be part of the group being finalized
            # or start the next group.
            words_to_finalize = list(current_group_words) # Make a copy
            final_group_end_time = last_word_end_time

            if not (exceeds_word_limit or exceeds_duration) or is_last_word:
                # If not exceeding limits OR it's the last word of all timed_words, include current word.
                words_to_finalize.append(word_text)
                final_group_end_time = word_end
            # Else (limit exceeded before this word), the group ends *before* this word.
            # current_group_words and last_word_end_time already represent the group to finalize.
            
            grouped_captions.append({
                "start": current_start_time,
                "end": final_group_end_time, # Use the end time of the last word actually in the group
                "text": " ".join(words_to_finalize)
            })
            
            # Reset for the next group
            current_group_words = [] # Always reset words for next group
            current_start_time = None  # Will be set by the next word if it exists
            last_word_end_time = None

            # If the current word was NOT part of the finalized group (because it exceeded limits),
            # it becomes the first word of the new group.
            if not is_last_word and (exceeds_word_limit or exceeds_duration):
                current_group_words = [word_text]
                current_start_time = word_start
                last_word_end_time = word_end
        
        else: # Not finalizing yet, or current_group_words is empty
             if not current_group_words: # This is the first word of a new group (or the very first word)
                  current_start_time = word_start 
             current_group_words.append(word_text)
             last_word_end_time = word_end # Update with the end time of the last added word

    # This final check for current_group_words is usually not needed if is_last_word logic is correct,
    # but kept as a safeguard.
    if current_group_words and current_start_time is not None and last_word_end_time is not None:
        grouped_captions.append({
            "start": current_start_time,
            "end": last_word_end_time,
            "text": " ".join(current_group_words)
        })

    return grouped_captions

def add_captions_to_video(
    video_path: Path, 
    captions_path: Path, 
    output_path: Path, 
    font_size: int = 70, # Slightly smaller default?
    font_color: str = 'yellow',
    font_face: str = DEFAULT_FONT, # Use default font
    stroke_color: str = 'black',
    stroke_width: float = 2,
    position: tuple = ('center', 'center') # Default position
) -> None:
    """
    Add styled captions to the video based on grouped timed words.
    """
    try:
        video = VideoFileClip(str(video_path))
        
        # Load the timed words JSON
        timed_words = load_captions(captions_path)
        if not timed_words:
            logging.warning(f"No timed words found in {captions_path}. Skipping caption overlay.")
            # Copy original video to output path if captions can't be added
            shutil.copy(video_path, output_path)
            logging.info(f"Copied original video to {output_path} as captions could not be generated.")
            return

        # Group words into displayable captions
        grouped_captions = group_words_into_captions(timed_words)
        if not grouped_captions:
            logging.warning("Failed to group timed words into captions. Skipping overlay.")
            shutil.copy(video_path, output_path)
            logging.info(f"Copied original video to {output_path} as captions could not be grouped.")
            return

        text_clips = []
        video_width, video_height = video.size
        max_text_width = video_width * 0.8 # Max 80% of video width for text

        for caption in grouped_captions:
            start_time = caption["start"]
            end_time = caption["end"]
            text = caption["text"]
            duration = end_time - start_time
            if duration <= 0:
                logging.warning(f"Skipping caption with zero/negative duration: '{text}'")
                continue
                
            # Create the TextClip
            # MoviePy's method='caption' handles word wrapping within the specified size
            txt_clip = TextClip(
                text, # Already grouped text
                fontsize=font_size,
                color=font_color,
                font=font_face,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                size=(max_text_width, None), # Let moviepy determine height based on wrapping
                method="caption",
                align="center" # Center align wrapped text
            ).set_position(position) \
             .set_start(start_time) \
             .set_duration(duration)
             # .set_end(end_time) # Setting duration is usually preferred
             
            text_clips.append(txt_clip)

        if not text_clips:
             logging.warning("No valid TextClips created. Skipping overlay.")
             shutil.copy(video_path, output_path)
             logging.info(f"Copied original video to {output_path} as no captions clips were created.")
             return
             
        # Composite the video with text clips
        final_video = CompositeVideoClip([video] + text_clips)

        # Write the final video
        logging.info(f"Writing final video with captions to: {output_path}...")
        final_video.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            threads=os.cpu_count() or 2,
            logger="bar"
        )
        
        # Cleanup
        try: 
            video.close()
            final_video.close()
            for tc in text_clips: tc.close()
        except Exception as close_e:
             logging.warning(f"Error during caption overlay cleanup: {close_e}")

        logging.info(f"✅ Video with captions saved to: {output_path}")

    except FileNotFoundError as fnf_e:
        logging.error(f"File not found during caption overlay: {fnf_e}")
        raise # Re-raise to stop the pipeline
    except Exception as e:
        logging.error(f"Failed to add captions to video: {e}", exc_info=True)
        # Should we copy the original video here too?
        try:
            shutil.copy(video_path, output_path)
            logging.warning(f"Copied original video to {output_path} due to caption overlay error.")
        except Exception as copy_e:
            logging.error(f"Failed to copy original video after caption error: {copy_e}")
        raise RuntimeError(f"Failed to add captions to video: {str(e)}")

def main(video_path: Path, captions_path: Path, output_path: Path) -> None:
    """
    Main function to add captions to a video.
    """
    try:
        if not video_path.exists():
            raise FileNotFoundError(f"Input video file not found: {video_path}")
        if not captions_path.exists():
            raise FileNotFoundError(f"Captions JSON file not found: {captions_path}")

        print("\n📝 Adding captions to video...")
        add_captions_to_video(video_path, captions_path, output_path)

    except Exception as e:
        print(f"❌ Error in caption overlay main function: {str(e)}")

# Keep this block if you want to test this module independently
# if __name__ == '__main__':
#     # Example usage for testing
#     logging.basicConfig(level=logging.INFO)
#     test_video = Path("./test_composer_project/output/final_video_no_captions.mp4") # Adjust path
#     test_captions = Path("./test_composer_project/captions/captions.json") # Adjust path
#     test_output = Path("./test_composer_project/output/final_video_WITH_CAPTIONS_test.mp4")
#     if test_video.exists() and test_captions.exists():
#         main(test_video, test_captions, test_output)
#     else:
#         print("Skipping caption_overlay test: Input video or captions file missing.") 