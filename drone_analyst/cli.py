"""Command line interface:  python -m drone_analyst <command>"""
from __future__ import annotations

import argparse
import time

from .agent import SecurityAnalystAgent
from .indexer import FrameIndex
from .models import Severity
from .simulator import read_feed, write_feed

RED, YEL, DIM, END = "\033[91m", "\033[93m", "\033[2m", "\033[0m"


def _agent(db: str, reset: bool = False) -> SecurityAnalystAgent:
    return SecurityAnalystAgent(FrameIndex(db, reset=reset))


def cmd_simulate(a):
    n = write_feed(a.out, date=a.date, seed=a.seed)
    print(f"Wrote {n} simulated frames to {a.out}")


def cmd_run(a):
    agent = _agent(a.db, reset=True)
    color = not a.no_color

    def show(res):
        f = res.frame
        t = f.telemetry
        if not a.quiet:
            print(f"{DIM if color else ''}Frame {f.frame_id:>3} | {f.hhmm} | {t.location:<15} | alt {t.altitude_m:>4.0f}m "
                  f"| batt {t.battery_pct:>3.0f}% | {f.description}{END if color else ''}")
            for line in res.logs:
                print(f"    LOG   {line}")
        for al in res.alerts:
            c = (RED if al.severity >= Severity.HIGH else YEL) if color else ""
            print(f"    {c}ALERT {al}{END if color else ''}")
        if a.delay:
            time.sleep(a.delay)

    n = agent.ingest_many(read_feed(a.feed), show)
    print(f"\nProcessed {n} frames -> {a.db}")
    print("\n=== SUMMARY ===\n" + agent.summary())


def cmd_ask(a):
    print(_agent(a.db).ask(a.question).text)


def cmd_chat(a):
    agent = _agent(a.db)
    print("Ask about the video (blank line to quit). e.g. 'show all truck events'")
    while (q := input("> ").strip()):
        print(agent.ask(q).text, "\n")


def cmd_summary(a):
    print(_agent(a.db).summary())


def cmd_query(a):
    idx = FrameIndex(a.db)
    tod = (a.start, a.end) if a.start and a.end else (None, None)
    for f in idx.frames(tod_start=tod[0], tod_end=tod[1], obj=a.object, location=a.location, limit=a.limit):
        print(f"{f['ts'][11:19]} @{f['location']}: {f['description']}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="drone_analyst", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("simulate"); s.add_argument("--out", default="data/sample_feed.jsonl")
    s.add_argument("--date", default="2026-11-24"); s.add_argument("--seed", type=int, default=7); s.set_defaults(fn=cmd_simulate)
    r = sub.add_parser("run"); r.add_argument("--feed", default="data/sample_feed.jsonl")
    r.add_argument("--db", default="output/drone.db"); r.add_argument("--delay", type=float, default=0.0)
    r.add_argument("--quiet", action="store_true"); r.add_argument("--no-color", action="store_true"); r.set_defaults(fn=cmd_run)
    for name, fn in (("ask", cmd_ask), ("chat", cmd_chat), ("summary", cmd_summary)):
        q = sub.add_parser(name); q.add_argument("--db", default="output/drone.db")
        if name == "ask": q.add_argument("question")
        q.set_defaults(fn=fn)
    q = sub.add_parser("query"); q.add_argument("--db", default="output/drone.db")
    q.add_argument("--object"); q.add_argument("--location"); q.add_argument("--start", help="HH:MM")
    q.add_argument("--end", help="HH:MM"); q.add_argument("--limit", type=int, default=50); q.set_defaults(fn=cmd_query)
    a = p.parse_args(argv)
    a.fn(a)
