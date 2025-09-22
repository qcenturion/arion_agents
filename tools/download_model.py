"""Downloads a SentenceTransformer model to a specified local cache directory.

Usage:
    python tools/download_model.py <model_name> --cache-dir <path>
"""
import argparse
import logging
from pathlib import Path
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def download_model(model_name: str, cache_dir: Path):
    """Downloads the specified model to the cache directory."""
    logging.info(f"Starting download of model '{model_name}'...")
    logging.info(f"This may take a while depending on model size and network speed.")
    logging.info(f"Cache directory: {cache_dir.resolve()}")

    try:
        SentenceTransformer(model_name, cache_folder=str(cache_dir))
        logging.info(f"Successfully downloaded and cached model '{model_name}'.")
    except Exception as e:
        logging.error(f"Failed to download model '{model_name}': {e}", exc_info=True)
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download a SentenceTransformer model.")
    parser.add_argument("model_name", type=str, help="The name of the model to download (e.g., 'BAAI/bge-large-en').")
    parser.add_argument("--cache-dir", type=Path, default=Path(".model_cache"), help="The directory to cache the model in.")
    args = parser.parse_args()

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    download_model(args.model_name, args.cache_dir)
