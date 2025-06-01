import json
import logging
from pathlib import Path
from typing import Dict, Any
from .google_api import generate_text # Import from the local google_api module
from .config_loader import get_config
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Utilisation de r""" pour gérer les caractères spéciaux comme \ dans le JSON
# DEFAULT_PROMPT_TEMPLATE = rf""" # Incorrect car le formatage se fait plus tard
DEFAULT_PROMPT_TEMPLATE = r"""

**RÔLE** : Tu es un expert en création de contenu viral pour TikTok et un scénariste créatif. Ton objectif est de générer des scripts vidéo ultra-engageants, optimisés pour la rétention d'audience et la conversion (affiliation), en langue française.

**OBJECTIF** : Crée un script JSON détaillé pour une vidéo TikTok dynamique (format vertical 9:16) d'environ {TARGET_DURATION} secondes (donc environ 1 minute 30), centrée sur le produit '{PRODUCT_INFO}'. La vidéo doit être conçue pour devenir virale et générer des clics/ventes.

**INPUTS PRINCIPAUX** :
- Produit : {PRODUCT_INFO}
- Sujet Général / Angle : {TOPIC}
- Hook Vidéo Initial (si disponible, sinon à créer) : {HOOK_DESCRIPTION}
- Durée Cible : {TARGET_DURATION} secondes

**STRUCTURE VIDÉO & APPROCHE NARRATIVE (Choisir ou adapter la plus pertinente)** :
Le but est de raconter une micro-histoire engageante qui connecte émotionnellement avec le spectateur et le guide naturellement vers la solution ({PRODUCT_INFO}) et le CTA. La narration doit être fluide, même avec des coupes rapides.

**Option B (Narrative "Secrets Dévoilés" - Style Liste de Hacks)** :
  1. Hook : **Promesse de Valeur Exclusive / Curiosité.** Titre/Visuel/VO promettant des astuces que "peu de gens connaissent" ou "que les [modèles/experts/influenceurs] utilisent". Créer un sentiment d'urgence ou d'exclusivité ("Arrêtez de faire [erreur] !", "Le secret beauté que personne ne vous dit...").
  2. Hack/Tip 1 : **Première Révélation & Connexion Produit.** Présenter un problème courant -> Révéler le hack/solution en utilisant {PRODUCT_INFO}. Montrer visuellement la démo/l'application rapide. La VO est concise et directe ("Astuce n°1 : Utilisez {PRODUCT_INFO} pour..."). Donner un sentiment de satisfaction immédiate ("Ah, c'est donc ça ! / Facile !").
  3. Hack/Tip 2 : **Maintien de l'Intérêt / Valeur Ajoutée.** Révéler un deuxième hack rapide et utile (peut mentionner {PRODUCT_INFO} de nouveau, un produit complémentaire, ou une technique générale). Garder le rythme élevé. La VO est toujours concise ("Ensuite, faites ça...").
  4. (Optionnel) Hack/Tip 3 : **Bonus / Sur-délivrance.** Un dernier hack rapide pour renforcer la valeur perçue de la vidéo et l'expertise du créateur.
  5. Synthèse & CTA Focalisé : **Ancrage et Conversion.** Rappeler brièvement le hack le plus impactant (souvent celui avec {PRODUCT_INFO}) OU poser une question rhétorique ("Prêt(e) à essayer ?"). Faire le lien direct vers le CTA pour {PRODUCT_INFO}. La VO est persuasive ("Retrouvez tous les détails et le lien vers {PRODUCT_INFO} sur tiktokshop, click sur l'affiche du produit !"). Visuel du produit + info lien/shop.

**INSTRUCTIONS DÉTAILLÉES POUR LE JSON DE SORTIE** :

Le JSON DOIT avoir la structure suivante. NE RIEN METTRE AVANT OU APRÈS LE BLOC JSON.

Voici l'exemple d'une scéne ceci est JUSTE UN EXEMPLE :
{{
  "video_title_suggestion": "SUGGESTION DE TITRE TIKTOK ACCROCHEUR EN FRANCAIS (avec emojis si pertinent ✨)",
  "suggested_hashtags": ["#hashtag1", "#hashtagPertinent", "#produit{PRODUCT_INFO}", "#astuceBeaute", "#tiktokmademebuyit"],
  "script": "TEXTE COMPLET DE LA VOIX OFF EN FRANCAIS. Intègre le nom '{PRODUCT_INFO}' au moins 2 fois naturellement (PAS de '[nom du produit]'). Le ton doit être dynamique, engageant, et adapté à une vidéo de {TARGET_DURATION} secondes.",
  "scenes": [
    {{
      "scene_number": 1,
      "visual_type": "hook", # DOIT ÊTRE L'UN DE: "hook", "stock_video", "ai_image", "product_shot", "product_video"
      "visual_description": "FRANCAIS: Description VIVE du hook. Si {HOOK_DESCRIPTION} fourni, s'en inspirer. Sinon, créer un visuel très fort (POV, réaction choc, avant/après rapide, question intrigante). Style UGC préféré.",
      "search_keywords": ["ANGLAIS: 1-3 mots max, LARGES. Ex: 'skin problem POV', 'model walking runway', 'messy room'"], # Respecter les 3 mots MAX. Laisser vide [] si 'product_video'.
      "voiceover_text": "FRANCAIS: VO très courte et percutante pour le hook.",
      "sound_cue": "Optionnel: Suggestion SFX (ex: 'whoosh', 'sparkle', 'camera click')",
      "duration_seconds": 4 # DURÉE TRÈS COURTE : 1-3
      # product_video_filename n'est plus demandé ici par Gemini
    }},
    # --- SCÈNES DU CORPS (Adapter selon Option A ou B, mais en utilisant SEULEMENT les visual_type autorisés) ---
    {{
      "scene_number": 2,
      "visual_type": "stock_video", # DOIT ÊTRE L'UN DE: "hook", "stock_video", "ai_image", "product_shot", "product_video"
      "visual_description": "FRANCAIS: Personne montrant frustration face à [problème] (ex: 'Personne soupirant devant miroir avec acné dos'). Utiliser une vidéo stock si possible.",
      "search_keywords": ["ANGLAIS: 1-3 mots max, LARGES. Ex: 'woman back acne', 'skin frustration mirror', 'annoyed person'"], # Respecter les 3 mots MAX. Laisser vide [] si 'product_video'.
      "voiceover_text": "FRANCAIS: VO décrivant le point de douleur.",
      "sound_cue": "Optionnel: 'sigh'",
      "duration_seconds": 7 # DURÉE COURTE : 2-4
    }},
    {{
      "scene_number": 3,
      "visual_type": "product_video", # EXEMPLE DE VIDEO PRODUIT
      "visual_description": "FRANCAIS: Démonstration dynamique de {PRODUCT_INFO} en action. Montrer son efficacité.",
      "search_keywords": [], # Laisser vide pour product_video
      "voiceover_text": "FRANCAIS: VO expliquant l'action et les bénéfices visibles.",
      "sound_cue": "Optionnel: 'satisfying sound'",
      "duration_seconds": 15 # DURÉE MOYENNE : 4-7
    }},
    # ... Ajouter d'autres scènes pour atteindre la durée cible ...
    # --- SCÈNE CTA FINALE ---\
    {{
      "scene_number": "N", # Remplacer N par le numéro de scène correct
      "visual_type": "product_shot", # DOIT ÊTRE L'UN DE: "hook", "stock_video", "ai_image", "product_shot", "product_video". Montrer le produit clairement.
      "visual_description": "FRANCAIS: Packaging de {PRODUCT_INFO} bien visible, peut-être tenu en main ou sur fond propre. Texte superposé 'Lien en Bio!' peut être ajouté au montage.",
      "search_keywords": ["ANGLAIS: 1-3 mots max. Ex: 'product packaging', '{PRODUCT_INFO}', 'beauty product display'"], # Respecter les 3 mots MAX. Laisser vide [] si 'product_video'.
      "voiceover_text": "FRANCAIS: VO finale avec CTA clair et enthousiaste. Ex: 'Ne ratez pas ça ! Cliquez sur le lien en bio pour obtenir votre {PRODUCT_INFO} maintenant !'",
      "sound_cue": "Optionnel: 'ding', 'success chime'",
      "duration_seconds": 3 # DURÉE CTA LONGUE : 10-15 (Mis à 12 par défaut)
    }}
  ],
  "total_duration_estimated": "SOMME ENTIÈRE des duration_seconds (devrait être proche de {TARGET_DURATION})"
}}

**ATTENTION : RESPECTE STRICTEMENT LES DURÉES SUIVANTES POUR CHAQUE TYPE DE SCÈNE** :
- "hook" : 4 secondes (obligatoire, jamais plus ni moins)
- "stock_video" : maximum 8 secondes (jamais plus)
- "product_video" : 15 secondes (obligatoire, jamais plus ni moins)
- "product_shot" : maximum 3 secondes (jamais plus)
- "ai_image" : maximum 3 secondes (jamais plus)

Si tu ne respectes pas ces durées, la réponse sera rejetée. Chaque scène doit avoir un champ "duration_seconds" conforme à ces règles, sans exception.

**DIRECTIVES CRUCIALES POUR LES MOTS-CLÉS DE RECHERCHE (`search_keywords`)**:\
1.  **LANGUE : TOUJOURS EN ANGLAIS.** Les banques d'images fonctionnent principalement en anglais.\
2.  **NOMBRE : STRICTEMENT ET IMPÉRATIVEMENT ENTRE 1 ET 3 MOTS-CLÉS MAXIMUM PAR SCÈNE.** Ne pas dépasser 3 mots. C'est essentiel pour la recherche.\
3.  **PERTINENCE vs GÉNÉRALITÉ : PRIVILÉGIER DES TERMES PLUS LARGES ET GÉNÉRAUX**, surtout pour les problèmes/symptômes. Cela augmente MASSIVEMENT les chances de trouver des clips pertinents sur Pexels/Pixabay.\
      *   MAUVAIS (Trop spécifique) : ["toenail fungus removal close up", "onychomycosis treatment spray"] -> Peu de résultats\
      *   BON (Plus large, 1-3 mots) : ["unhealthy feet", "foot care", "spraying foot"] -> Plus de résultats\
      *   MAUVAIS : ["severe acne back scratching woman frustrated"] -> Trop long\
      *   BON (1-3 mots) : ["back skin problem", "woman scratching", "skin irritation"] \
      *   MAUVAIS : ["micellar water cleaning makeup brush deep clean technique tutorial"] -> Trop long\
      *   BON (1-3 mots) : ["cleaning makeup brush", "micellar water use", "beauty routine"]\
4.  **COHÉRENCE :** Les mots-clés doivent correspondre à l'intention visuelle décrite dans `visual_description`.\
5.  **CAS SPÉCIAL `product_video`** : Si `visual_type` est `"product_video"`, le champ `search_keywords` DOIT être une liste vide (`[]`) car la vidéo sera fournie localement par l'utilisateur via l'interface.


**AUTRES DIRECTIVES IMPORTANTES** :
- **TYPES DE VISUELS AUTORISÉS & MAPPING :** Pour le champ `visual_type`, utilise **UNIQUEMENT** les valeurs `hook`, `stock_video`, `ai_image`, `product_shot`, `product_video`.
    - Si tu décris une **démonstration du produit en action avec une vidéo fournie par l'utilisateur**, utilise `visual_type: product_video` et laisse `search_keywords: []`. L'utilisateur fournira le chemin de cette vidéo directement.
    - Si tu décris une **démonstration du produit en action et qu'une vidéo stock générique pourrait convenir**, utilise préférentiellement `visual_type: stock_video` et décris une action générique trouvable en stock.
    - Si ce n'est pas possible (ni `product_video` ni `stock_video` pour une démo), utilise `visual_type: product_shot` et décris l'action autour de l'image produit.
    - Si tu décris un écran avec des **graphiques superposés** ou un **appel à l'action final**, utilise `visual_type: product_shot` et décris le visuel autour de l'image produit.
- **DURÉE & RYTHME ({TARGET_DURATION}s) :** Pour atteindre 90s, il faudra plus de scènes ou des scènes légèrement plus longues. Garde un rythme dynamique adapté à TikTok, mais assure-toi que la **scène finale CTA (`product_shot` ou `product_video` si le CTA est une vidéo) dure entre 10 et 15 secondes**. La `total_duration_estimated` doit correspondre à la somme des durées de scènes et être proche de {TARGET_DURATION}.
- **VISUELS CLAIRS & UGC :** Prioriser les descriptions simples, directes, style "filmé rapidement avec un téléphone". Éviter le jargon complexe. `ai_image` en dernier recours.
- **TEXTE VOIX OFF :** Naturel, facile à comprendre, percutant. Intégrer `{PRODUCT_INFO}` sans que ça sonne forcé.
- **VALIDITÉ JSON :** Le format de sortie doit être un JSON parfaitement valide, sans texte additionnel avant ou après.
"""

def parse_gemini_response(response_text: str) -> Dict[str, Any] | None:
    # Try to find the JSON block
    # Use triple quotes for the multi-line raw string regex
    json_match = re.search(r'''\`\`\`json
({.*?})
\`\`\`''', response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Fallback: assume the whole string might be JSON if no ```json is found
        # More robust: try to find JSON start/end braces if possible
        start_brace = response_text.find('{')
        end_brace = response_text.rfind('}')
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            json_str = response_text[start_brace:end_brace+1]
        else: # If even braces aren't found reliably, maybe it's not JSON
             logging.error("Could not reliably locate JSON in the response.")
             return None
    
    json_str = json_str.strip()
    
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse JSON: {e}")
        logging.debug(f"Invalid JSON string received:\\n{json_str}")
        return None

    # Basic validation (adapt based on the new prompt structure)
    required_keys = ["video_title_suggestion", "suggested_hashtags", "script", "scenes", "total_duration_estimated"]
    if not all(key in data for key in required_keys):
        logging.warning(f"JSON structure missing one or more required keys: {required_keys}. Found: {list(data.keys())}")
        return None # Or handle partially? For now, require all.
        
    if not isinstance(data["scenes"], list) or not data["scenes"]:
         logging.warning("JSON 'scenes' field is not a valid non-empty list.")
         return None
         
    # Validate scenes structure (add more checks if needed)
    for i, scene in enumerate(data["scenes"]):
        # Common keys for all visual types
        scene_keys_common = ["scene_number", "visual_type", "visual_description", "voiceover_text", "duration_seconds"]
        
        # Keys specific to certain visual types
        visual_type = scene.get("visual_type")
        current_scene_keys_required = list(scene_keys_common) # Start with common keys

        if visual_type in ["hook", "stock_video", "ai_image", "product_shot"]:
            current_scene_keys_required.append("search_keywords")
        # elif visual_type == "product_video": # product_video_filename n'est plus requis ici
            # current_scene_keys_required.append("product_video_filename")
            # For product_video, search_keywords should ideally be present and empty, or absent.
            # If present, it must be a list.
        if "search_keywords" in scene and not isinstance(scene.get("search_keywords"), list):
            # Cette vérification s'applique maintenant aussi à product_video si search_keywords est présent
            logging.warning(f"Scene {i+1} (type: {visual_type}): 'search_keywords' is present but not a list.")
            return None # Make it strict
        if visual_type == "product_video" and "search_keywords" in scene and scene.get("search_keywords"): # Check if it's not an empty list for product_video
            logging.warning(f"Scene {i+1} (product_video): 'search_keywords' should be an empty list [] but found {scene.get('search_keywords')}.")
            # return None # Optionnel: être strict

        if not all(key in scene for key in current_scene_keys_required):
             logging.warning(f"Scene {i+1} (type: {visual_type}) is missing one or more required keys from {current_scene_keys_required}. Found: {list(scene.keys())}")
             # return None # Make it strict for now

        # Validate search_keywords list format if it's supposed to be there and is present
        # Modifié pour ne plus exiger search_keywords si product_video, mais s'il est là, il doit être une liste
        # if visual_type != "product_video" and "search_keywords" in scene and not isinstance(scene.get("search_keywords"), list):
        #      logging.warning(f"Scene {i+1} (type: {visual_type}) 'search_keywords' is not a list.")
        #      return None # Make it strict

        if not isinstance(scene.get("duration_seconds"), (int, float)) or scene.get("duration_seconds", 0) <= 0:
             logging.warning(f"Scene {i+1} has invalid 'duration_seconds': {scene.get('duration_seconds')}")
             return None # Duration must be positive number

    logging.info("✅ Script JSON parsed successfully from Gemini response (New Format with product_video).")
    return data

def generate_script(
    hook_description: str | None = None,
    product_info: str = "un produit générique",
    topic: str = "sujet général",
    language: str = "French", # Language is mainly for VO, but prompt assumes French for now
    target_duration_seconds: int = 25, 
) -> Dict[str, Any] | None:
    """Génère le script vidéo JSON complet en utilisant l'API Gemini avec le nouveau prompt."""
    
    hook_desc_for_prompt = hook_description if hook_description else "(Aucune description de hook fournie, créer une accroche visuelle pertinente)"
    
    # Format the new prompt template
    try:
        prompt = DEFAULT_PROMPT_TEMPLATE.format(
            PRODUCT_INFO=product_info,
            TOPIC=topic,
            HOOK_DESCRIPTION=hook_desc_for_prompt,
            TARGET_DURATION=target_duration_seconds
            # LANGUAGE is not directly used in this prompt template,
            # NUM_SCENES is also not used as the new prompt focuses on duration
        )
    except KeyError as e:
        logging.error(f"Missing key in prompt template formatting: {e}")
        return None

    logging.info(f"""Génération du script avec le prompt amélioré (Début) :
{prompt[:250]}...""")
    
    response_text = generate_text(prompt)

    if not response_text:
        logging.error("La génération de texte a échoué ou n'a retourné aucun contenu.")
        return None

    logging.info("Tentative de parsing de la réponse Gemini (Nouveau Format)...")
    script_data = parse_gemini_response(response_text)

    # Additional validation: Check if total_duration_estimated matches sum of scene durations
    if script_data:
        calculated_duration = sum(s.get("duration_seconds", 0) for s in script_data.get("scenes", []))
        estimated_duration = script_data.get("total_duration_estimated")
        if not isinstance(estimated_duration, (int, float)):
             logging.warning(f"Total estimated duration ('{estimated_duration}') is not a number.")
        elif abs(calculated_duration - estimated_duration) > 1: # Allow small float tolerance
            logging.warning(f"Total estimated duration ({estimated_duration}s) does not match sum of scene durations ({calculated_duration:.2f}s).")
            # Optionally update the total_duration_estimated field:
            # script_data["total_duration_estimated"] = round(calculated_duration) 

    return script_data

def save_script(script_data: Dict[str, Any], output_path: Path) -> None:
    """Save the script data as a JSON file."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding='utf-8') as f:
            json.dump(script_data, f, indent=2, ensure_ascii=False)
        logging.info(f"✅ Script saved to: {output_path}")
    except IOError as e:
        logging.error(f"Failed to save script to {output_path}: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while saving script: {e}")

if __name__ == '__main__':
    print(DEFAULT_PROMPT_TEMPLATE)
    logging.basicConfig(level=logging.INFO)
    print("--- Testing Script Generator (New Prompt) --- ")

    # Test Inputs
    test_hook_desc = "Personne montrant des pieds secs et craquelés."
    test_product = "Crème Réparatrice Pieds Magique"
    test_topic = "Comment se débarrasser des pieds secs rapidement"
    output_file = Path("generated_script_test_new.json")

    print("Inputs:")
    print(f"  Hook Desc: {test_hook_desc}")
    print(f"  Product: {test_product}")
    print(f"  Topic: {test_topic}")
    # print(f"  Language: French (Assumed by prompt)") # Language not a direct param for the template

    # Generate script
    script_json = generate_script(
        hook_description=test_hook_desc,
        product_info=test_product,
        topic=test_topic,
        target_duration_seconds=100 # Test with 30s target
    )

    if script_json:
        print("\n--- Generated Script Data --- ")
        print(json.dumps(script_json, indent=2, ensure_ascii=False))
        
        save_script(script_json, output_file)
        
        print(f"\nValidation:")
        print(f"  Title Suggestion: {script_json.get('video_title_suggestion', 'N/A')}")
        print(f"  Hashtags: {script_json.get('suggested_hashtags', 'N/A')}")
        print(f"  Number of scenes: {len(script_json.get('scenes', []))}")
        print(f"  Total estimated duration: {script_json.get('total_duration_estimated', 'N/A')}")
        # Verify duration calculation
        calculated_duration = sum(s.get("duration_seconds", 0) for s in script_json.get('scenes', []))
        print(f"  Sum of scene durations: {calculated_duration:.2f}s")
    else:
        print("\nScript generation failed.")

    print("--- End Test --- ")
    # if output_file.exists(): os.remove(output_file) 