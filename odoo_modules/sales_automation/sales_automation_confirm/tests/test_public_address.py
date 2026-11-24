# -*- coding: utf-8 -*-
"""The address bar shows a link that opens for anybody (24 Nov 2026): the bare
`/wa/confirm/<token>` is "Not Found" in a browser that has no session."""
from odoo.tests import tagged

from .test_back_to_group import TestBackToGroup as Base


@tagged('post_install', '-at_install')
class TestPublicAddress(Base):

    def _path(self):
        return self.link._public_path(self.link.token)

    def test_the_whatsapp_link_is_the_same_address(self):
        self.assertTrue(self.link._url().endswith(self._path()))
        self.assertIn('db=%s&t=%s' % (self.env.cr.dbname, self.link.token), self._path())

    def test_the_open_page_shows_it(self):
        self.assertIn('history.replaceState(null,"","%s")' % self._path(), self._html())

    def test_the_result_shows_it_and_stays_the_result(self):
        self._post('accept')
        self.assertIn('history.replaceState(null,"","%s&done=1")' % self._path(), self._html('?done=1'))

    def test_opened_with_no_session_at_all(self):
        """A browser that never signed in: the doorway alone is enough."""
        self.opener.cookies.clear()
        res = self.url_open(self._path())
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.url.endswith('/wa/confirm/%s' % self.link.token))

    def test_a_page_that_is_not_there_shows_nothing(self):
        self.assertNotIn('replaceState', self.url_open('/wa/confirm/short').text)
