"""Run the browser-based UI development server."""

from src.web.app import run


def main() -> None:
    run(host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
