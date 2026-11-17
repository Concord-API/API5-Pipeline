import io
import json
import zipfile


def _records(content):
    return json.loads(content.decode("utf-8-sig"))


def _has_id(record):
    return isinstance(record.get("id"), str) and record["id"].strip() != ""


def parse_rulings(name, content):
    if name.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            records = [
                record
                for member in sorted(archive.namelist())
                if member.lower().endswith(".json")
                for record in _records(archive.read(member))
            ]
    else:
        records = _records(content)
    return [record for record in records if _has_id(record)]
