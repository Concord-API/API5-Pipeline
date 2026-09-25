import argparse
import sys

import requests

from pipeline import harvest_doctrine, oai


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m pipeline.harvest_oai")
    parser.add_argument("--repository", action="append")
    return parser.parse_args(argv)


def main(argv=None, session_factory=requests.Session, collect_fn=oai.collect):
    args = parse_args(sys.argv[1:] if argv is None else argv)

    def report(name, found, changed, disabled_reason=None):
        if disabled_reason:
            print(f"{name}: skipped ({disabled_reason})", flush=True)
        else:
            print(f"{name}: {found} articles, {changed} new or updated", flush=True)

    def collect(session, cursor):
        return collect_fn(
            session,
            cursor,
            repositories=args.repository,
            on_repository=report,
        )

    return harvest_doctrine.run(collect, oai.OAIError, "OAI-PMH", session_factory)


if __name__ == "__main__":
    sys.exit(main())
