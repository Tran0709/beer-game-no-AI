"""One-time setup: makes the project a git repo with the three environments (dev, test, main = live).
Safe to run again: it only creates what is missing.     python ai-maintenance/agent/setup_repo.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import *

def main():
    gb = cfg()["git"]; dev, test, live = gb["dev_branch"], gb["test_branch"], gb["live_branch"]
    inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=REPO, capture_output=True, text=True).returncode == 0
    if not inside:
        git("init", "-q", "-b", live); print("Created a new git repository in", REPO)
    if not git("config", "user.name", check=False): git("config", "user.name", "Beer Game maintainer")
    if not git("config", "user.email", check=False): git("config", "user.email", "maintainer@localhost")
    if not git("rev-parse", "--verify", "-q", "HEAD", check=False):
        git("add", "-A"); git("commit", "-q", "-m", "Initial commit"); print("Made the first commit.")
    elif git("status", "--porcelain", "--", ".", ":!ai-maintenance"):
        print("NOTE: you have uncommitted changes. Commit them first (git add -A && git commit -m ...), then run this again.")
    base = live if git("rev-parse", "--verify", "-q", live, check=False) else git("rev-parse", "--abbrev-ref", "HEAD")
    for b in (dev, test):
        if not git("rev-parse", "--verify", "-q", b, check=False):
            git("branch", b, base); print("Created branch", b)
    git("checkout", "-q", dev)
    print("\nReady. Environments: %s (development), %s (digital twin), %s (live). You are now on %s." % (dev, test, live, dev))
    print("Try the weekly run:  python ai-maintenance/agent/maintain.py weekly")

if __name__ == "__main__": main()
