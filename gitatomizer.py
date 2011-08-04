#!/usr/bin/env python
# coding: utf8

import collections
import string
import datetime
from xml.sax.saxutils import escape as xml_escape

from dulwich.repo import Repo


ATOM_FEED_REQUIRED = ('title', 'id', 'updated')
ATOM_ENTRY_REQUIRED = ('title', 'id', 'updated')

# Recommended and optional
ATOM_FEED_OPTIONAL = ('author', 'link', 'category', 'contributor', 'rights',
    'generator', 'icon', 'logo', 'subtitle')
ATOM_ENTRY_OPTIONAL = ('author', 'link', 'category', 'contributor', 'rights',
    'content', 'summary', 'published', 'source')


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
    A tzinfo implementation for a fixed offset. (Once again.)

    :param offset: seconds east of UTC
    """
    def __init__(self, offset):
        self.delta = datetime.timedelta(seconds=offset)

    def utcoffset(self, _dt):
        return self.delta

    def dst(self, _dt):
        return datetime.timedelta(0)


def parse_timestamp(timestamp, timezone):
    """
    Get a POSIX `timestamp` and a `timezone` is seconds east of UTC (as
    found in Dulwich’s  `Commit.commit_time` and `Commit.commit_timezone`)
    and return a timezone-aware datetime object.
    """
    tzinfo = FixedOffsetTimezone(timezone)
    return datetime.datetime.fromtimestamp(timestamp, tzinfo)


def _format_xml(tag, content):
    tag = tag.encode('utf8') # assume it is XML-safe
    content = xml_escape(content.encode('utf8'))
    return '<{tag}>{content}</{tag}>\n'.format(**locals())


def _dict_to_xml(data, required_keys, optional_keys):
    for key in required_keys:
        yield _format_xml(key, data[key])

    for key in optional_keys:
        if key in data:
            yield _format_xml(key, data[key])


def build_atom_feed(feed_data):
    """
    Yield fragments of an Atom feed as byte-strings.
    """
    yield '<?xml version="1.0" encoding="utf-8"?>\n' \
          '<feed xmlns="http://www.w3.org/2005/Atom">\n'

    feed_data = dict(feed_data)

    for fragment in _dict_to_xml(feed_data,
            ATOM_FEED_REQUIRED, ATOM_FEED_OPTIONAL):
        yield '  ' + fragment

    entries = feed_data.pop('entries')

    for entry in entries:
        entry = dict(entry)
        yield '  <entry>\n'
        for fragment in _dict_to_xml(dict(entry),
                ATOM_ENTRY_REQUIRED, ATOM_ENTRY_OPTIONAL):
            yield '    ' + fragment
        yield '  </entry>\n'
    yield '</feed>'


def build_feed_data(repo):
    """
    Return a data structure matching that of an Atom feed:
    a dict with the following keys:

    * Required: id, title, updated, entries
    * Recommended: author, link
    * Optional: category, contributor, generator, icon, logo, rights, subtitle

    All values should be unicode strings except `entries` which is a list of
    dicts with the following keys:

    * Required: id, title, updated
    * Recommended: author, link, content, summary
    * Optional: category, contributor, published, source, rights

    Again, all values should be unicode strings.

    See http://tools.ietf.org/html/rfc4287 and
    http://www.atomenabled.org/developers/syndication/
    """
    feed_id = 'http://example.org/feed'
    entries = []
    for hash_, commit in get_latest_commits(repo):
        date = parse_timestamp(commit.commit_time, commit.commit_timezone)
        message = commit.message.strip()
        entries.append(dict(
            id='{}#{}'.format(feed_id, hash_),
            updated=date.isoformat(),
            title=message.split('\n', 1)[0],
            content=message,
        ))
    return dict(
        id=feed_id,
        title='Git commits',
        updated=max(entry['updated'] for entry in entries),
        entries=entries,
    )


def build_commit_feed(repository_path, data_builder=build_feed_data):
    """
    Return an Atom feed as a byte string.
    """
    return ''.join(build_atom_feed(data_builder(Repo(repository_path))))


def main():
    print build_commit_feed('.')


if __name__ == '__main__':
    main()
