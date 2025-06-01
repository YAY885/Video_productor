import streamlit as st
from pathlib import Path
import tempfile
import os
import sys
import logging
import csv
import time

# Assurez-vous que le répertoire parent (racine du projet) est dans le PYTHONPATH
# pour que l'import de 'main' fonctionne correctement.
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))

# Importer la fonction principale du pipeline
# Il faut s'assurer que main.py est structuré pour permettre cet import
# et ne lance pas le pipeline directement lors de l'import.
# La vérification if __name__ == "__main__": dans main.py est cruciale.
try:
    # Assumons que run_pipeline est bien dans main.py
    from main import run_pipeline 
except ImportError as e:
    st.error(f"Erreur d'importation: Assurez-vous que streamlit_app.py est à la racine du projet et que main.py existe. Détails: {e}")
    st.stop() # Arrête l'exécution de l'app Streamlit

# Configuration du logging (optionnel mais utile pour le debug via console)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

st.set_page_config(layout="wide")
st.title("🎬 Générateur de Vidéo TikTok (Productor)")
st.markdown("Interface pour lancer le pipeline de génération de vidéos.")

# --- Sélection du mode ---
mode = st.radio("Mode d'utilisation", ["Unitaire", "Bulk (CSV)"])

if mode == "Unitaire":
    # --- Formulaire pour les inputs ---
    with st.form("video_generation_form"):
        st.header("Paramètres de la Vidéo")

        # --- Inputs requis ---
        col1, col2 = st.columns(2)
        with col1:
            project_name = st.text_input("Nom du Projet*", help="Nom unique pour ce projet vidéo (sera utilisé comme nom de dossier).")
            hook_video_file = st.file_uploader("Vidéo Hook*", type=["mp4", "mov", "avi"], help="Fichier vidéo court servant d'accroche.")
        with col2:
            product_info = st.text_input("Nom/Info Produit*", help="Nom ou description courte du produit.")
            product_image_file = st.file_uploader("Image Produit (Optionnel)", type=["png", "jpg", "jpeg"], help="Image du produit à inclure.")

        # --- Nouveaux champs pour vidéo produit --- 
        st.subheader("Vidéo Produit (Optionnel)") # Ajout d'un sous-titre pour la clarté
        product_video_file = st.file_uploader("Fichier Vidéo Produit", type=["mp4", "mov", "avi"], help="Votre propre vidéo de démonstration du produit.")

        # --- Inputs Optionnels --- (Déplacés pour regroupement logique)
        st.subheader("Paramètres Avancés (Optionnel)")
        topic = st.text_area("Sujet/Contexte", help="Description plus détaillée du sujet pour guider la génération du script.")
        language = st.text_input("Langue", value="French", help="Langue pour le script et la voix off (ex: French, English).")

        # --- Bouton de soumission ---
        submitted = st.form_submit_button("🚀 Générer la Vidéo")

    # --- Traitement après soumission ---
    if submitted:
        # Validation des inputs requis
        if not project_name:
            st.error("Veuillez fournir un nom de projet.")
        elif not hook_video_file:
            st.error("Veuillez uploader une vidéo hook.")
        elif not product_info:
            st.error("Veuillez fournir le nom ou l'info du produit.")
        else:
            # Créer des répertoires temporaires sécurisés pour les fichiers uploadés
            temp_dir = tempfile.mkdtemp()
            hook_video_path_temp = None
            product_image_path_temp = None
            product_video_path_temp = None # Pour la vidéo produit
            final_video_path_result = None # Pour stocker le chemin retourné

            try:
                # Sauvegarder la vidéo hook
                hook_video_path_temp = Path(temp_dir) / hook_video_file.name
                with open(hook_video_path_temp, "wb") as f:
                    f.write(hook_video_file.getbuffer())
                st.info(f"Vidéo hook sauvegardée temporairement : {hook_video_path_temp}")

                # Sauvegarder l'image produit si elle existe
                if product_image_file:
                    product_image_path_temp = Path(temp_dir) / product_image_file.name
                    with open(product_image_path_temp, "wb") as f:
                        f.write(product_image_file.getbuffer())
                    st.info(f"Image produit sauvegardée temporairement : {product_image_path_temp}")
                
                # Sauvegarder la vidéo produit si elle existe
                if product_video_file:
                    product_video_path_temp = Path(temp_dir) / product_video_file.name
                    with open(product_video_path_temp, "wb") as f:
                        f.write(product_video_file.getbuffer())
                    st.info(f"Vidéo produit sauvegardée temporairement : {product_video_path_temp}")

                # Afficher un message pendant l'exécution
                with st.spinner(f"Génération de la vidéo '{project_name}' en cours... Veuillez patienter."):
                    st.info("Lancement du pipeline principal...")
                    # Appeler la fonction principale du pipeline
                    
                    success_status_or_path = run_pipeline(
                        project_name=project_name,
                        hook_video=str(hook_video_path_temp),
                        product_info=product_info,
                        product_image=str(product_image_path_temp) if product_image_path_temp else None,
                        product_video_path=str(product_video_path_temp) if product_video_path_temp else None, # Nouveau
                        topic=topic,
                        language=language
                    )
                    
                    final_video_path_result = None
                    pipeline_succeeded = False

                    if success_status_or_path and isinstance(success_status_or_path, (str, Path)) and Path(success_status_or_path).exists():
                        final_video_path_result = Path(success_status_or_path)
                        pipeline_succeeded = True
                        st.success(f"🎉 Pipeline terminé avec succès pour '{project_name}' !")
                    elif success_status_or_path: # Cas où run_pipeline retourne True
                        pipeline_succeeded = True
                        st.success(f"🎉 Pipeline terminé avec succès pour '{project_name}' ! (Vérifiez le dossier du projet)")
                        guessed_path = Path(project_name) / "output" / "final_video_with_captions.mp4"
                        if guessed_path.exists():
                            final_video_path_result = guessed_path
                    else:
                         st.error("Le pipeline a rencontré une erreur. Vérifiez la console/logs pour les détails.")

                # Afficher la vidéo et le bouton de téléchargement si réussi
                if final_video_path_result:
                    st.info(f"Chemin de la vidéo finale : {final_video_path_result}")
                    try:
                        video_file = open(final_video_path_result, 'rb')
                        video_bytes = video_file.read()
                        st.video(video_bytes)
                        
                        st.download_button(
                             label="Télécharger la vidéo",
                             data=video_bytes,
                             file_name=final_video_path_result.name,
                             mime='video/mp4'
                        )
                        video_file.close()
                    except FileNotFoundError:
                         st.error(f"Impossible de trouver le fichier vidéo généré à : {final_video_path_result}")
                    except Exception as e:
                         st.error(f"Erreur lors de la lecture ou de l'affichage de la vidéo : {e}")

            except Exception as e:
                st.error(f"Une erreur est survenue lors de l'exécution du pipeline : {e}")
                logging.error("Erreur Streamlit lors de l'appel du pipeline", exc_info=True)
            finally:
                # Nettoyer les fichiers temporaires
                if hook_video_path_temp and hook_video_path_temp.exists():
                    try:
                        os.remove(hook_video_path_temp)
                    except PermissionError as pe:
                        st.warning(f"Impossible de supprimer le fichier temporaire hook ({hook_video_path_temp.name}) car il est encore utilisé : {pe}. Il sera supprimé plus tard.")
                    except Exception as e:
                        st.warning(f"Erreur lors de la suppression du fichier hook temporaire: {e}")
                if product_image_path_temp and product_image_path_temp.exists():
                    try:
                        os.remove(product_image_path_temp)
                    except Exception as e: # Peut aussi arriver pour les images ? Moins probable.
                         st.warning(f"Erreur lors de la suppression du fichier image temporaire: {e}")
                if product_video_path_temp and product_video_path_temp.exists():
                    try:
                        os.remove(product_video_path_temp)
                    except Exception as e:
                        st.warning(f"Erreur lors de la suppression du fichier vidéo produit temporaire: {e}")
                # Supprimer le répertoire temporaire lui-même
                try:
                    os.rmdir(temp_dir)
                    st.info("Nettoyage du répertoire temporaire terminé.")
                except OSError as e:
                     # Souvent normal si les fichiers n'ont pas pu être supprimés avant
                     logging.warning(f"Impossible de supprimer le répertoire temporaire {temp_dir} (peut être normal si fichiers encore présents): {e}")

elif mode == "Bulk (CSV)":
    st.header("Mode Bulk : Génération de plusieurs vidéos à partir d'un CSV")
    st.markdown("""
    <ul>
    <li>Le CSV doit contenir au minimum les colonnes suivantes : <b>nom_projet, nom_produit, hook_video_path, product_image, topic, language, product_video_path</b> (les colonnes optionnelles peuvent être laissées vides).</li>
    <li>Les chemins de fichiers (vidéos, images) doivent être accessibles depuis le serveur où tourne ce script.</li>
    </ul>
    """, unsafe_allow_html=True)
    csv_file = st.file_uploader("Uploader le fichier CSV de configuration des vidéos", type=["csv"])
    lancer_bulk = st.button("🚀 Lancer la génération en mode Bulk")

    if csv_file and lancer_bulk:
        temp_dir = tempfile.mkdtemp()
        csv_path = Path(temp_dir) / csv_file.name
        with open(csv_path, "wb") as f:
            f.write(csv_file.getbuffer())
        st.info(f"CSV sauvegardé temporairement : {csv_path}")
        results = []
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            total = sum(1 for _ in open(csv_path, encoding='utf-8')) - 1
            f.seek(0)
            st.progress(0)
            for i, row in enumerate(reader):
                st.write(f"--- Génération de la vidéo {i+1}/{total} : {row.get('nom_projet','(nom inconnu)')}")
                try:
                    res = run_pipeline(
                        project_name=row.get('nom_projet','bulk_project'),
                        hook_video=row.get('hook_video_path',''),
                        product_info=row.get('nom_produit',''),
                        product_image=row.get('product_image', None) or None,
                        topic=row.get('topic', ''),
                        language=row.get('language', 'French'),
                        product_video_path=row.get('product_video_path', None) or None
                    )
                    results.append({"projet": row.get('nom_projet'), "status": "OK", "video": str(res) if res else None})
                    st.success(f"Vidéo générée pour {row.get('nom_projet')}")
                except Exception as e:
                    results.append({"projet": row.get('nom_projet'), "status": f"Erreur: {e}", "video": None})
                    st.error(f"Erreur pour {row.get('nom_projet')} : {e}")
                st.progress((i+1)/total)
                # Ajout d'une pause de 1 minute entre chaque vidéo sauf la dernière
                if i < total - 1:
                    st.info("Pause de 1 minute avant la prochaine vidéo...")
                    time.sleep(60)
        st.write("\n--- Récapitulatif ---")
        st.dataframe(results)
        st.success("Mode bulk terminé !")
        try:
            os.remove(csv_path)
            os.rmdir(temp_dir)
        except Exception:
            pass