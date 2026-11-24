"""Copie de secours des sources brutes sur le stockage S3 (MinIO) du SSP Cloud."""

import hashlib
import json
import os


def open_backup(config, snapshot_id):
    """Ouvrir le stockage S3 ; retourner None si la copie de secours est inactive ou injoignable."""
    settings = config.get("s3_backup", {})
    path = os.environ.get("S3_BACKUP_PATH") or settings.get("path")
    if not settings.get("enabled", False) or not path:
        print("Copie de secours S3 désactivée : bloc 's3_backup' absent, 'enabled' faux ou 'path' vide dans config/sources.json.")
        return None
    try:
        import s3fs

        # Sur le SSP Cloud, les identifiants sont déjà dans les variables AWS_*.
        endpoint = os.environ.get("AWS_S3_ENDPOINT", "minio.lab.sspcloud.fr")
        if not endpoint.startswith("http"):
            endpoint = "https://" + endpoint
        # Sans identifiants, lecture anonyme : suffisant pour un dossier rendu public.
        anonymous = not os.environ.get("AWS_ACCESS_KEY_ID")
        fs = s3fs.S3FileSystem(anon=anonymous, client_kwargs={"endpoint_url": endpoint})
        folder = path.strip("/") + "/" + snapshot_id
        # Lire un fichier ne demande pas le droit de lister le dossier (refusé aux autres utilisateurs).
        fs.exists(folder + "/manifest.json")  # échoue tout de suite si les identifiants ont expiré
    except Exception as error:
        print(f"Copie de secours S3 indisponible ({type(error).__name__} : {error}).")
        return None
    return fs, folder


def read_remote_manifest(backup):
    """Lire la provenance enregistrée sur S3 (vide si l'instantané n'y est pas encore)."""
    fs, folder = backup
    path = folder + "/manifest.json"
    if not fs.exists(path):
        return {"files": {}}
    return json.loads(fs.cat_file(path).decode("utf-8"))


def restore_file(backup, remote_manifest, source):
    """Récupérer une source sur S3 et vérifier son empreinte ; None si elle n'y est pas."""
    fs, folder = backup
    entry = remote_manifest["files"].get(source["id"])
    path = folder + "/" + source["filename"]
    if entry is None or not fs.exists(path):
        print(f"Copie S3 introuvable : {path} (entrée au manifeste : {entry is not None}).")
        return None
    assert entry["download_url"] == source["url"], "Adresse modifiée : créer un nouvel instantané."
    content = fs.cat_file(path)
    assert hashlib.sha256(content).hexdigest() == entry["sha256"], f"Copie S3 modifiée : {source['filename']}."
    return content, entry


def save_missing_files(backup, local_folder, manifest, remote_manifest, sources):
    """Envoyer sur S3 les fichiers absents ; ne jamais écraser une copie déjà enregistrée."""
    fs, folder = backup
    sent = 0
    for source in sources:
        remote_path = folder + "/" + source["filename"]
        if fs.exists(remote_path):
            continue
        entry = manifest["files"][source["id"]]
        content = (local_folder / source["filename"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == entry["sha256"], f"Fichier local modifié : {source['filename']}."
        fs.pipe_file(remote_path, content)
        remote_manifest["files"][source["id"]] = entry
        sent += 1
    if sent:
        remote_manifest["snapshot_id"] = manifest["snapshot_id"]
        text = json.dumps(remote_manifest, ensure_ascii=False, indent=2) + "\n"
        fs.pipe_file(folder + "/manifest.json", text.encode("utf-8"))
    return sent