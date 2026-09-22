"""
Share the dashboard on a temporary public URL.

Nothing is deployed. Streamlit keeps running on this machine, ngrok opens a
tunnel, and traffic to a public https address is forwarded to localhost -
so the data stays here and only the pages people request travel out.

    python share.py

One-off setup, a free ngrok account:

    1. Sign up at https://dashboard.ngrok.com/signup
    2. Copy the authtoken from Getting Started > Your Authtoken
    3. setx NGROK_AUTHTOKEN "<your token>"      (then open a new terminal)

Stop with Ctrl+C. The tunnel closes with the script and the URL stops
working immediately - it is also a new URL every run, unless you claim the
free static domain an ngrok account comes with and pass it as
--domain <name>.ngrok-free.app.

ANYONE WITH THE URL CAN OPEN THE DASHBOARD. There is no login in front of
it, and the address is guessable in the sense that it is not a secret once
you have sent it to someone. Share it with people who should see the SAT
figures, and stop the script when the meeting is over.
"""

import argparse
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

APP = Path(__file__).parent / "app.py"
DEFAULT_PORT = 8501

# How long to wait for a Streamlit we started to begin serving.
STARTUP_TIMEOUT = 60


def is_serving(port):
    """True if something is already listening on the port."""

    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def start_streamlit(port):
    """
    Launch the app, and return the process so it can be stopped again.

    Returns None when Streamlit is already running on the port - then the
    tunnel just points at the server that is already there, and this script
    leaves it alone on the way out.
    """

    if is_serving(port):
        print(f"Streamlit is already serving on port {port}; using it.")
        return None

    print(f"Starting Streamlit on port {port}...")

    process = subprocess.Popen([
        sys.executable, "-m", "streamlit", "run", str(APP),
        "--server.port", str(port),
        "--server.headless", "true",
    ])

    deadline = time.time() + STARTUP_TIMEOUT

    while time.time() < deadline:
        if is_serving(port):
            return process
        if process.poll() is not None:
            raise SystemExit("Streamlit exited before it started serving.")
        time.sleep(0.5)

    process.terminate()
    raise SystemExit(
        f"Streamlit did not start within {STARTUP_TIMEOUT}s. Try running it "
        "on its own first: python -m streamlit run app.py"
    )


def open_tunnel(port, domain=None):
    """Open the ngrok tunnel and return it."""

    from pyngrok import conf, ngrok
    from pyngrok.exception import PyngrokError

    # ngrok's own process logs its failures as a wall of ERROR lines, which
    # buries the one-line explanation below. The message is re-raised with
    # the underlying text, so nothing is actually lost.
    logging.getLogger("pyngrok").setLevel(logging.CRITICAL)

    token = os.getenv("NGROK_AUTHTOKEN")

    if token:
        ngrok.set_auth_token(token)

    # Without this pyngrok logs the whole ngrok process output over the URL
    # we are trying to make easy to read.
    conf.get_default().log_event_callback = None

    options = {"addr": port, "proto": "http"}

    if domain:
        options["domain"] = domain

    try:
        return ngrok.connect(**options)

    except PyngrokError as error:
        message = str(error)

        if "ERR_NGROK_4018" in message or "authtoken" in message.lower():
            raise SystemExit(
                "ngrok needs a free authtoken before it will open a tunnel.\n"
                "  1. Sign up at https://dashboard.ngrok.com/signup\n"
                "  2. Copy your token from Getting Started > Your Authtoken\n"
                '  3. setx NGROK_AUTHTOKEN "<your token>"\n'
                "  4. Open a new terminal and run this again."
            )

        raise SystemExit(
            f"Could not open the tunnel: {message}\n\n"
            "If this is a download or connection error, the corporate network "
            "may be blocking ngrok. The Network URL that Streamlit prints on "
            "startup already works for anyone on the same network."
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--domain",
        help="a static ngrok domain, e.g. my-name.ngrok-free.app, so the URL "
             "is the same every run",
    )
    args = parser.parse_args()

    streamlit = start_streamlit(args.port)

    try:
        tunnel = open_tunnel(args.port, args.domain)
    except SystemExit:
        # Started for a share that is not happening - don't leave it behind.
        if streamlit is not None:
            streamlit.terminate()
        raise

    print()
    print("=" * 68)
    print("  Share this URL:", tunnel.public_url)
    print("=" * 68)
    print()
    print("  Anyone with the link can open the dashboard - there is no login.")
    print("  First-time visitors see an ngrok warning page; they click")
    print("  'Visit Site' once to continue.")
    print()
    print("  Ctrl+C to stop sharing.")
    print()

    try:
        # Nothing to do but hold the tunnel open. The work happens in the
        # Streamlit process and in ngrok's.
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nClosing the tunnel...")

    finally:
        from pyngrok import ngrok

        ngrok.disconnect(tunnel.public_url)
        ngrok.kill()

        # Only stop Streamlit if this script was the one that started it.
        if streamlit is not None:
            streamlit.terminate()

        print("Stopped. The URL no longer works.")


if __name__ == "__main__":
    main()
