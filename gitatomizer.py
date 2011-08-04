#!/usr/bin/env python
# coding: utf8

import collections
import string
import datetime
from xml.sax.saxutils import escape as xml_escape

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
    A tzinfo implementation for a fixed offset. (Once again.)

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
    * 't' formats a (timestamp, timezone) tuple in ISO format.
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


def build_atom_feed(entries, feed_title, feed_link):
    """
    Yield fragments of an Atom feed as byte-strings.
    """
    # http://tools.ietf.org/html/rfc4287
    # http://www.atomenabled.org/developers/syndication/
    # Feed elements
    #    Required: id, title, updated
    #    Recommended: author, link
    #    Optional: category, contributor, generator, icon, logo,
    #              rights, subtitle
    # Entry elements:
    #    Required: id, title, updated
    #    Recommended: author, link, content, summary
    #    Optional: category, contributor, published, source, rights
    format = AtomizerFormatter().format
    assert len(entries) > 0
    yield format(
        (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<feed xmlns="http://www.w3.org/2005/Atom">\n'
	        '  <title>{title!x}</title>\n'
	        '  <id>{link!x}</id>\n'
	        '  <link>{link!x}</link>\n'
	        '  <updated>{updated!t}</updated>\n'
        ),
	    title=feed_title,
        link=feed_link,
        updated=max(entry['updated'] for entry in entries),
    )
    if feed_link:
        yield format('  <link>{link!x}</link>\n', link=feed_link)
    for entry in entries:
        yield format(
            (
                '  <entry>\n'
	            '    <title>{title!x}</title>\n'
	            '    <id>{feed_link!x}#{id!x}</id>\n'
	            '    <updated>{updated!t}</updated>\n'
                '  </entry>\n'
            ),
            feed_link=feed_link,
            **entry
        )
    yield '</feed>'


def main():
    repo = Repo('.')
    entries = []
    for hash_, commit in get_latest_commits(repo):
        entries.append(dict(
            id=hash_,
            updated=(commit.commit_time, commit.commit_timezone),
            title=commit.message.split('\n', 1)[0]
        ))
    print ''.join(build_atom_feed(entries, 'Git commits',
        'http://example.org/feed'))


if __name__ == '__main__':
    main()
