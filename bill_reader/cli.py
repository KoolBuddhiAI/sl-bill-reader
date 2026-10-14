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

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
