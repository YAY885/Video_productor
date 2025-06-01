import logging
import json
from pathlib import Path
import time
import shutil
import argparse

# Import necessary functions from utils
from utils.config_loader import load_config # To ensure config is loaded early
from utils.video_analyzer import get_hook_description
from utils.script_generator_gemini import generate_script, save_script
from utils.image_prompt_generator_gemini import extract_ai_image_prompts, save_image_prompts
from utils.image_generator import generate_images
from utils.stock_video_finder import find_and_download_stock_videos
from utils.audio_generator_fr import generate_audio_fr
from utils.caption_generator import convert_srt_to_timed_words
from utils.video_composer import compose_final_video
from utils.caption_overlay import add_captions_to_video

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_project_structure(project_name: str) -> Path:
    """Creates the necessary directory structure for the project."""
    project_dir = Path(project_name)
    project_dir.mkdir(exist_ok=True)
    (project_dir / "audio").mkdir(exist_ok=True)
    (project_dir / "images").mkdir(exist_ok=True)
    (project_dir / "stock_videos").mkdir(exist_ok=True)
    (project_dir / "captions").mkdir(exist_ok=True)
    (project_dir / "output").mkdir(exist_ok=True)
    logging.info(f"Project directory structure created/verified at: {project_dir}")
    return project_dir

def run_pipeline(project_name: str, hook_video: str, product_info: str, product_image: str | None = None, topic: str = "", language: str = "French", product_video_path: str | None = None):
    """Runs the full video generation pipeline."""
    start_time = time.time()
    logging.info(f"--- Starting TikTok Gemini Generator Pipeline for: {project_name} ---")

    # --- 0. Setup ---    
    try:
        # Load config early to catch errors
        config = load_config()
        logging.info("Configuration loaded.")
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}. Pipeline cannot continue.")
        return

    project_dir = create_project_structure(project_name)
    script_json_path = project_dir / "script.json"
    image_prompts_path = project_dir / "image_prompts.json"
    ai_images_dir = project_dir / "images"
    stock_videos_dir = project_dir / "stock_videos"
    audio_dir = project_dir / "audio"
    voiceover_audio_path = audio_dir / "voiceover.mp3"
    voiceover_srt_path = audio_dir / "voiceover.srt"
    captions_dir = project_dir / "captions"
    captions_json_path = captions_dir / "captions.json"
    output_dir = project_dir / "output"
    final_video_no_captions_path = output_dir / "final_video_no_captions.mp4"
    final_video_with_captions_path = output_dir / "final_video_with_captions.mp4"

    # --- 1. Analyze Hook (Optional) --- 
    hook_desc = None
    if hook_video:
        logging.info("--- Step 1: Analyzing Hook Video ---")
        hook_video_path = Path(hook_video)
        if hook_video_path.is_file():
             hook_desc = get_hook_description(str(hook_video_path))
             if not hook_desc:
                 logging.warning("Hook analysis failed or returned empty. Continuing without description.")
        else:
            logging.warning(f"Hook video path invalid: {hook_video}. Skipping analysis.")
    else:
         logging.info("--- Step 1: Skipped Hook Video Analysis (No path provided) ---")

    # --- 2. Generate Script --- 
    logging.info("--- Step 2: Generating Script --- ")
    script_data = generate_script(
        hook_description=hook_desc,
        product_info=product_info,
        language=language,
        topic=topic
        # Add other parameters like style, target_audience, cta if needed
    )
    if not script_data:
        logging.error("Script generation failed. Pipeline cannot continue.")
        return
    save_script(script_data, script_json_path)
    script_full_text = script_data.get("script", "")
    if not script_full_text:
         logging.error("Generated script is missing the main 'script' text. Pipeline cannot continue.")
         return

    # User interaction point for product videos
    if any(scene.get("visual_type") == "product_video" for scene in script_data.get("scenes", [])):
        logging.info("IMPORTANT ACTION REQUIRED:")
        logging.info(f"The generated script ({script_json_path}) includes scenes of type 'product_video'.")
        logging.info("Please EDIT this file now and fill in the 'product_video_filename' for each of these scenes with the actual filename of your video (e.g., 'my_product_demo.mp4').")
        logging.info(f"These video files should be located in the directory specified by --product_video_path (currently: {Path(product_video_path).resolve() if product_video_path else 'Not Specified (will use default or fail)'}).")
        # In a more interactive setup, you might pause here:
        # input("Press Enter to continue after editing the script.json file...")

    # --- 3. Generate AI Image Prompts --- 
    logging.info("--- Step 3: Extracting AI Image Prompts --- ")
    ai_prompts_list = extract_ai_image_prompts(script_data)
    if ai_prompts_list:
        if not save_image_prompts(ai_prompts_list, image_prompts_path):
             logging.warning("Failed to save AI image prompts file, but attempting to continue.")
    else:
        logging.info("No AI image prompts to generate.")
        image_prompts_path = None # Mark as none if no prompts

    # --- 4. Generate AI Images --- 
    if image_prompts_path and ai_prompts_list:
        logging.info("--- Step 4: Generating AI Images --- ")
        try:
            generate_images(str(image_prompts_path), str(ai_images_dir))
        except Exception as e:
            logging.error(f"AI Image generation failed: {e}. Continuing without AI images.")
            # We might want to handle this more gracefully in the composer later
    else:
         logging.info("--- Step 4: Skipped AI Image Generation (No prompts) ---")

    # --- 5. Find & Download Stock Videos --- 
    logging.info("--- Step 5: Finding and Downloading Stock Videos --- ")
    stock_videos_map = {}
    try:
         stock_videos_map = find_and_download_stock_videos(
             script_data=script_data,
             output_dir=stock_videos_dir
             # preferred_source="pexels", videos_per_scene=1 # Add options if needed
         )
    except Exception as e:
         logging.error(f"Stock video search/download failed: {e}. Video composition might lack these scenes.")
         
    # --- 6. Generate Audio & SRT --- 
    logging.info("--- Step 6: Generating Audio (TTS), SRT, and Timed Words JSON --- ")
    audio_success = generate_audio_fr(
        script_text=script_full_text,
        output_audio_path=voiceover_audio_path,
        output_subtitle_path=voiceover_srt_path,
        output_captions_json_path=captions_json_path,
        voice_name="fr-FR-RemyMultilingualNeural"
    )
    if not audio_success:
        logging.error("Audio and/or Timed Words JSON generation failed. Pipeline cannot continue.")
        return

    # --- 7. Convert SRT to Timed Words JSON (ÉTAPE SUPPRIMÉE/MODIFIÉE) --- 
    logging.info("--- Step 7: Skipped SRT to Timed Words JSON conversion (JSON generated directly) ---")
    if not captions_json_path.exists():
         logging.error("Timed words JSON file was not found after audio generation. Final video will not have captions.")
         # captions_json_path = None # Déjà géré si audio_success est False, mais double sécurité
         # On pourrait décider d'arrêter ici si le JSON est crucial et que audio_success était True pour une raison imprévue

    # --- 8. Compose Video (No Captions) --- 
    logging.info("--- Step 8: Composing Video (without captions) --- ")
    composition_success = compose_final_video(
        script_data=script_data,
        project_dir=project_dir,
        hook_video_path=hook_video, # Pass original path
        product_image_path=product_image, # Pass original path
        stock_videos_map=stock_videos_map,
        ai_images_dir=ai_images_dir,
        main_product_video_path=product_video_path, # Changé de product_videos_dir
        audio_path=voiceover_audio_path,
        output_path=final_video_no_captions_path
    )
    if not composition_success:
        logging.error("Video composition failed. Pipeline cannot continue.")
        return

    # --- 9. Add Captions Overlay --- 
    if captions_json_path:
        logging.info("--- Step 9: Adding Captions Overlay --- ")
        try:
            add_captions_to_video(final_video_no_captions_path, captions_json_path, final_video_with_captions_path)
            logging.info(f"Captions added successfully to {final_video_with_captions_path}")
        except Exception as e:
            logging.error(f"Failed to add captions overlay: {e}")
            logging.warning("Proceeding with the video without captions.")
            # Optionally copy the no-caption video to the final name
            try:
                shutil.copy(final_video_no_captions_path, final_video_with_captions_path)
                logging.info(f"Copied video without captions to final destination: {final_video_with_captions_path}")
            except Exception as copy_e:
                logging.error(f"Failed to copy no-caption video: {copy_e}")
    else:
         logging.warning("--- Step 9: Skipped Adding Captions (JSON conversion failed earlier) ---")
         # Copy the no-caption video to the final name
         try:
             shutil.copy(final_video_no_captions_path, final_video_with_captions_path)
             logging.info(f"Copied video without captions to final destination: {final_video_with_captions_path}")
         except Exception as copy_e:
              logging.error(f"Failed to copy no-caption video: {copy_e}")
              
    # --- End --- 
    end_time = time.time()
    total_time = end_time - start_time
    logging.info(f"--- Pipeline Completed for: {project_name} in {total_time:.2f} seconds ---")
    logging.info(f"Final video available at: {final_video_with_captions_path}")

    # Retourner le chemin du fichier si tout s'est bien passé et que le fichier existe
    if final_video_with_captions_path.exists():
        return final_video_with_captions_path
    else:
        logging.error("Pipeline seemed to complete, but the final video file was not found.")
        return None # Retourner None si le fichier final n'est pas trouvé

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TikTok Gemini Video Generator Pipeline")
    parser.add_argument("-n", "--name", required=True, help="Project name (used for output directory)")
    parser.add_argument("-k", "--hook", required=True, help="Path to the hook video file")
    parser.add_argument("-p", "--product", required=True, help="Product information string")
    parser.add_argument("-pi", "--product-image", help="Path to the product image file (optional)")
    parser.add_argument("-t", "--topic", default="", help="Optional topic context for the script")
    parser.add_argument("-l", "--language", default="French", help="Language for the script and TTS")
    parser.add_argument("-pvp", "--product_video_path", help="Path to the product video file (optional)")
    
    args = parser.parse_args()

    # L'appel ici ne capture pas la valeur de retour car c'est l'exécution principale
    run_pipeline(
        project_name=args.name,
        hook_video=args.hook,
        product_info=args.product,
        product_image=args.product_image,
        topic=args.topic,
        language=args.language,
        product_video_path=args.product_video_path
    ) 