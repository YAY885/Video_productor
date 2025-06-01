import logging
from pathlib import Path
from .google_api import analyze_video # Import from the local google_api module

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_hook_description(video_path: str, request_timeout: int = 600) -> str | None:
    """
    Analyzes the hook video using Gemini or loads from a local cache 
    and returns its description.
    The description is cached in a .txt file with the same name as the video
    in the same directory.
    """
    video_file = Path(video_path)
    if not video_file.is_file():
        logging.error(f"Hook video file not found: {video_path}")
        return None

    # Define the path for the cached description file
    description_cache_file = video_file.with_suffix('.txt')

    # 1. Try to load from cache
    if description_cache_file.is_file():
        try:
            description = description_cache_file.read_text(encoding='utf-8')
            if description.strip(): # Ensure content is not just whitespace
                logging.info(f"Loaded hook description from cache: {description_cache_file}")
                return description.strip()
            else:
                logging.warning(f"Cached description file {description_cache_file} is empty. Will re-analyze.")
        except Exception as e:
            logging.warning(f"Could not read cached description file {description_cache_file}: {e}. Will re-analyze.")

    # 2. If not in cache or cache read failed, analyze video
    prompt = (
        "Analyze this video intended as a hook for a TikTok video. "
        "Describe the key visual elements, actions, and overall mood in a concise sentence or two. "
        "Focus on what makes it potentially engaging."
    )

    try:
        logging.info(f"Analyzing hook video (cache not found or invalid): {video_path}...")
        description = analyze_video(prompt, video_path, request_timeout=request_timeout)
        
        if description:
            logging.info("Hook video analysis successful.")
            # 3. Save to cache for next time
            try:
                description_cache_file.write_text(description, encoding='utf-8')
                logging.info(f"Saved hook description to cache: {description_cache_file}")
            except Exception as e:
                logging.warning(f"Failed to save hook description to cache {description_cache_file}: {e}")
            return description
        else:
            logging.warning("Hook video analysis returned no description (possibly blocked or empty).")
            return None
    except Exception as e:
        logging.error(f"Error during hook video analysis ({video_path}): {e}")
        return None

if __name__ == '__main__':
    # Example Usage - Replace with a real video path for testing
    sample_hook_video = "path/to/your/hook_video.mp4" # <<< REMPLACEZ CECI
    
    print(f"--- Testing Video Analyzer ({sample_hook_video}) ---")
    if Path(sample_hook_video).exists():
        desc = get_hook_description(sample_hook_video, request_timeout=720) # 12 min timeout
        if desc:
            print("\nAnalysis Result:")
            print(desc)
        else:
            print("\nVideo analysis failed or returned empty.")
    else:
        print(f"\nSkipping test: Sample hook video not found at {sample_hook_video}")
    print("--- End Test --- ") 