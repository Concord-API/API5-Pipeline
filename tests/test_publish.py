import hashlib
import json
import subprocess
import zipfile

import pytest

from pipeline.publish import PublishError, main, publish, release_tag

MANIFEST = {
    "schema_version": "V016__add_strength_settings.sql",
    "extracted_at": "2026-10-01T12:00:00+00:00",
    "tables": {"dim_court": 3, "fact_case_event": 120},
}
TAG = "load-20261001-V016"
COMMIT = "4acd4db9f1c2e3d4b5a6978812345678abcdef01"


class FakeGh:
    def __init__(self, existing=(), changes=""):
        self.calls = []
        self.existing = set(existing)
        self.changes = changes

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[:2] == ["git", "rev-parse"]:
            return f"{COMMIT}\n"
        if argv[:2] == ["git", "status"]:
            return self.changes
        if argv[:3] == ["gh", "release", "view"]:
            if argv[3] in self.existing:
                return TAG
            raise subprocess.CalledProcessError(1, argv)
        return ""

    def created(self):
        return [call for call in self.calls if call[:3] == ["gh", "release", "create"]]


@pytest.fixture
def load_file(tmp_path):
    path = tmp_path / "ratio-load.sql"
    path.write_bytes(b"BEGIN;\nCOMMIT;\n")
    (tmp_path / "ratio-load.manifest.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    return path


def test_release_tag_combines_the_extraction_date_and_the_schema_version():
    assert release_tag(MANIFEST) == TAG


def test_publish_creates_the_release_with_the_zip_its_checksum_and_the_manifest(load_file):
    gh = FakeGh()

    tag = publish(load_file, runner=gh)

    zip_path = load_file.with_name(f"ratio-{TAG}.zip")
    checksum_path = load_file.with_name(f"ratio-{TAG}.zip.sha256")
    manifest_path = load_file.with_name("ratio-load.manifest.json")
    create = gh.created()[0]
    assert tag == TAG
    assert create[:4] == ["gh", "release", "create", TAG]
    assert create[4:7] == [str(zip_path), str(checksum_path), str(manifest_path)]
    assert create[create.index("--repo") + 1] == "Concord-API/API5-Pipeline"
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.read("ratio-load.sql") == b"BEGIN;\nCOMMIT;\n"
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert checksum_path.read_text(encoding="utf-8") == f"{digest}  {zip_path.name}\n"


def test_publish_writes_the_version_the_extraction_date_and_the_counts_in_the_notes(load_file):
    gh = FakeGh()

    publish(load_file, runner=gh)

    create = gh.created()[0]
    notes = create[create.index("--notes") + 1]
    assert "V016__add_strength_settings.sql" in notes
    assert "2026-10-01T12:00:00+00:00" in notes
    assert "| fact_case_event | 120 |" in notes


def test_publish_refuses_a_load_without_extraction_date(load_file):
    empty = dict(MANIFEST, extracted_at=None)
    load_file.with_name("ratio-load.manifest.json").write_text(json.dumps(empty), encoding="utf-8")
    gh = FakeGh()

    with pytest.raises(PublishError, match="data de extração"):
        publish(load_file, runner=gh)

    assert gh.created() == []


def test_publish_does_not_overwrite_an_existing_release(load_file):
    gh = FakeGh(existing={TAG})

    with pytest.raises(PublishError, match="já existe"):
        publish(load_file, runner=gh)

    assert gh.created() == []


def test_publish_requires_the_manifest_beside_the_load_file(load_file):
    load_file.with_name("ratio-load.manifest.json").unlink()

    with pytest.raises(PublishError, match="manifesto"):
        publish(load_file, runner=FakeGh())


def test_main_publishes_the_load_file_from_the_settings(load_file, monkeypatch, capsys):
    monkeypatch.setenv("LOAD_FILE_PATH", str(load_file))

    exit_code = main(runner=FakeGh())

    assert exit_code == 0
    assert TAG in capsys.readouterr().out


def test_main_reports_a_refused_publication(load_file, monkeypatch, capsys):
    monkeypatch.setenv("LOAD_FILE_PATH", str(load_file))

    exit_code = main(runner=FakeGh(existing={TAG}))

    assert exit_code == 1
    assert "já existe" in capsys.readouterr().err


def test_publish_records_the_pipeline_commit_in_the_notes(load_file):
    gh = FakeGh()

    publish(load_file, runner=gh)

    create = gh.created()[0]
    assert COMMIT in create[create.index("--notes") + 1]


def test_publish_refuses_a_pipeline_with_uncommitted_changes(load_file):
    gh = FakeGh(changes=" M pipeline/run.py\n")

    with pytest.raises(PublishError, match="não commitadas"):
        publish(load_file, runner=gh)

    assert gh.created() == []
