import os
import random
import hashlib # For MD5 hashing
import json # Needed for loading script_data in __main__
from typing import List, Dict, Any # Use Dict instead of MaterialInfo for simplicity
from urllib.parse import urlencode
from pathlib import Path
import re

import requests
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip

# Import the new config loader
from .config_loader import get_pexels_api_key, get_pixabay_api_key, get_config
from .script_generator_gemini import generate_text

# Define TikTok aspect ratio directly
TIKTOK_ASPECT = (1080, 1920) # width, height

# Remove MaterialInfo dependency and related schema imports
# from app.models.schema import MaterialInfo, VideoAspect, VideoConcatMode

# Remove app.utils dependency - reimplement md5 or import hashlib
# from app.utils import utils

# --- Rotation des clés API ---
_pexels_key_index = 0
_pixabay_key_index = 0

def get_rotating_api_key(api_keys: list, key_type: str = "pexels"):
    global _pexels_key_index, _pixabay_key_index
    if not api_keys:
        raise ValueError("Aucune clé API fournie.")
    if isinstance(api_keys, str):
        return api_keys
    if key_type == "pexels":
        idx = _pexels_key_index
        _pexels_key_index = (idx + 1) % len(api_keys)
        return api_keys[idx]
    elif key_type == "pixabay":
        idx = _pixabay_key_index
        _pixabay_key_index = (idx + 1) % len(api_keys)
        return api_keys[idx]
    else:
        return api_keys[0]

def md5(text: str) -> str:
    """Calculate the MD5 hash of a string."""
    return hashlib.md5(text.encode('utf-8')).hexdigest()

# Remove old get_api_key
# requested_count = 0
# def get_api_key(cfg_key: str):
# ...

def search_videos_pexels(
    search_term: str,
    minimum_duration: int,
) -> List[Dict]:
    video_width, video_height = TIKTOK_ASPECT
    api_keys = get_config("pexels_api_keys") or get_pexels_api_key()
    api_key = get_rotating_api_key(api_keys, key_type="pexels")
    headers = {
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0",
    }
    params = {"query": search_term, "per_page": 10, "orientation": "portrait"}
    query_url = f"https://api.pexels.com/videos/search?{urlencode(params)}"
    proxy_config = get_config("proxy")
    logger.debug(f"Searching Pexels videos: {query_url}, with proxies: {proxy_config}")
    try:
        r = requests.get(query_url, headers=headers, proxies=proxy_config, timeout=(30, 60))
        r.raise_for_status()
        response = r.json()
        video_items = []
        if "videos" not in response:
            logger.warning(f"Pexels: pas de vidéos pour {search_term}")
            return video_items
        videos = response["videos"]
        for v in videos:
            duration = v.get("duration", 0)
            if duration < minimum_duration:
                continue
            video_files = v.get("video_files", [])
            found_link = None
            best_area = 0
            for video in video_files:
                w = video.get("width")
                h = video.get("height")
                link = video.get("link")
                if w is None or h is None or link is None:
                    logger.warning(f"Vidéo incomplète ignorée: {video}")
                    continue
                if h > w:
                    if w == video_width and h == video_height:
                        found_link = link
                        break
                    area = w * h
                    if area > best_area:
                        found_link = link
                        best_area = area
            if found_link:
                item = {
                    "provider": "pexels",
                    "url": found_link,
                    "duration": duration
                }
                video_items.append(item)
        logger.info(f"Pexels search for '{search_term}' returned {len(video_items)} portrait videos.")
        return video_items
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur réseau Pexels: {e}")
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"Erreur parsing Pexels: {e}")
    except Exception as e:
        logger.error(f"Erreur inattendue Pexels: {e}")
    return []


def search_videos_pixabay(
    search_term: str,
    minimum_duration: int,
) -> List[Dict]:
    video_width, video_height = TIKTOK_ASPECT
    api_keys = get_config("pixabay_api_keys") or get_pixabay_api_key()
    api_key = get_rotating_api_key(api_keys, key_type="pixabay")
    params = {
        "q": search_term,
        "video_type": "film",
        "orientation": "vertical",
        "per_page": 20,
        "key": api_key,
    }
    query_url = f"https://pixabay.com/api/videos/?{urlencode(params)}"
    proxy_config = get_config("proxy")
    logger.debug(f"Searching Pixabay videos: {query_url}, with proxies: {proxy_config}")
    try:
        r = requests.get(query_url, proxies=proxy_config, timeout=(30, 60))
        r.raise_for_status()
        response = r.json()
        video_items = []
        if "hits" not in response:
            logger.warning(f"Pixabay: pas de vidéos pour {search_term}")
            return video_items
        videos = response["hits"]
        for v in videos:
            duration = v.get("duration", 0)
            if duration < minimum_duration:
                continue
            w = v.get("width", 0)
            h = v.get("height", 0)
            if h > w:
                video_data = v.get("videos", {}).get("large") or v.get("videos", {}).get("medium")
                if video_data and video_data.get("url"):
                    item = {
                        "provider": "pixabay",
                        "url": video_data["url"],
                        "duration": duration,
                        "width": video_data.get("width"),
                        "height": video_data.get("height")
                    }
                    video_items.append(item)
        logger.info(f"Pixabay search for '{search_term}' returned {len(video_items)} portrait videos.")
        return video_items
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur réseau Pixabay: {e}")
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"Erreur parsing Pixabay: {e}")
    except Exception as e:
        logger.error(f"Erreur inattendue Pixabay: {e}")
    return []


def save_video(video_url: str, save_dir: Path) -> str:
    """Downloads and saves a video, returning the path or empty string on failure."""
    if not video_url:
        return ""

    save_dir.mkdir(parents=True, exist_ok=True)

    try:
        url_without_query = video_url.split("?")[0]
        url_hash = md5(url_without_query)
        # Include provider in hash/ID to avoid potential collisions if URL is somehow identical
        provider = "generic"
        if "pexels.com" in video_url: provider = "pexels"
        elif "pixabay.com" in video_url: provider = "pixabay"
        video_id = f"vid-{provider}-{url_hash}" 
        video_path = save_dir / f"{video_id}.mp4"

        if video_path.exists() and video_path.stat().st_size > 1024: # Check for non-trivial size
            logger.info(f"Video already exists: {video_path}")
            # Quick verification if possible without full load
            # For now, assume existing file is okay if size > 1KB
            return str(video_path)

        headers = {"User-Agent": "Mozilla/5.0"}
        proxy_config = get_config("proxy")

        logger.info(f"Downloading video: {video_url} to {video_path}")
        with requests.get(video_url, headers=headers, proxies=proxy_config, stream=True, timeout=(60, 300)) as r: # Increased download timeout
            r.raise_for_status()
            with open(video_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        if video_path.exists() and video_path.stat().st_size > 1024:
            # Verify the downloaded video is valid using moviepy (optional, can be slow)
            # try:
            #     with VideoFileClip(str(video_path)) as clip:
            #         duration = clip.duration
            #         fps = clip.fps
            #     if duration > 0 and fps > 0:
            #         logger.info(f"Video downloaded and verified: {video_path}")
            #         return str(video_path)
            #     else:
            #         logger.warning(f"Downloaded video is invalid (duration/fps=0): {video_path}")
            #         video_path.unlink(missing_ok=True)
            #         return ""
            # except Exception as e:
            #     logger.warning(f"Failed to verify video file with moviepy: {video_path} => {e}")
            #     video_path.unlink(missing_ok=True)
            #     return ""
            logger.info(f"Video downloaded successfully: {video_path}")
            return str(video_path) # Assume success if downloaded with size
        else:
             logger.error(f"Failed to save video after download (size <= 1KB?): {video_path}")
             if video_path.exists(): video_path.unlink(missing_ok=True)
             return ""
             
    except requests.exceptions.RequestException as e:
         logger.error(f"Failed to download video {video_url}: {e}")
         return ""
    except Exception as e:
        logger.error(f"Error saving video {video_url}: {e}")
        if 'video_path' in locals() and video_path.exists():
             try: video_path.unlink(missing_ok=True)
             except OSError: pass
        return ""

def generate_alternative_keywords(scene, product_info=None):
    """Appelle Gemini pour générer 3 nouveaux mots-clés larges pour une scène donnée."""
    visual_desc = scene.get("visual_description", "")
    context = f"Produit : {product_info}. " if product_info else ""
    prompt = (
        f"{context}Voici la description d'une scène TikTok :\n"
        f"{visual_desc}\n"
        f"Aucun résultat vidéo n'a été trouvé pour les mots-clés initiaux : {scene.get('search_keywords', [])}. "
        f"Propose 3 nouveaux mots-clés ou expressions, différents et plus larges, en anglais, pour illustrer cette scène dans une banque de vidéos (Pexels/Pixabay). "
        f"Strictement 1 à 3 mots par mot-clé, séparés par des virgules. Réponds uniquement par une liste Python, exemple : ['mot1', 'mot2', 'mot3']"
    )
    response = generate_text(prompt)
    if not response:
        logger.error("Gemini n'a pas pu générer de nouveaux mots-clés.")
        return []
    # Extraction robuste de la liste Python
    try:
        match = re.search(r'\[(.*?)\]', response, re.DOTALL)
        if match:
            keywords = [k.strip(" ' \"") for k in match.group(1).split(',') if k.strip()]
            return keywords
        else:
            logger.error(f"Réponse Gemini inattendue : {response}")
            return []
    except Exception as e:
        logger.error(f"Erreur parsing Gemini keywords : {e} | Réponse : {response}")
        return []

# --- New Main Function --- 
def find_and_download_stock_videos(
    script_data: Dict[str, Any],
    output_dir: Path,
    preferred_source: str = "pexels", # pexels or pixabay - this will be used as a starting point per keyword
    videos_per_scene: int = 1
) -> Dict[int, List[str]]:
    """
    Finds and downloads stock videos for each scene based on search_keywords.
    Iterates through keywords sequentially, stopping when videos are found for a scene.
    """
    downloaded_scene_videos: Dict[int, List[str]] = {}
    if not script_data or "scenes" not in script_data:
        logger.error("Invalid script data provided to find_and_download_stock_videos.")
        return downloaded_scene_videos

    video_cache_dir = output_dir / "stock_videos_cache"
    video_cache_dir.mkdir(parents=True, exist_ok=True)

    scenes = script_data.get("scenes", [])
    product_info = script_data.get("product_info", None) or script_data.get("product", None)

    for scene_index, scene in enumerate(scenes):
        scene_number = scene.get("scene_number", scene_index + 1) # Use scene_number if available
        visual_type = scene.get("visual_type")
        
        # Skip if visual_type is product_video or not relevant for stock video search
        if visual_type == "product_video":
            logger.info(f"Scene {scene_number}: Skipping stock video search, visual_type is 'product_video'. A local product video is expected.")
            downloaded_scene_videos[scene_number] = [] # No stock videos to download
            continue
        elif visual_type not in ["stock_video", "hook"]: # 'hook' might also use stock
            logger.info(f"Scene {scene_number}: Skipping stock video search, visual_type is '{visual_type}'.")
            downloaded_scene_videos[scene_number] = []
            continue

        search_keywords_list = scene.get("search_keywords", [])
        if not isinstance(search_keywords_list, list) or not search_keywords_list:
            logger.warning(f"Scene {scene_number}: No search_keywords provided or not a list.")
            downloaded_scene_videos[scene_number] = []
            continue
        
        # Ensure keywords are strings
        search_keywords_list = [kw for kw in search_keywords_list if isinstance(kw, str) and kw.strip()]
        if not search_keywords_list:
            logger.warning(f"Scene {scene_number}: All keywords were empty or invalid.")
            downloaded_scene_videos[scene_number] = []
            continue

        minimum_duration = scene.get("duration_seconds", 3) # Default to scene duration
        found_videos_for_scene: List[Dict[str, Any]] = []

        logger.info(f"Scene {scene_number}: Processing keywords {search_keywords_list} sequentially.")

        for keyword in search_keywords_list:
            logger.info(f"Scene {scene_number}: Trying keyword '{keyword}'...")
            
            pexels_videos: List[Dict[str, Any]] = []
            pixabay_videos: List[Dict[str, Any]] = []

            if preferred_source == "pexels":
                pexels_videos = search_videos_pexels(keyword, minimum_duration)
                if pexels_videos:
                    logger.info(f"Scene {scene_number}: Found {len(pexels_videos)} Pexels videos for keyword '{keyword}'.")
                    found_videos_for_scene.extend(pexels_videos)
                else: # No Pexels videos, try Pixabay for this keyword
                    logger.info(f"Scene {scene_number}: No Pexels videos for '{keyword}', trying Pixabay.")
                    pixabay_videos = search_videos_pixabay(keyword, minimum_duration)
                    if pixabay_videos:
                        logger.info(f"Scene {scene_number}: Found {len(pixabay_videos)} Pixabay videos for keyword '{keyword}'.")
                        found_videos_for_scene.extend(pixabay_videos)
            
            elif preferred_source == "pixabay":
                pixabay_videos = search_videos_pixabay(keyword, minimum_duration)
                if pixabay_videos:
                    logger.info(f"Scene {scene_number}: Found {len(pixabay_videos)} Pixabay videos for keyword '{keyword}'.")
                    found_videos_for_scene.extend(pixabay_videos)
                else: # No Pixabay videos, try Pexels for this keyword
                    logger.info(f"Scene {scene_number}: No Pixabay videos for '{keyword}', trying Pexels.")
                    pexels_videos = search_videos_pexels(keyword, minimum_duration)
                    if pexels_videos:
                        logger.info(f"Scene {scene_number}: Found {len(pexels_videos)} Pexels videos for keyword '{keyword}'.")
                        found_videos_for_scene.extend(pexels_videos)
            
            else: # Default order if preferred_source is not recognized: Pexels then Pixabay
                pexels_videos = search_videos_pexels(keyword, minimum_duration)
                if pexels_videos:
                    logger.info(f"Scene {scene_number}: Found {len(pexels_videos)} Pexels videos for keyword '{keyword}'.")
                    found_videos_for_scene.extend(pexels_videos)
                else:
                    logger.info(f"Scene {scene_number}: No Pexels videos for '{keyword}', trying Pixabay.")
                    pixabay_videos = search_videos_pixabay(keyword, minimum_duration)
                    if pixabay_videos:
                        logger.info(f"Scene {scene_number}: Found {len(pixabay_videos)} Pixabay videos for keyword '{keyword}'.")
                        found_videos_for_scene.extend(pixabay_videos)

            if found_videos_for_scene:
                logger.info(f"Scene {scene_number}: Videos found with keyword '{keyword}'. Proceeding to download.")
                break
            else:
                logger.info(f"Scene {scene_number}: No videos found for keyword '{keyword}' from any source.")
        # End of keyword loop for the scene

        # Fallback Gemini si aucune vidéo trouvée
        if not found_videos_for_scene:
            logger.warning(f"Scene {scene_number}: No stock videos found après tous les mots-clés. Tentative Gemini...")
            alt_keywords = generate_alternative_keywords(scene, product_info)
            if alt_keywords:
                logger.info(f"Scene {scene_number}: Nouveaux mots-clés Gemini : {alt_keywords}")
                for keyword in alt_keywords:
                    pexels_videos = search_videos_pexels(keyword, minimum_duration)
                    if pexels_videos:
                        found_videos_for_scene.extend(pexels_videos)
                        break
                    pixabay_videos = search_videos_pixabay(keyword, minimum_duration)
                    if pixabay_videos:
                        found_videos_for_scene.extend(pixabay_videos)
                        break
            else:
                logger.warning(f"Scene {scene_number}: Gemini n'a pas pu générer de mots-clés alternatifs ou aucun résultat trouvé.")

        scene_video_paths: List[str] = []
        if not found_videos_for_scene:
            logger.warning(f"Scene {scene_number}: No stock videos found after trying all keywords: {search_keywords_list}.")
            downloaded_scene_videos[scene_number] = []
            continue

        # Shuffle to get variety if multiple videos were found for the successful keyword
        random.shuffle(found_videos_for_scene)
        
        download_count = 0
        for video_info in found_videos_for_scene:
            if download_count >= videos_per_scene:
                break
            
            video_url = video_info.get("url")
            if video_url:
                saved_path = save_video(video_url, video_cache_dir)
                if saved_path:
                    scene_video_paths.append(saved_path)
                    download_count += 1
                    logger.info(f"Scene {scene_number}: Successfully downloaded video {download_count}/{videos_per_scene} from {video_url}")
                else:
                    logger.warning(f"Scene {scene_number}: Failed to download video from {video_url}")
            else:
                logger.warning(f"Scene {scene_number}: Video info missing URL: {video_info}")

        downloaded_scene_videos[scene_number] = scene_video_paths
        if not scene_video_paths:
            logger.warning(f"Scene {scene_number}: Despite finding video metadata, failed to download any actual video files.")


    logger.info("Finished processing all scenes for stock videos.")
    return downloaded_scene_videos

# Remove old download_videos function
# def download_videos(...):
# ...

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_output_dir_main = Path("./test_project_output")
    test_script_file = Path("generated_script_test.json") # Assumes this exists from script_generator test

    # Create a dummy script file if it doesn't exist
    if not test_script_file.exists():
        dummy_script = {
            "script": "Test script voiceover.",
            "scenes": [
                {"scene_number": 1, "visual_type": "hook", "visual_description": "Hook description", "voiceover_text": "Hook VO", "duration_seconds": 5},
                {"scene_number": 2, "visual_type": "stock_video", "visual_description": "coding hacker matrix", "voiceover_text": "Code scene VO", "duration_seconds": 10},
                {"scene_number": 3, "visual_type": "ai_image", "visual_description": "Detailed AI prompt", "voiceover_text": "AI image VO", "duration_seconds": 8},
                {"scene_number": 4, "visual_type": "stock_video", "visual_description": "abstract technology background", "voiceover_text": "Tech scene VO", "duration_seconds": 12}
            ],
            "total_duration_estimated": 35
        }
        try:
            with open(test_script_file, 'w', encoding='utf-8') as f:
                json.dump(dummy_script, f, indent=2)
            logger.info(f"Created dummy script file for testing: {test_script_file}")
            script_data_main = dummy_script
        except Exception as e:
            logger.error(f"Could not create dummy script file: {e}")
            script_data_main = None
    else:
         try:
             with open(test_script_file, 'r', encoding='utf-8') as f:
                 script_data_main = json.load(f)
             logger.info(f"Loaded test script file: {test_script_file}")
         except Exception as e:
             logger.error(f"Could not load test script file {test_script_file}: {e}")
             script_data_main = None

    if script_data_main:
        print("--- Testing Stock Video Finder --- ")
        try:
            download_map = find_and_download_stock_videos(
                script_data=script_data_main,
                output_dir=test_output_dir_main,
                preferred_source="pexels",
                videos_per_scene=2
            )
            print("\n--- Download Results Map --- ")
            print(json.dumps(download_map, indent=2))
            print(f"Check downloaded files in: {test_output_dir_main / 'stock_videos'}")

        except ValueError as ve:
             print(f"Config error during test: {ve}. Ensure my_config.json has Pexels/Pixabay keys.")
        except Exception as e:
            print(f"An error occurred during testing: {e}")
    else:
        print("Skipping stock video finder test as script data could not be loaded/created.")
        
    print("--- End Test --- ")
    # finally:
        # Add cleanup logic for test_output_dir_main and dummy script if desired
        # print(f"\nCleanup: Consider deleting {test_output_dir_main} and {test_script_file}") 