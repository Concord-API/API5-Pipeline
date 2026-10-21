import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from pipeline import config
from pipeline.load_file import manifest_path

REPOSITORY = "Concord-API/API5-Pipeline"


class PublishError(Exception):
    pass


def _subprocess_runner(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=True).stdout


def release_tag(manifest):
    extracted_on = datetime.fromisoformat(manifest["extracted_at"]).strftime("%Y%m%d")
    version = manifest["schema_version"].split("__", 1)[0]
    return f"load-{extracted_on}-{version}"


def read_manifest(load_path):
    path = manifest_path(load_path)
    if not path.exists():
        raise PublishError(f"manifesto não encontrado em {path}: gere a carga de novo")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not manifest.get("extracted_at"):
        raise PublishError("o manifesto não tem data de extração: a carga está vazia")
    return manifest


def pipeline_commit(runner):
    if runner(["git", "status", "--porcelain"]).strip():
        raise PublishError("o pipeline tem alterações não commitadas: publique de um commit")
    return runner(["git", "rev-parse", "HEAD"]).strip()


def release_exists(tag, runner):
    try:
        runner(["gh", "release", "view", tag, "--repo", REPOSITORY])
    except subprocess.CalledProcessError:
        return False
    return True


def package(load_path, tag):
    zip_path = load_path.with_name(f"ratio-{tag}.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(load_path, arcname=load_path.name)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    checksum_path = zip_path.with_name(f"{zip_path.name}.sha256")
    checksum_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8", newline="\n")
    return zip_path, checksum_path


def notes(manifest, commit):
    rows = "\n".join(f"| {table} | {count} |" for table, count in manifest["tables"].items())
    return (
        f"Carga do `dw` para a versão de schema `{manifest['schema_version']}`, "
        f"extraída em {manifest['extracted_at']}, gerada pelo pipeline no commit `{commit}`.\n\n"
        "| Tabela | Linhas |\n|---|---:|\n"
        f"{rows}\n"
    )


def publish(load_path, runner=_subprocess_runner):
    load_path = Path(load_path)
    manifest = read_manifest(load_path)
    commit = pipeline_commit(runner)
    tag = release_tag(manifest)
    if release_exists(tag, runner):
        raise PublishError(f"a release {tag} já existe: esta carga já foi publicada")
    zip_path, checksum_path = package(load_path, tag)
    runner([
        "gh", "release", "create", tag,
        str(zip_path), str(checksum_path), str(manifest_path(load_path)),
        "--repo", REPOSITORY, "--title", tag, "--notes", notes(manifest, commit),
    ])
    return tag


def main(runner=_subprocess_runner) -> int:
    config.load_env()
    try:
        tag = publish(config.load_file_path(), runner=runner)
    except PublishError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"release: {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
