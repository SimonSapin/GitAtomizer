#!/usr/bin/env python
# coding: utf8

import collections
import string
import datetime

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


class FixedOffsetTimezone(datetime.tzinfo):
    """
    A tzinfo implemtation for a fixed offset. (Once again.)

    :param offset: seconds east of UTC
    """
    def __init__(self, offset):
        self.delta = datetime.timedelta(seconds=offset)

    def utcoffset(self, _dt):
        return self.delta

    def dst(self, _dt):
        return datetime.timedelta(0)


class AtomizerFormatter(string.Formatter):
    """
    The same Formatter that implements `str.format`, but with an additional
    conversion scheme:

    * 'x' encodes an unicode string into UTF-8 and escapes it for XML
    * 't' formates a (timestamp, timezone) tuple in ISO format.
      `timestamp` is a POSIX timestamp in seconds and `timezone` is in
      seconds east of UTC. They are what Dulwich puts in `Commit.commit_time`
      and `Commit.commit_timezone`
    """
    def convert_field(self, value, conversion):
        if conversion == 'x':
            return xml_escape(value.encode('utf8'))
        elif conversion == 't':
            timestamp, timezone = value
            return datetime.datetime.fromtimestamp(timestamp,
                FixedOffsetTimezone(timezone)).isoformat()
        else:
            return super(AtomizerFormatter, self).convert_field(
                value, conversion)


def main():
    repo = Repo('.')
    format = AtomizerFormatter().format
    for hash_, c in get_latest_commits(repo):
        print format('{0} {1!t}', hash_,
            (c.commit_time, c.commit_timezone))


if __name__ == '__main__':
    main()
