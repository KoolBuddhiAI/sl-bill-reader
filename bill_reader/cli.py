"""`bill-reader` command line entry point."""

import argparse


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    from bill_reader.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port)


def _models(args: argparse.Namespace) -> None:
    from bill_reader.config import get_settings
    from bill_reader.llm.check import check_profile, list_profiles

    settings = get_settings()
    rows = list_profiles(settings)
    if args.action == "list":
        for r in rows:
            print(f"{r['name']:<18} {r['provider']:<18} {r['model']:<16} {r['mode']:<9} {r['key']:<24} {r['role']}")
        return
    names = args.names or [r["name"] for r in rows]
    for name in names:
        r = check_profile(settings, name)
        print(f"{r['name']:<18} {r['model']:<16} text: {r['text']:<40} vision: {r['vision']}")


def _eval(args: argparse.Namespace) -> None:
    from pathlib import Path

    from bill_reader.config import get_settings
    from bill_reader.evaluate import evaluate, write_reports
    from bill_reader.llm import load_models_config
    from bill_reader.worker import default_ocr

    settings = get_settings()
    categorisation = args.categorisation or load_models_config(settings).categorisation
    names = [n.strip() for n in args.models.split(",")] if args.models else None
    reports = evaluate(settings, Path(args.samples_dir), names, categorisation=categorisation,
                       ocr=default_ocr()[0], progress=lambda m: print(f"  … {m}", flush=True))
    json_path = write_reports(reports, categorisation, Path(args.out), settings.data_dir / "eval")
    print(Path(args.out).read_text(encoding="utf-8"))
    print(f"Wrote {args.out} and {json_path}")


def _import_accounts(args: argparse.Namespace) -> None:
    from pathlib import Path

    from sqlmodel import Session

    from bill_reader.categorise import load_chart_csv
    from bill_reader.config import get_settings
    from bill_reader.db import make_engine

    with Session(make_engine(get_settings())) as session:
        print(f"Imported {load_chart_csv(session, Path(args.csv))} accounts")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bill-reader")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_serve)

    models = sub.add_parser("models", help="List model profiles or probe them with a test call")
    models.add_argument("action", choices=["list", "check"])
    models.add_argument("names", nargs="*", help="Profiles to check (default: all)")
    models.set_defaults(func=_models)

    ev = sub.add_parser("eval", help="Compare model profiles on the sample bills")
    ev.add_argument("samples_dir", nargs="?", default="samples")
    ev.add_argument("--models", help="Comma-separated profiles (default: every profile with an API key)")
    ev.add_argument("--categorisation", help="Profile used for account codes (default: active one)")
    ev.add_argument("--out", default="docs/eval-results.md")
    ev.set_defaults(func=_eval)

    imp = sub.add_parser("import-accounts", help="Replace the chart of accounts from an MYOB accounts CSV export")
    imp.add_argument("csv")
    imp.set_defaults(func=_import_accounts)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
