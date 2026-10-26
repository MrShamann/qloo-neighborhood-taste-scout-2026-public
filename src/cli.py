import argparse
import json
from .taste_scout import fixture, live_flow, offline_flow, GuardError


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--live",action="store_true")
    args=p.parse_args()
    try:
        result=live_flow(fixture()) if args.live else offline_flow(fixture())
    except GuardError as exc:
        print(json.dumps({"state":"BLOCKED","reason":str(exc)}))
        return 2
    print(json.dumps(result,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
