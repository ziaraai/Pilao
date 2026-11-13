import argparse
import time

from tests.fixtures.fake_atexo import serve

parser = argparse.ArgumentParser(description="Fausse plateforme Atexo (tests et parcours).")
parser.add_argument("--port", type=int, default=8765)
parser.add_argument("--deny-robots", action="store_true")
args = parser.parse_args()
server, _ = serve(args.port, args.deny_robots)
print(f"fake Atexo on http://127.0.0.1:{server.server_address[1]}", flush=True)
while True:
    time.sleep(3600)
