import json
import logging
from pathlib import Path
from typing import Dict, Any, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_ai_image_prompts(script_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extracts AI image prompts from the script data.

    Args:
        script_data: The parsed JSON script data from Gemini.

    Returns:
        A list of dictionaries, where each dictionary contains the scene number 
        and the detailed English prompt for AI image generation.
        Example: [{'scene_number': 3, 'prompt': 'Detailed description...'}, ...]
    """
    ai_prompts = []
    scenes = script_data.get("scenes", [])
    if not scenes:
        logging.warning("No scenes found in script data for extracting image prompts.")
        return []

    for scene in scenes:
        scene_number = scene.get("scene_number")
        visual_type = scene.get("visual_type")
        description = scene.get("visual_description")

        if visual_type == "product_video":
            logging.info(f"Scene {scene_number}: Skipping AI image prompt extraction, visual_type is 'product_video'.")
            continue

        if visual_type == "ai_image" and description and scene_number is not None:
            if not isinstance(description, str) or not description.strip():
                 logging.warning(f"Scene {scene_number}: Skipping invalid or empty AI image description.")
                 continue
                 
            # The description *should* already be the detailed English prompt
            ai_prompts.append({
                "scene_number": scene_number,
                "prompt": description.strip() # Ensure no leading/trailing whitespace
            })
            logging.info(f"Scene {scene_number}: Extracted AI image prompt.")
        elif visual_type == "ai_image" and not description:
             logging.warning(f"Scene {scene_number}: Marked as 'ai_image' but 'visual_description' is missing or empty.")
             
    if not ai_prompts:
         logging.warning("No scenes with visual_type 'ai_image' and valid descriptions were found.")
         
    return ai_prompts

def save_image_prompts(prompts_list: List[Dict[str, Any]], output_path: Path) -> bool:
    """Saves the extracted image prompts to a JSON file compatible with image_generator.
    
    Args:
        prompts_list: The list of prompt dictionaries [{'scene_number': n, 'prompt': '...'}]
        output_path: The path to save the JSON file.

    Returns:
        True if successful, False otherwise.
    """
    # Format for image_generator.py (expects {"prompts": [list_of_strings_or_dicts_with_prompt_key]})
    output_data = {"prompts": [item["prompt"] for item in prompts_list]} # Extract just the prompt text
    
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        logging.info(f"✅ AI Image prompts saved to: {output_path}")
        return True
    except IOError as e:
        logging.error(f"Failed to save AI image prompts to {output_path}: {e}")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred while saving AI image prompts: {e}")
        return False


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("--- Testing AI Image Prompt Extractor --- ")

    # Use the same dummy script data structure as stock_video_finder test
    dummy_script_for_prompts = {
        "script": "Test script voiceover.",
        "scenes": [
            {"scene_number": 1, "visual_type": "hook", "visual_description": "Hook description", "voiceover_text": "Hook VO", "duration_seconds": 5},
            {"scene_number": 2, "visual_type": "stock_video", "visual_description": "coding hacker matrix", "voiceover_text": "Code scene VO", "duration_seconds": 10},
            {"scene_number": 3, "visual_type": "ai_image", "visual_description": "A highly detailed photorealistic image of a programmer working late at night, illuminated only by the screen, energy drink can on desk", "voiceover_text": "AI image VO", "duration_seconds": 8},
             {"scene_number": 4, "visual_type": "product_shot", "visual_description": "Close up of product", "voiceover_text": "Product VO", "duration_seconds": 7},
            {"scene_number": 5, "visual_type": "ai_image", "visual_description": "Impressionistic painting of brain synapses firing with vibrant colors", "voiceover_text": "Brain VO", "duration_seconds": 9}
        ],
        "total_duration_estimated": 39
    }
    output_prompts_file = Path("generated_image_prompts_test.json")

    # Extract prompts
    extracted_prompts = extract_ai_image_prompts(dummy_script_for_prompts)

    if extracted_prompts:
        print("\n--- Extracted Prompts Data --- ")
        print(json.dumps(extracted_prompts, indent=2, ensure_ascii=False))
        
        # Save the extracted prompts
        save_success = save_image_prompts(extracted_prompts, output_prompts_file)
        
        if save_success:
             print(f"\nPrompts successfully saved for image generator: {output_prompts_file}")
             # Optional: Verify file content
             # with open(output_prompts_file, 'r', encoding='utf-8') as f:
             #    print("File content:", f.read())
        else:
            print("\nFailed to save the prompts file.")
            
    else:
        print("\nNo AI image prompts were extracted from the script data.")

    print("--- End Test --- ")
    # Cleanup test file
    # if output_prompts_file.exists():
    #     import os
    #     os.remove(output_prompts_file) 