import os
import requests
import json
import base64
from pathlib import Path
from typing import List, Dict
# Import the new config loader
from .config_loader import get_together_api_key 
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Remove old loading function
# def load_api_keys(config_file: str = "my_config.json") -> Dict:
#     ...

def generate_images(image_prompts_path: str, output_dir: str) -> None:
    """
    Generate images from JSON prompts file using FLUX.1-schnell model
    Args:
        image_prompts_path: Path to JSON file with prompts
        output_dir: Directory to save generated images
    """
    image_prompts_path = Path(image_prompts_path)
    output_dir = Path(output_dir)

    if not image_prompts_path.exists():
        logging.error(f"Prompt file {image_prompts_path} not found")
        raise FileNotFoundError(f"Prompt file {image_prompts_path} not found")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Get API key from central loader
    api_key = get_together_api_key()
    if not api_key:
        logging.error("Together AI API key not found in configuration.")
        raise ValueError("Together AI API key not found in configuration.")

    try:
        with open(image_prompts_path, "r", encoding='utf-8') as f:
            prompts_data = json.load(f)
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON in prompts file: {image_prompts_path}")
        raise
    except Exception as e:
        logging.error(f"Error reading prompts file {image_prompts_path}: {e}")
        raise

    if "prompts" not in prompts_data or not isinstance(prompts_data["prompts"], list):
        logging.error("Invalid prompts format - expected {'prompts': [...]}")
        raise ValueError("Invalid prompts format - expected {'prompts': [...]}")

    # Check if prompts list is empty
    if not prompts_data["prompts"]:
        logging.warning("No prompts found in the input file. Skipping image generation.")
        return
        
    generated_image_paths = []
    for i, prompt_item in enumerate(prompts_data["prompts"], 1):
        logging.info(f"🖼️  Generating image {i}/{len(prompts_data['prompts'])}...")
        
        # Adapt prompt extraction based on actual structure from prompt generator
        # Assuming it's now a list of strings or simple dicts
        if isinstance(prompt_item, str):
            prompt_text = prompt_item
        elif isinstance(prompt_item, dict) and 'prompt' in prompt_item:
             prompt_text = prompt_item['prompt']
        # Add more complex extraction logic if needed based on script_generator_gemini output
        else: 
            logging.warning(f"Skipping invalid prompt item at index {i-1}: {prompt_item}")
            continue # Skip this prompt
            
        if not prompt_text: # Skip empty prompts
             logging.warning(f"Skipping empty prompt at index {i-1}.")
             continue

        try:
            response = requests.post(
                url="https://api.together.xyz/v1/images/generations",
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                    "authorization": f"Bearer {api_key}"
                },
                json={
                    "model": "black-forest-labs/FLUX.1-schnell",
                    "prompt": prompt_text,
                    "steps": 3,
                    "n": 1,
                    "height": 1792, # TikTok standard resolution (reverse)
                    "width": 1008,
                },
                timeout=60 # Increased timeout
            )

            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            data = response.json()
            if "data" in data and len(data["data"]) > 0 and "url" in data["data"][0]:
                image_url = data["data"][0]["url"]
                # Download the image
                image_response = requests.get(image_url, timeout=60)
                image_response.raise_for_status()

                # Determine the next sequential filename
                existing_files = sorted(output_dir.glob("*.jpeg"))
                next_number = 1
                if existing_files:
                    try:
                        last_number = int(existing_files[-1].stem)
                        next_number = last_number + 1
                    except ValueError:
                         # Handle cases where filenames are not simple numbers
                         next_number = len(existing_files) + 1 
                         
                image_path = output_dir / f"{next_number}.jpeg"

                with open(image_path, "wb") as f:
                    f.write(image_response.content)
                logging.info(f"✅ Image saved to {image_path}")
                generated_image_paths.append(str(image_path))
            else:
                logging.warning(f"⚠️ No image data in response for prompt {i}: {data}")
        except requests.exceptions.RequestException as e:
             logging.error(f"⚠️ Request failed for image {i}: {e}")
        except Exception as e:
             logging.error(f"⚠️ An unexpected error occurred for image {i}: {e}")
             
    logging.info(f"Image generation complete. {len(generated_image_paths)} images saved.")


if __name__ == "__main__":
    # Example usage (create dummy files for testing if needed)
    example_prompts_file = Path("example_image_prompts.json")
    example_output_dir = Path("generated_images_test")
    
    # Create a dummy prompt file for testing
    dummy_prompts = {"prompts": ["A vibrant futuristic cityscape at sunset", "A cute cat wearing a tiny hat"]}
    try:
        with open(example_prompts_file, 'w', encoding='utf-8') as f:
            json.dump(dummy_prompts, f)
        print(f"Created dummy prompt file: {example_prompts_file}")
        
        generate_images(
            image_prompts_path=str(example_prompts_file),
            output_dir=str(example_output_dir)
        )
    except ValueError as ve:
         print(f"Config error: {ve}. Make sure my_config.json has 'together_api_key'.")
    except Exception as e:
        print(f"An error occurred during test: {e}")
    finally:
        # Clean up dummy file
        if example_prompts_file.exists():
             os.remove(example_prompts_file)
             print(f"Cleaned up dummy file: {example_prompts_file}") 