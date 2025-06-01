import os
import time
import google.generativeai as genai
from PIL import Image # Pour charger les images
import logging
from pathlib import Path # Import Path
# Import the new config loader
from .config_loader import get_google_api_key 

# Configuration du logging (optionnel mais recommandé)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
model = None # Initialize model variable
GOOGLE_API_KEY = None
try:
    # Load the API key using the config loader
    GOOGLE_API_KEY = get_google_api_key()
    if not GOOGLE_API_KEY:
        raise ValueError("Clé API GOOGLE_API_KEY non trouvée via config_loader.")
    genai.configure(api_key=GOOGLE_API_KEY)
    logging.info("SDK Google Generative AI configuré.")
    # Load the model after configuration
    MODEL_NAME = "gemini-2.5-pro-exp-03-25"
    model = genai.GenerativeModel(MODEL_NAME)
    logging.info(f"Modèle {MODEL_NAME} chargé.")
except ValueError as ve:
    logging.error(f"Erreur de configuration: {ve}")
except Exception as e:
    logging.error(f"Erreur lors de la configuration ou chargement modèle Gemini: {e}")
    # Decide if the script should exit or continue without the model
    # exit() # Or handle gracefully later

# --- Fonctions --- (Assuming model is loaded)

def generate_text(prompt: str) -> str | None:
    """Génère du texte à partir d'un prompt en utilisant Gemini."""
    if not model:
        logging.error("Le modèle Gemini n'a pas été chargé. Impossible de générer du texte.")
        return None
    try:
        logging.info(f"Génération de texte pour le prompt: '{prompt[:50]}...'")
        response = model.generate_content(prompt)
        logging.info("Réponse texte générée.")
        if not response.parts:
            safety_ratings = response.prompt_feedback.safety_ratings if response.prompt_feedback else 'N/A'
            logging.warning(f"Réponse texte bloquée/vide. Raison: {response.prompt_feedback.block_reason if response.prompt_feedback else 'Unknown'}, Safety: {safety_ratings}")
            return None
        return response.text
    except Exception as e:
        logging.error(f"Erreur lors de la génération de texte: {e}")
        return None

def analyze_image(prompt: str, image_path: str) -> str | None:
    """Analyse une image avec un prompt texte."""
    if not model:
        logging.error("Le modèle Gemini n'a pas été chargé. Impossible d'analyser l'image.")
        return None
    try:
        image_file = Path(image_path)
        if not image_file.is_file():
            logging.error(f"Fichier image non trouvé: {image_path}")
            return None

        logging.info(f"Analyse de l'image '{image_path}' avec prompt: '{prompt[:50]}...'")
        img = Image.open(image_path)
        response = model.generate_content([prompt, img])
        logging.info("Réponse de l'analyse d'image générée.")
        if not response.parts:
            safety_ratings = response.prompt_feedback.safety_ratings if response.prompt_feedback else 'N/A'
            logging.warning(f"Réponse analyse image bloquée/vide pour '{image_path}'. Raison: {response.prompt_feedback.block_reason if response.prompt_feedback else 'Unknown'}, Safety: {safety_ratings}")
            return None
        return response.text
    except Exception as e:
        logging.error(f"Erreur lors de l'analyse de l'image '{image_path}': {e}")
        return None

def analyze_video(prompt: str, video_path: str, request_timeout: int = 600) -> str | None:
    """Analyse une vidéo avec un prompt texte en utilisant l'API File."""
    if not model:
        logging.error("Le modèle Gemini n'a pas été chargé. Impossible d'analyser la vidéo.")
        return None
        
    uploaded_file = None
    try:
        video_file = Path(video_path)
        if not video_file.is_file():
            logging.error(f"Fichier vidéo non trouvé: {video_path}")
            return None

        logging.info(f"Début de l'upload du fichier vidéo: {video_path}")
        uploaded_file = genai.upload_file(path=video_path, display_name=video_file.name)
        logging.info(f"Fichier '{uploaded_file.display_name}' uploadé (URI: {uploaded_file.uri}). Attente du traitement...")

        start_time = time.time()
        while uploaded_file.state.name == "PROCESSING":
            if time.time() - start_time > request_timeout:
                 raise TimeoutError(f"Timeout ({request_timeout}s) pendant traitement vidéo.")
            logging.debug("Traitement vidéo en cours...") # Changed to debug
            time.sleep(10)
            uploaded_file = genai.get_file(uploaded_file.name)

        if uploaded_file.state.name != "ACTIVE":
            logging.error(f"Traitement vidéo échoué/interrompu. État: {uploaded_file.state.name}")
            # Attempt to delete the failed upload
            try:
                logging.info(f"Tentative de suppression du fichier échoué: {uploaded_file.name}")
                genai.delete_file(uploaded_file.name)
            except Exception as del_e:
                logging.warning(f"Échec suppression fichier échoué {uploaded_file.name}: {del_e}")
            return None

        # THIS IS THE CORRECT LOCATION FOR THIS BLOCK:
        logging.info(f"Fichier vidéo prêt (ACTIVE). Analyse avec le prompt: '{prompt[:50]}...'")

        # 3. Faire la requête d'analyse
        response = model.generate_content([prompt, uploaded_file], request_options={'timeout': request_timeout})
        logging.info("Réponse de l'analyse vidéo générée.")

        # Check for safety/block
        if not response.parts:
            safety_ratings = response.prompt_feedback.safety_ratings if response.prompt_feedback else 'N/A'
            logging.warning(f"Réponse analyse vidéo bloquée/vide pour '{video_path}'. Raison: {response.prompt_feedback.block_reason if response.prompt_feedback else 'Unknown'}, Safety: {safety_ratings}")
            return None
        return response.text

    except TimeoutError as e:
        logging.error(f"Timeout lors de l'analyse vidéo: {e}")
        return None
    except Exception as e:
        logging.error(f"Erreur lors de l'analyse de la vidéo '{video_path}': {e}", exc_info=True) # Add exc_info
        return None
    finally:
        # 4. Supprimer le fichier uploadé (toujours tenter)
        if uploaded_file:
            try:
                logging.info(f"Suppression du fichier uploadé: {uploaded_file.name} (État: {uploaded_file.state.name})")
                genai.delete_file(uploaded_file.name)
                logging.info(f"Fichier {uploaded_file.name} supprimé.")
            except Exception as e:
                logging.warning(f"Échec suppression fichier {uploaded_file.name}: {e}")

# --- Exemple d'Utilisation --- (Requires fixing paths)
if __name__ == "__main__":
    # Correct paths needed for tests to run
    sample_image_path = "./test_media/image.jpg"  # Example relative path
    sample_video_path = "./test_media/video.mp4"  # Example relative path
    
    # Create dummy media dir if not exists for basic testing
    test_media_dir = Path("./test_media")
    test_media_dir.mkdir(exist_ok=True)
    # TODO: Add creation of dummy image/video files for proper testing if needed

    # Check if model loaded before running tests
    if not model:
        print("\nLe modèle Gemini n'a pas pu être chargé. Impossible d'exécuter les tests.")
    else:
        # --- Test Génération Texte ---
        logging.info("\n--- Test Génération Texte ---")
        text_prompt = "Écris un court script pour une vidéo TikTok sur les bienfaits du sommeil."
        generated_script = generate_text(text_prompt)
        if generated_script:
            print("\nScript Généré:\n", generated_script)
        else:
            print("\nLa génération de script a échoué ou a été bloquée.")

        # --- Test Analyse Image ---
        logging.info("\n--- Test Analyse Image ---")
        image_prompt = "Décris en détail les objets et l'ambiance de cette image."
        if Path(sample_image_path).exists():
            image_analysis = analyze_image(image_prompt, sample_image_path)
            if image_analysis:
                print(f"\nAnalyse de l'image ({sample_image_path}):\n", image_analysis)
            else:
                print(f"\nL'analyse de l'image a échoué ou a été bloquée.")
        else:
            logging.warning(f"Fichier image d'exemple non trouvé: {sample_image_path}. Test ignoré.")

        # --- Test Analyse Vidéo ---
        logging.info("\n--- Test Analyse Vidéo ---")
        video_prompt = "Résume les actions principales qui se déroulent dans cette vidéo."
        if Path(sample_video_path).exists():
            video_analysis = analyze_video(video_prompt, sample_video_path, request_timeout=900)
            if video_analysis:
                print(f"\nAnalyse de la vidéo ({sample_video_path}):\n", video_analysis)
            else:
                print(f"\nL'analyse vidéo a échoué ou a été bloquée.")
        else:
            logging.warning(f"Fichier vidéo d'exemple non trouvé: {sample_video_path}. Test ignoré.")

    logging.info("\n--- Fin des Tests --- ") 