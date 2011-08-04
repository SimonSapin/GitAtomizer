#!/usr/bin/env python
# coding: utf8

import collections

from dulwich.repo import Repo


def get_all_branches(repo):
    """
    Return the hash of each local branch.
    """
    return repo.refs.as_dict('refs/heads').values()


def get_latest_commits(repo, max_count=10, heads=None):
    """
    Return Commit objects for the `max_count` latest commits in branches
    `heads` (defaults to all local branches).
    """
    if heads is None:
        heads = get_all_branches(repo)

    # Descend into each branch up to a depth of `max_count` and
    # collect commits. We're collecting more than needed, but we don't know
    # in advance which branch will have the latest commits.
    commits = []
    seen_hashes = set()
    queue = collections.deque((head, 0) for head in heads)
    while queue:
        hash_, depth = queue.popleft()
        if hash_ in seen_hashes:
            continue
        seen_hashes.add(hash_)
        commit = repo.commit(hash_)
        commits.append((hash_, commit))
        if depth < max_count:
            for parent in commit.parents:
                queue.append((parent, depth + 1))

    # Only keep the `max_count` latest commits
    commits.sort(key=lambda (hash_, commit): commit.commit_time, reverse=True)
    return commits[:max_count]


def main():
    repo = Repo('.')
    for hash_, c in get_latest_commits(repo):
        print hash_


if __name__ == '__main__':
    main()
