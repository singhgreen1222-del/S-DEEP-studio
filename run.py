#!/usr/bin/env python3
"""python run.py daily|weekly|dryrun"""
import sys
import pipeline as P

mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
s = P.load()
{"daily": P.produce, "weekly": P.weekly, "dryrun": P.dryrun}[mode](s)
if mode == "daily":  # report bhi taaza rakho
    import analytics
    analytics.write_report(s, analytics.table(s), analytics.group_stats(analytics.table(s)))
