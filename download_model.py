import os

from huggingface_hub import snapshot_download


def download_model(target_dir="./models"):
    model_id = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
    print(f"Downloading {model_id} to {target_dir}...")
    
    # Ensure directory exists
    os.makedirs(target_dir, exist_ok=True)
    
    snapshot_download(
        repo_id=model_id,
        local_dir=os.path.join(target_dir, model_id),
        local_dir_use_symlinks=False
    )
    print("Download complete.")

if __name__ == "__main__":
    download_model()
