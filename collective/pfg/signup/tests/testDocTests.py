# -*- coding: utf-8 -*-
from collective.pfg.signup.testing import FUNCTIONAL_TESTING
from plone import api
from plone.testing import layered
from plone.testing.z2 import Browser
from plone import api

import doctest
import re
import six
import transaction
import unittest
from plone.app.testing import TEST_USER_ID, TEST_USER_PASSWORD, SITE_OWNER_NAME, SITE_OWNER_PASSWORD
from Products.CMFCore.Expression import Expression


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


def get_browser(layer, url=None, auth=True, role="Editor", approval_group=None):
    browser = Browser(layer["app"])
    browser.handleErrors = True # 4.1 doesn't handle redirect if False
    if auth:
        user = api.user.create(
            username="adm", password="secret", email="a@example.org", roles=(role,)
        ) # TODO: why have to use contributor? Should work with lower role
        api.group.add_user(groupname="Managers", user=user)
        if approval_group:
            if type(approval_group) != list:
                approval_group = [approval_group]
            layer['portal'].form.signup.user_group_template = Expression('string:{}'.format(approval_group[0]))
            tal = 'python:{"Managers": %s}' % repr(approval_group)
            layer['portal'].form.signup.manage_group_template = Expression(tal)

        transaction.commit()
        browser.addHeader("Authorization", "Basic adm:secret")
        #browser.addHeader("Authorization", "Basic {}:{}".format(TEST_USER_ID, TEST_USER_PASSWORD))

    if url:
        browser.open(layer['portal'].absolute_url() + '/' + url)
    return browser


def test_register_user_without_approval():
    """
    Register an user

        >>> browser = get_browser(layer, "form", role="Manager")
        >>> browser.getControl(name='fullname').value = 'Tester'
        >>> browser.getControl(name='username').value = 'tester'
        >>> browser.getControl(name='email').value = 'tester@example.com'
        >>> browser.getControl('Submit').click()
        >>> 'Error' not in browser.contents
        True
        >>> print browser.contents
        <...
        ...<dt>Your E-Mail Address</dt>
        ...<dd>a@example.org</dd>
        ...

    Then manage the user
        >>> browser.open("form/signup/@@user_search_view")
        >>> print browser.contents
        <...
        ...Tester...
        ...

    :return:
    """
    pass

def test_search_user():
    """
    Create a user

        >>> user = api.user.create(username='mylogin',email="me@me.com", properties=dict(fullname="Fred")) # TODO: set userid different
        >>> api.group.add_user(groupname="staff", user=user)
        >>> b = get_browser(layer, 'form/signup/@@user_search_view', approval_group="staff")

        >>> b.open("@@user_search_view")
        >>> b.getControl("User Search").value = "mylogin"
        >>> b.getControl("Find Users").click()
        >>> print b.contents
        <...
        ...
        ...mylogin
        ...Fred
        ...staff
        ...Active
        ...
    """

def test_search_by_group():
    """
    One user in staff
        >>> staff1 = api.user.create(username='mystaff1',email="me1@me.com", properties=dict(fullname="Fred"))
        >>> api.group.add_user(groupname="staff", user=staff1)

    One user in staff2
        >>> staff2 = api.user.create(username='mystaff2',email="me2@me.com", properties=dict(fullname="Sally"))
        >>> group = api.group.create(groupname='staff2')
        >>> api.group.add_user(group=group, user=staff2)

        >>> transaction.commit()

    Ensure we are the manager of both groups
        >>> b = get_browser(layer, 'form/signup/@@user_search_view', approval_group=["staff","staff2"])

    So we should see both users
        >>> b.open("@@user_search_view")
        >>> print b.contents
        <...
        ...mystaff1...Fred...
        ...
        ...mystaff2...Sally...
        ...

    and limit to a group staff
        >>> b.getControl("Group").options
        ['staff', 'staff2']
        >>> b.getControl("Group").value = ["staff"]
        >>> b.getControl("Find Users").click()
        >>> print b.contents
        <...
        ...mystaff1...Fred...
        ...
        >>> 'mystaff2' in b.contents
        False

    and limit to a group staff2
        >>> b.getControl("Group").value = ["staff2"]
        >>> b.getControl("Find Users").click()
        >>> print b.contents
        <...
        ...mystaff2...Sally...
        ...
        >>> 'mystaff1' in b.contents
        False

    keyword and group filter can work togeather
        >>> b.getControl("User Search").value = "dummy"
        >>> b.getControl("Group").value = ["staff2"]
        >>> b.getControl("Find Users").click()
        >>> 'mystaff1' in b.contents
        False
        >>> 'mystaff2' in b.contents
        False

        >>> b.getControl("User Search").value = "mystaff"
        >>> b.getControl("Group").value = ["staff2"]
        >>> b.getControl("Find Users").click()
        >>> 'mystaff1' in b.contents
        False
        >>> 'mystaff2' in b.contents
        True


    """


def test_only_see_users_you_manage():
    """
    Create two users. One in a group we control. and one in our staff group
        >>> notingroup = api.user.create(username='notingroup',email="me2@me.com", properties=dict(fullname="Not in group"))
        >>> mylogin = api.user.create(username='mylogin',email="me@me.com", properties=dict(fullname="Fred"))
        >>> api.group.add_user(groupname="staff", user=mylogin)
        >>> transaction.commit()
        >>> b = get_browser(layer, 'form/signup/@@user_search_view', approval_group="staff")


        >>> b.open("@@user_search_view")

    We can users but only in teh groups we control
        >>> 'notingroup' in b.contents
        False

        >>> print b.contents
        <...
        ...mylogin...
        ...

    Ensure we view profile of users we don't manage
        >>> url = layer['portal'].absolute_url() + '/form/signup'
        >>> b.open("{}/user_profile_view?userid={}".format(url, 'notingroup'))
        >>> print b.contents
        <...
        ...Insufficient Privileges...

    or deactivate
        >>> b.open("{}/user_profile_view?userid={}&form.button.deactivate=1".format(url, 'notingroup'))
        >>> print b.contents
        <...
        ...Insufficient Privileges...

    or edit
        >>> b.open("{}/user_edit_view?userid={}".format(url, 'notingroup'))
        >>> print b.contents
        <...
        ...Insufficient Privileges...
    """

def test_group_in_group():
    """
    We will have a group inside a group you manage.
    Not clear if you should expect to manage people in a subgroup or not.
    So far functionality has been to allow editing subgroup users so will test and keep that

        >>> notingroup = api.user.create(username='notingroup',email="me2@me.com", properties=dict(fullname="Not in group"))
        >>> mylogin = api.user.create(username='mylogin',email="me@me.com", properties=dict(fullname="Fred"))
        >>> api.group.add_user(groupname="staff", user=mylogin)

        >>> superstaff = api.group.create(groupname="superstaff")
        >>> api.group.add_user(groupname="superstaff", user=notingroup)
        >>> layer['portal'].portal_groups.addPrincipalToGroup('superstaff', 'staff') # api.group.add_user(groupname="staff", username="superstaff")
        True
        >>> transaction.commit()
        >>> b = get_browser(layer, 'form/signup/@@user_search_view', approval_group="staff")
        >>> url = layer['portal'].absolute_url() + '/form/signup'

    If we look at staff group we shouldn't see the superstaff or its users
        >>> b.open("{}/@@user_search_view?user-groups=staff".format(url))
        >>> 'notingroup' in b.contents
        True

        >>> b.open("{}/@@user_search_view".format(url))
        >>> 'notingroup' in b.contents
        True
    
    Ensure we view profile of users we don't manage
        >>> url = layer['portal'].absolute_url() + '/form/signup'
        >>> b.open("{}/user_profile_view?userid={}".format(url, 'notingroup'))
        >>> print b.contents
        <...
        ...Not in group...

    or edit
        >>> b.open("{}/user_edit_view?userid={}".format(url, 'notingroup'))
        >>> print b.contents
        <...
        ...Not in group...

    or deactivate
        >>> b.open("{}/user_profile_view?userid={}".format(url, 'notingroup'))
        >>> b.getControl("Deactivate").click()
        >>> print b.contents
        <...
        ...Not in group...


    """

def test_set_group_manager(): #TODO: actually test it changes who can manage a group
    """
    Setup the Administrators group as the managers for MyGroup
        >>> b = get_browser(layer, 'form/signup/edit')
        >>> b.getControl("Add to Groups",index=0).value = "string:staff}"
        >>> b.getControl(name="manage_group_template")
        <Control name='manage_group_template' type='textarea'>
        >>> b.getControl(name="manage_group_template").value = "python:{'Managers': ['staff']}"
        >>> b.getControl("Save").click()
        >>> print b.contents
        <...
        ...Changes saved...
    """


def test_deactivate_user():
    """
    Create a user

        >>> user = api.user.create(username='mylogin', email="me@me.com", password="blahblah", properties=dict(fullname="Fred")) # TODO: set userid different
        >>> api.group.add_user(groupname="staff", user=user)
        >>> b = get_browser(layer, 'form/signup/@@user_search_view', approval_group="staff")

        >>> b.open("@@user_search_view")
        >>> b.getControl("User Search").value = "mylogin"
        >>> b.getControl("Find Users").click()
        >>> print b.contents
        <...
        ...
        ...mylogin
        ...Active
        ...

        >>> b.getLink("mylogin").click()
        >>> b.getControl("Deactivate").click()
        >>> print b.contents
        <...
        ...
        ...This user is deactivated...
        ...

    This should mean the user can no longer login
        >>> b2 = get_browser(layer, url="login", auth=False)
        >>> b2.getControl(name="__ac_name").value = "mylogin"
        >>> b2.getControl("Password").value = "blahblah"
        >>> b2.getControl("Log in").click()
        >>> print b2.contents
        <...
        ...Login failed...
        ...

    """


def test_suite():
    suite = unittest.TestSuite()
    suite.addTests(
        [
            layered(
                doctest.DocTestSuite("collective.pfg.signup.tests.testDocTests",
                    optionflags=optionflags,
                    globs=globals(),
                    #checker=Py23DocChecker(),
                ),
                layer=FUNCTIONAL_TESTING,
            )
            for f in testfiles
        ]
    )
    return suite
