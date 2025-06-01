import os
import random
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

from moviepy.editor import (
    VideoFileClip,
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    concatenate_videoclips,
    ColorClip,
    TextClip # Keep for potential error messages
)
from moviepy.video.fx.all import fadein, fadeout # MODIFIÉ
import moviepy.video.fx.all as vfx # AJOUTÉ
from moviepy.config import change_settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configure ImageMagick if needed (especially for complex text rendering, though less critical now)
# You might need to adjust this path or remove it if ImageMagick is not used/installed
try:
    change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"})
    logging.info("ImageMagick path configured (if available).")
except Exception as e:
     logging.warning(f"Could not configure ImageMagick path: {e}. This might affect complex TextClip rendering.")

TIKTOK_ASPECT_RATIO = (1080, 1920) # Width, Height
DEFAULT_BG_COLOR = (0, 0, 0) # Black background for padding
BLUR_RADIUS = 25 # Valeur pour sigma (flou gaussien)

# --- Define the missing helper function --- 
def close_clip(clip):
    """Safely closes a moviepy clip object, ignoring errors."""
    if clip:
        try:
            clip.close()
        except Exception as e:
            # Optional: Log warning, but don't crash the main process
            # logging.warning(f"Ignoring error while closing clip: {e}")
            pass
# --- End of helper function definition ---

def _create_blurred_background(source_clip: Any, target_size: Tuple[int, int], duration: float, blur_radius: int = BLUR_RADIUS) -> VideoFileClip:
    """Crée un clip d'arrière-plan flouté et agrandi à partir du clip source."""
    # Redimensionner pour remplir la cible (peut déformer, ok pour fond flou)
    # Utiliser .copy() pour éviter de modifier le clip original si c'est un objet partagé
    try:
        bg_clip = source_clip.copy()
    except AttributeError: # ImageClip n'a pas de copy() directement comme VideoFileClip
        bg_clip = source_clip 
        
    bg_clip_resized = bg_clip.resize(target_size)
    blurred_bg = bg_clip_resized.fx(vfx.gaussian_blur, sigma=blur_radius)
    return blurred_bg.set_duration(duration).set_fps(24) # Assurer une frame rate

def _resize_clip_for_foreground(clip: Any, target_width: int, target_height: int) -> Any:
    """Redimensionne un clip pour qu'il s'insère dans les dimensions cibles en conservant son ratio."""
    clip_w, clip_h = clip.size
    target_ratio = target_width / target_height
    clip_ratio = clip_w / clip_h

    if clip_ratio > target_ratio:
        # Clip plus large que la cible: ajuster par la largeur
        new_width = target_width
        new_height = int(new_width / clip_ratio)
    else:
        # Clip plus haut (ou même ratio) que la cible: ajuster par la hauteur
        new_height = target_height
        new_width = int(new_height * clip_ratio)
    
    return clip.resize((new_width, new_height))

def resize_clip_to_aspect(clip: Any, target_width: int, target_height: int, bg_color: tuple = DEFAULT_BG_COLOR) -> Any:
    """Resizes a clip to fit the target aspect ratio, adding padding if needed."""
    
    clip_w, clip_h = clip.size
    target_ratio = target_width / target_height
    clip_ratio = clip_w / clip_h

    if clip_ratio == target_ratio:
        # If aspect ratios match, just resize
        return clip.resize(width=target_width) # Resize based on width
    else:
        # Resize to fit within target dimensions while maintaining aspect ratio
        if clip_ratio > target_ratio:
            # Clip is wider than target: fit to width
            scale_factor = target_width / clip_w
        else:
            # Clip is taller than target: fit to height
            scale_factor = target_height / clip_h
            
        new_width = int(clip_w * scale_factor)
        new_height = int(clip_h * scale_factor)
        
        # Ensure duration is preserved for ImageClips without explicit duration
        clip_duration = clip.duration
        if clip_duration is None:
             logging.warning("Clip has no duration, defaulting to 1s for resize background.")
             clip_duration = 1 # Default duration if none
             
        resized_clip = clip.resize((new_width, new_height))
        
        # Create background clip
        background = ColorClip(size=(target_width, target_height), color=bg_color, duration=clip_duration)
        
        # Composite the resized clip onto the background
        # Use set_position('center') and set_duration on the final composite clip
        final_clip = CompositeVideoClip([
            background,
            resized_clip.set_position('center')
        ], size=(target_width, target_height))
        
        # Crucially, set the duration of the final composite clip
        final_clip = final_clip.set_duration(clip_duration)
        return final_clip

def apply_ken_burns(image_clip: ImageClip, duration: float, zoom_factor: float = 1.15, direction="random") -> CompositeVideoClip:
    """Applies a subtle zoom (Ken Burns) effect to an ImageClip."""
    
    img_w, img_h = image_clip.size

    def resize_func(t):
        # Calculate scale: starts at 1, ends at zoom_factor
        scale = 1 + (zoom_factor - 1) * (t / duration)
        return scale

    # Resize the clip over time
    zoomed_clip = image_clip.resize(resize_func)
    
    # Pan effect (optional, simple implementation: move slightly)
    # More complex panning requires calculating position based on zoom
    # Example: slight move up and right
    # pos_func = lambda t: ('center', img_h * 0.01 * (t / duration)) 
    # zoomed_clip = zoomed_clip.set_position(pos_func)
    zoomed_clip = zoomed_clip.set_position('center')
    
    # Create a composite clip to maintain original size and center the zoom
    # Use the original image clip as the base size reference
    # Set the final duration on the CompositeVideoClip
    final_kb_clip = CompositeVideoClip([zoomed_clip], size=image_clip.size).set_duration(duration)
    return final_kb_clip

def compose_final_video(
    script_data: Dict[str, Any],
    project_dir: Path,
    hook_video_path: str | None, # Path to the original hook video
    product_image_path: str | None, # Path to the product image
    stock_videos_map: Dict[int, List[str]], # Map scene_number -> list of downloaded stock video paths
    ai_images_dir: Path, # Directory containing AI images (e.g., 3.jpeg, 5.jpeg)
    main_product_video_path: str | None, # Path to the main product video file
    audio_path: Path, # Path to the final voiceover audio
    output_path: Path, # Path for the output video (no captions)
    target_aspect_ratio: tuple = TIKTOK_ASPECT_RATIO,
    add_blurred_bg: bool = True # NOUVEAU: Option pour activer/désactiver le fond flouté
) -> bool:
    """Composes the final video based on the script data and media assets."""
    
    target_w, target_h = target_aspect_ratio
    video_clips = []
    ai_image_index = 0 # To track which AI image to use sequentially
    scenes = script_data.get("scenes", [])

    if not scenes:
        logging.error("No scenes found in script data. Cannot compose video.")
        return False

    # --- Load Main Audio ---    
    try:
        main_audio_clip = AudioFileClip(str(audio_path))
        total_audio_duration = main_audio_clip.duration
        logging.info(f"Loaded main audio: {audio_path} (Duration: {total_audio_duration:.2f}s)")
    except Exception as e:
        logging.error(f"Failed to load main audio file {audio_path}: {e}")
        return False
        
    # --- Process Scenes --- 
    current_video_duration = 0.0
    error_occurred = False
    for scene in scenes:
        scene_number = scene.get("scene_number")
        visual_type = scene.get("visual_type")
        duration_seconds = scene.get("duration_seconds")
        
        if not all([scene_number, visual_type, duration_seconds]):
            logging.warning(f"Skipping scene due to missing data: {scene}")
            continue
            
        logging.info(f"Processing Scene {scene_number}: Type='{visual_type}', Duration={duration_seconds}s")
        scene_clip_raw = None # Clip original avant tout traitement majeur
        media_path_for_log = "N/A"
        
        try:
            # --- Load Media --- 
            if visual_type == "hook":
                if hook_video_path and Path(hook_video_path).is_file():
                    media_path_for_log = hook_video_path
                    # Limit hook duration to avoid freezing on short hooks
                    MAX_HOOK_DURATION = 4.0 # Max seconds to take from hook video
                    try:
                        full_hook_clip = VideoFileClip(media_path_for_log)
                        actual_hook_duration = full_hook_clip.duration
                        target_duration = min(duration_seconds, actual_hook_duration, MAX_HOOK_DURATION)
                        scene_clip_raw = full_hook_clip.subclip(0, target_duration)
                        # Keep the original clip object open until after subclip is potentially used
                        # full_hook_clip.close() # Close later in finally block if needed
                    except Exception as hook_e:
                        logging.error(f"Error loading hook video {media_path_for_log}: {hook_e}")
                        scene_clip_raw = None # Fallback to placeholder
                else:
                    logging.warning(f"Scene {scene_number}: Hook video not found or invalid: {hook_video_path}. Using black screen.")
            
            elif visual_type == "ai_image":
                # Find the next available AI image sequentially based on scene order of type 'ai_image'
                # Assumes image_generator saved them as 1.jpeg, 2.jpeg etc. IN THE ORDER of ai_image scenes
                ai_image_files = sorted(ai_images_dir.glob("*.jpeg"))
                if ai_image_index < len(ai_image_files):
                    media_path_for_log = str(ai_image_files[ai_image_index])
                    logging.info(f"Scene {scene_number}: Using AI image {media_path_for_log}")
                    scene_clip_raw = ImageClip(media_path_for_log).set_duration(duration_seconds)
                    ai_image_index += 1
                else:
                     logging.warning(f"Scene {scene_number}: No more AI images found in {ai_images_dir} (expected index {ai_image_index}). Using black screen.")
                     
            elif visual_type == "stock_video":
                video_paths = stock_videos_map.get(scene_number, [])
                if video_paths:
                    media_path_for_log = random.choice(video_paths)
                    logging.info(f"Scene {scene_number}: Using stock video {Path(media_path_for_log).name}")
                    temp_clip = VideoFileClip(media_path_for_log)
                    if temp_clip.duration >= duration_seconds:
                         scene_clip_raw = temp_clip.subclip(0, duration_seconds)
                    else:
                         logging.warning(f"Scene {scene_number}: Stock video duration ({temp_clip.duration:.2f}s) is shorter than required ({duration_seconds}s). Looping.")
                         scene_clip_raw = temp_clip.loop(duration=duration_seconds)
                    if scene_clip_raw: scene_clip_raw = scene_clip_raw.without_audio()
                else:
                    logging.warning(f"Scene {scene_number}: No downloaded stock videos found for this scene type. Using black screen.")
            
            elif visual_type == "product_shot":
                if product_image_path and Path(product_image_path).is_file():
                    media_path_for_log = product_image_path
                    scene_clip_raw = ImageClip(media_path_for_log).set_duration(duration_seconds)
                else:
                    logging.warning(f"Scene {scene_number}: Product image not found or invalid for type '{visual_type}'. Using black screen.")

            elif visual_type == "product_video":
                if main_product_video_path and Path(main_product_video_path).is_file():
                    media_path_for_log = main_product_video_path
                    logging.info(f"Scene {scene_number}: Using main product video {media_path_for_log}")
                    try:
                        temp_clip = VideoFileClip(media_path_for_log)
                        if temp_clip.duration >= duration_seconds:
                            scene_clip_raw = temp_clip.subclip(0, duration_seconds)
                        else:
                            logging.warning(f"Scene {scene_number}: Main product video '{Path(main_product_video_path).name}' duration ({temp_clip.duration:.2f}s) is shorter than required ({duration_seconds}s). Looping.")
                            scene_clip_raw = temp_clip.loop(duration=duration_seconds)
                        if scene_clip_raw: 
                            scene_clip_raw = scene_clip_raw.without_audio()
                    except Exception as e:
                        logging.error(f"Error loading main product video {media_path_for_log} for scene {scene_number}: {e}")
                        scene_clip_raw = None # Fallback
                else:
                    logging.warning(f"Scene {scene_number}: Main product video path not provided or file not found ('{main_product_video_path}') for type 'product_video'. Using black screen.")
            
            else:
                logging.warning(f"Scene {scene_number}: Unknown visual_type '{visual_type}'. Using black screen.")

            # --- Create Placeholder if Load Failed --- 
            if scene_clip_raw is None:
                scene_clip_raw = ColorClip(size=(target_w, target_h), color=DEFAULT_BG_COLOR, duration=duration_seconds)
                logging.debug(f"Scene {scene_number}: Created placeholder ColorClip.")
            
            # --- Ensure Clip Duration and Resize --- 
            # Force duration just in case
            scene_clip_raw = scene_clip_raw.set_duration(duration_seconds)
            
            # Resize to target aspect ratio
            processed_clip = resize_clip_to_aspect(scene_clip_raw, target_w, target_h)
            video_clips.append(processed_clip)
            current_video_duration += duration_seconds
            logging.debug(f"Scene {scene_number}: Processed. Clip duration: {processed_clip.duration:.2f}s")

        except Exception as e:
            logging.error(f"Error processing Scene {scene_number} (Media: {media_path_for_log}): {e}", exc_info=True)
            # Add a placeholder on error to avoid stopping the whole process
            error_clip = ColorClip(size=(target_w, target_h), color=(255,0,0), duration=duration_seconds) # Red screen for error
            error_text = TextClip(f"Error\nScene {scene_number}", fontsize=50, color='white').set_duration(duration_seconds).set_position('center')
            processed_clip = CompositeVideoClip([error_clip, error_text], size=(target_w, target_h)).set_duration(duration_seconds)
            video_clips.append(processed_clip)
            current_video_duration += duration_seconds
            error_occurred = True # Mark that an error happened
            # continue # Continue to next scene
            
        finally:
             # Clean up temporary clips to free memory? 
             # Check if clip needs closing: clip.close() (especially VideoFileClip)
             if isinstance(scene_clip_raw, (VideoFileClip, ImageClip)): 
                 try: scene_clip_raw.close() 
                 except: pass 

    # --- Concatenate and Add Audio --- 
    if not video_clips:
        logging.error("No video clips were processed. Cannot create final video.")
        return False
        
    try:
        logging.info(f"Concatenating {len(video_clips)} clips. Target duration: {current_video_duration:.2f}s")
        final_video_track = concatenate_videoclips(video_clips, method="compose")
        final_video_track = final_video_track.set_fps(30) # Set FPS
        
        # Adjust audio to match final video duration
        final_duration = final_video_track.duration
        logging.info(f"Final concatenated video duration: {final_duration:.2f}s")
        # Compare audio duration but avoid explicit subclip which might cause precision errors
        if abs(final_duration - total_audio_duration) > 0.5:
             logging.warning(f"Video duration ({final_duration:.2f}s) differs significantly from audio duration ({total_audio_duration:.2f}s). Audio will be truncated by video length during write.")

        # Set the original main audio clip; moviepy should handle duration matching during write
        final_video = final_video_track.set_audio(main_audio_clip) 
        
        # --- Write Video File --- 
        logging.info(f"Writing final video (no captions) to: {output_path}...")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        final_video.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            threads=os.cpu_count() or 2, # Use available cores
            logger='bar' # Show progress bar
        )
        
        # --- Clean Up --- 
        close_clip(final_video)
        # Log success using logging.info instead of logging.success
        logging.info(f"✅ Final video (no captions) saved to: {output_path}")
        return True

    except Exception as e:
        logging.error(f"Failed during final video composition or writing: {e}", exc_info=True)
        return False


# Remove old functions
# def calculate_image_duration(...)
# def create_video_clip(...)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("--- Testing Video Composer --- ")
    
    # --- Setup Test Environment --- 
    test_proj_dir = Path("./test_composer_project")
    test_proj_dir.mkdir(exist_ok=True)
    (test_proj_dir / "images").mkdir(exist_ok=True)
    (test_proj_dir / "stock_videos").mkdir(exist_ok=True)
    (test_proj_dir / "audio").mkdir(exist_ok=True)
    (test_proj_dir / "output").mkdir(exist_ok=True)

    # Create dummy script data (same as stock_video_finder test)
    test_script_data = {
        "script": "Test script voiceover. Scene 2. Scene 3. Scene 4.",
        "scenes": [
            {"scene_number": 1, "visual_type": "hook", "visual_description": "Hook description", "duration_seconds": 3},
            {"scene_number": 2, "visual_type": "stock_video", "visual_description": "coding hacker matrix", "duration_seconds": 4},
            {"scene_number": 3, "visual_type": "ai_image", "visual_description": "Detailed AI prompt", "duration_seconds": 5},
            {"scene_number": 4, "visual_type": "product_shot", "visual_description": "Close up", "duration_seconds": 3},
            {"scene_number": 5, "visual_type": "ai_image", "visual_description": "Another detailed AI prompt", "duration_seconds": 4}
        ],
        "total_duration_estimated": 19
    }

    # Create dummy media files 
    # Hook Video (simple black screen)
    hook_vid_path = test_proj_dir / "hook.mp4"
    ColorClip(size=(640, 360), color=(0,0,0), duration=5).write_videofile(str(hook_vid_path), fps=30, logger=None)
    
    # Product Image (simple white square)
    prod_img_path = test_proj_dir / "product.png"
    ColorClip(size=(200, 200), color=(255,255,255), ismask=False, duration=1).save_frame(str(prod_img_path))
    
    # AI Images (simple colored squares)
    ai_img_dir = test_proj_dir / "images"
    ColorClip(size=(500, 500), color=(0,255,0), ismask=False, duration=1).save_frame(str(ai_img_dir / "1.jpeg")) # Corresponds to scene 3
    ColorClip(size=(500, 500), color=(0,0,255), ismask=False, duration=1).save_frame(str(ai_img_dir / "2.jpeg")) # Corresponds to scene 5
    
    # Stock Video (simple blue screen)
    stock_vid_dir = test_proj_dir / "stock_videos"
    stock_vid_path_1 = stock_vid_dir / "stock1.mp4"
    ColorClip(size=(480, 854), color=(100,100,255), duration=6).write_videofile(str(stock_vid_path_1), fps=30, logger=None)
    stock_map = { 2: [str(stock_vid_path_1)] } # Scene 2 uses this stock video
    
    # Audio File (silence matching duration)
    audio_fpath = test_proj_dir / "audio" / "voiceover.mp3"
    total_duration = sum(s['duration_seconds'] for s in test_script_data['scenes']) 
    # Create silent audio - moviepy doesn't have a direct silent generator, 
    # we might skip audio for this basic test or use a real short mp3 file
    # For simplicity, we'll proceed without perfect audio match for this test.
    # Let's create a dummy file just so it exists
    with open(audio_fpath, "w") as af: af.write("dummy") 
    logging.warning("Using dummy audio file for testing. Duration mismatch is expected.")

    # Output Path
    output_vid_path = test_proj_dir / "output" / "final_no_captions.mp4"
    # -----------------------------

    print("--- Running Video Composition Test --- ")
    try:
        success = compose_final_video(
            script_data=test_script_data,
            project_dir=test_proj_dir,
            hook_video_path=str(hook_vid_path),
            product_image_path=str(prod_img_path),
            stock_videos_map=stock_map,
            ai_images_dir=ai_img_dir,
            main_product_video_path=None,
            audio_path=audio_fpath,
            output_path=output_vid_path
        )
        
        if success:
            print(f"Composition test successful. Video saved to: {output_vid_path}")
        else:
             print("Composition test failed.")
             
    except Exception as e:
         print(f"An error occurred during composition test: {e}", exc_info=True)
         
    print("--- End Test --- ")
    # Cleanup?
    # import shutil
    # shutil.rmtree(test_proj_dir) 