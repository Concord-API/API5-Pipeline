import argparse
import sys

import requests

from pipeline import doaj, harvest_doctrine


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m pipeline.harvest_doaj")
    parser.add_argument("--term", action="append")
    parser.add_argument("--year", action="append", type=int)
    return parser.parse_args(argv)


def main(argv=None, session_factory=requests.Session, collect_fn=doaj.collect):
    args = parse_args(sys.argv[1:] if argv is None else argv)

    def collect(session, cursor):
        return collect_fn(
            session,
            cursor,
            terms=args.term,
            years=args.year,
            on_bucket=lambda term, year, changed: print(
                f"{term} / {year}: {changed} new or updated articles", flush=True
            ),
        )

    return harvest_doctrine.run(collect, doaj.DOAJError, "DOAJ", session_factory)


if __name__ == "__main__":
    sys.exit(main())
