import argparse
import sys

import requests

from pipeline import harvest_doctrine, scielo


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m pipeline.harvest_scielo")
    parser.add_argument("--issn", action="append")
    return parser.parse_args(argv)


def main(argv=None, session_factory=requests.Session, collect_fn=scielo.collect):
    args = parse_args(sys.argv[1:] if argv is None else argv)

    def collect(session, cursor):
        return collect_fn(
            session,
            cursor,
            issns=args.issn,
            on_journal=lambda issn, found, updated: print(
                f"{issn}: {found} articles, {updated} new or updated", flush=True
            ),
        )

    return harvest_doctrine.run(collect, scielo.SciELOError, "SciELO", session_factory)


if __name__ == "__main__":
    sys.exit(main())
