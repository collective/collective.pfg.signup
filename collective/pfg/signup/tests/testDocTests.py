# -*- coding: utf-8 -*-
from collective.pfg.signup.testing import FUNCTIONAL_TESTING
from plone import api
from plone.testing import layered
from plone.testing.z2 import Browser

import doctest
import re
import six
import transaction
import unittest


optionflags = (
    doctest.REPORT_ONLY_FIRST_FAILURE
    | doctest.NORMALIZE_WHITESPACE
    | doctest.ELLIPSIS
    | doctest.REPORTING_FLAGS
)

testfiles = (
    "browser.rst",
)


class Py23DocChecker(doctest.OutputChecker):
    def check_output(self, want, got, optionflags):
        if six.PY2:
            got = re.sub("zExceptions.NotFound", "NotFound", got)
            got = re.sub("u'(.*?)'", "'\\1'", want)
        return doctest.OutputChecker.check_output(self, want, got, optionflags)


def get_browser(layer, auth=True):
    browser = Browser(layer["app"])
    browser.handleErrors = False
    if auth:
        api.user.create(
            username="adm", password="secret", email="a@example.org", roles=("Manager",)
        )
        transaction.commit()
        browser.addHeader("Authorization", "Basic adm:secret")
    return browser


def brpswer_test():
    """
    Integration tests
    =================

        >>> browser = get_browser(layer)

    Standalone form
    ---------------

    Open the PFG Form:

        >>> portal = layer['portal']
        >>> form_url = portal.absolute_url() + '/form'
        >>> browser.open(form_url)
        >>> browser.url
        'http://nohost/plone/form'

    Auto-register an user

        >>> browser.open(form_url)
        >>> browser.getControl(name='fullname').value = 'Tester'
        >>> browser.getControl(name='username').value = 'tester'
        >>> browser.getControl(name='email').value = 'tester@example.com'
        >>> browser.getControl('Submit').click()

        >>> user_group_url = portal.absolute_url() + '/@@usergroup-userprefs'
        >>> browser.open(user_group_url)
        >>> 'tester' in browser.contents
        True

    :return:
    """
    pass

def test_suite():
    suite = unittest.TestSuite()
    suite.addTests(
        [
            layered(
                doctest.DocTestSuite("collective.pfg.signup.tests.testDocTests",
                    optionflags=optionflags,
                    globs={"get_browser": get_browser},
                    checker=Py23DocChecker(),
                ),
                layer=FUNCTIONAL_TESTING,
            )
            for f in testfiles
        ]
    )
    return suite
