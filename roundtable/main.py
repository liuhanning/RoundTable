"""
RoundTable CLI entrypoint.
"""
from utils.console_encoding import configure_utf8_console

configure_utf8_console()

from cli.main import main

if __name__ == "__main__":
    main()
