#!/usr/bin/env python
# coding: utf8

import os.path
import collections
import string
import datetime
import operator
import subprocess
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
        commits.append(commit)
        if depth < max_count:
            for parent in commit.parents:
                queue.append((parent, depth + 1))

    # Only keep the `max_count` latest commits
    commits.sort(key=operator.attrgetter('commit_time'), reverse=True)
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


class AtomBuilder(object):
    """
    Abstract class building Atom feeds.
    """

    def build(self):
        return ''.join(self.build_fragments())

    def escape(self, value):
        """
        Encode an unicode `value` in UTF-8 and XML-escape it.
        """
        return xml_escape(value.encode('utf8'))

    def build_fragments(self):
        yield ('<?xml version="1.0" encoding="utf-8"?>\n'
               '<feed xmlns="http://www.w3.org/2005/Atom">\n'
               '  <id>')
        yield self.escape(self.get_feed_id())
        yield '</id>\n  <title>'
        yield self.escape(self.get_feed_title())
        yield '</title>\n  <updated>'
        yield self.get_feed_updated().isoformat()
        yield '</updated>\n'
        link = self.get_feed_link()
        if link:
            yield '  <link>'
            yield self.escape(link)
            yield '</link>\n'

        for entry in self.get_entries():
            yield '  <entry>\n    <id>'
            yield self.escape(self.get_entry_id(entry))
            yield '</id>\n    <title>'
            yield self.escape(self.get_entry_title(entry))
            yield '</title>\n    <updated>'
            yield self.get_entry_updated(entry).isoformat()
            yield '</updated>\n'
            link = self.get_entry_link(entry)
            if link:
                yield '    <link href="'
                yield self.escape(link).replace('"', '&quot;')
                yield '"/>\n'
            author = self.get_entry_author(entry)
            if author:
                yield '    <author><name>'
                yield self.escape(author)
                yield '</name></author>\n'
            content = self.get_entry_html_content(entry)
            if content:
                yield '    <content type="html">'
                yield self.escape(content)
                yield '</content>\n'
            yield'  </entry>\n'

        yield '</feed>'

    ## Required

    def get_entries(self):
        """
        Return a iterable of objects, one for each entry in the feed.
        These objects can be anything and are passed to get_entry_* methods.

        Must be overriden.
        """
        raise NotImplementedError

    def get_feed_updated(self):
        """
        Date of the last significant update to the feed, as a datetime object.

        Defaults to the latest update date of its entries, can be overriden.
        """
        return max(self.get_entry_updated(entry)
                   for entry in self.get_entries())

    def get_feed_title(self):
        """
        The title of the feed, as an unicode string.

        Must be overriden.
        """
        raise NotImplementedError

    def get_feed_id(self):
        """
        A unique identifier for this feed, as an unicode string.

        Defaults to the feed’s link if there is one. Must be overriden
        if there is no link.
        """
        link = self.get_feed_link()
        if link:
            return link
        else:
            raise NotImplementedError

    def get_entry_title(self, entry):
        """
        The title for the given entry, as an unicode string.
        Must be overriden.
        """
        raise NotImplementedError

    def get_entry_id(self, entry):
        """
        A unique identifier for the given entry, as an unicode string.
        Must be overriden.

        Defaults to the entry’s link if there is one. Must be overriden
        if there is no link.
        """
        link = self.get_entry_link(entry)
        if link:
            return link
        else:
            raise NotImplementedError

    def get_entry_updated(self, entry):
        """
        The date of the last significant update to the given entry, as a
        datetime object.

        Must be overriden.
        """
        raise NotImplementedError

    ## Recommended

    def get_feed_link(self):
        """
        Optional link for the feed, as an unicode string.

        May be overriden. Otherwise there is no link.
        """
        return None

    def get_entry_link(self, entry):
        """
        Optional link for the given entry, as an unicode string.

        May be overriden. Otherwise there is no link.
        """
        return None

    def get_entry_author(self, entry):
        """
        Optional author name for the given entry, as an unicode string.

        May be overriden. Otherwise there is no link.
        """
        return None

    def get_entry_text_content(self, entry):
        """
        Optional plain text content describing the given entry,
        as an unicode string.

        May be overriden.
        """
        return None

    def get_entry_html_content(self, entry):
        """
        Optional HTML content describing the given entry,
        as an unicode string.

        May be overriden. Defaults to the result of get_entry_text_content
        in a <pre> element.
        """
        text = self.get_entry_text_content(entry)
        if text:
            return u'<pre>{}</pre>'.format(xml_escape(text))
        else:
            return None


class GitCommitsAtomBuilder(AtomBuilder):
    """
    Abstract builder of an Atom feed for git commits.
    """
    def __init__(self, repository_path):
        self.repository_path = repository_path
        self.repository = Repo(repository_path)

    def get_entries(self):
        return get_latest_commits(self.repository)

    def get_entry_title(self, commit):
        # First line of the commit message.
        return commit.message.strip().split('\n', 1)[0]

    def get_entry_id(self, commit):
        # `commit.id` is the SHA1 hash in hex, should be fairly unique
        return 'git:' + commit.id

    def get_entry_updated(self, commit):
        return parse_timestamp(commit.commit_time, commit.commit_timezone)

    def get_entry_author(self, commit):
        # `commit.author` looks like 'Author Name <email@example.org>',
        # only keep 'Author Name'.
        return commit.author.split('<', 1)[0].strip()

    def get_commit_diff(self, commit):
        process = subprocess.Popen(
            ['git', 'show', '--format=%B', '--stat', '--patch', commit.id],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        returncode = process.wait()
        if returncode != 0:
            raise RuntimeError('git show returned with code %i, stderr: %s' %
                (returncode, stderr))
        # Just assume UTF-8 ... we need unicode while git only cares
        # about bytes.
        return stdout.decode('utf8')

    def get_entry_text_content(self, commit):
        return self.get_commit_diff(commit)


class GithubAtomBuilder(GitCommitsAtomBuilder):
    """
    Builder for a git project on GitHub

    eg. for https://github.com/SimonSapin/GitAtomizer,
    `github_owner` is 'SimonSapin' and `github_repository` is 'GitAtomizer'.
    """
    def __init__(self, repository_path, github_owner, github_repository):
        super(GithubAtomBuilder, self).__init__(repository_path)
        self.github_owner = github_owner
        self.github_repository = github_repository

    def project_name(self):
        return '{}/{}'.format(self.github_owner, self.github_repository)

    def get_feed_title(self):
        return 'Latest commits for ' + self.project_name()

    def github_link(self):
        return 'https://github.com/' + self.project_name()

    def get_feed_link(self):
        return self.github_link()

    def get_entry_link(self, commit):
        return '{}/commit/{}'.format(self.github_link(), commit.id)


def main():
    print GithubAtomBuilder('.', 'SimonSapin', 'GitAtomizer').build()


if __name__ == '__main__':
    main()
