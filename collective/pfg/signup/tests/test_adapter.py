"""Test on sign up adapter."""
from collective.pfg.signup.testing import INTEGRATION_TESTING
from plone.app.testing import setRoles
from plone.app.testing import TEST_USER_ID
from Products.CMFCore.Expression import Expression
try:
    import unittest2 as unittest
except:
    import unittest
from plone import api

class TestSignUpAdapter(unittest.TestCase):

    """Test case on sign up adapter."""

    layer = INTEGRATION_TESTING

    def setUp(self):
        self.app = self.layer['app']
        self.portal = self.layer['portal']
        form = self.portal['form']
        form.checkAuthenticator = False # no csrf protection
        self.form = form

    def test_correctly_installed(self):
        """Test on sign up adapter is correctly installed."""
        portal = self.layer['portal']
        self.assertIn('SignUpAdapter', portal.portal_types.objectIds())
        self.assertIn('SignUpAdapter', portal.portal_factory.getFactoryTypes())

    def test_creation(self):
        """Test on creation of sign up adapter."""
        portal = self.layer['portal']
        setRoles(portal, TEST_USER_ID, ['Contributor'])
        form = portal[portal.invokeFactory('FormFolder', 'form1')]
        signup_adapter = form[form.invokeFactory('SignUpAdapter', 'signup1')]
        self.assertEqual(signup_adapter.portal_type, 'SignUpAdapter')

    def LoadRequestForm(self, **kwargs):
        form = self.app.REQUEST.form
        form.clear()
        for key in kwargs.keys():
            form[key] = kwargs[key]
        self.app.REQUEST['ACTUAL_URL'] = 'http://nohost/form/signup' # HACK for plone 4.1
        self.app.REQUEST['URL'] = 'http://nohost/form/signup'
        return self.app.REQUEST

    def test_auto_register(self):
        signup = self.form.signup
        fields = self.form._getFieldObjects()
        request = self.LoadRequestForm(fullname='test name', username='test1', email='test@mail.com')
        signup.onSuccess(fields, request)
        user = api.user.get(username='test1')
        self.assertIsNotNone(user, 'Fail to auto-register user')

    def test_add_to_group(self):
        self.form.signup.user_group_template = Expression('string:staff')
        signup = self.form.signup
        fields = self.form._getFieldObjects()
        request = self.LoadRequestForm(fullname='test name', username='test1', email='test@mail.com', )
        signup.onSuccess(fields, request)
        groups = api.group.get_groups(username='test1')
        self.assertTrue('staff' in [group.id for group in groups],'User not created with staff group')

    def test_add_to_dynamic_group(self):
        self.form.signup.user_group_template = Expression('string:${department}')
        signup = self.form.signup
        fields = self.form._getFieldObjects()
        request = self.LoadRequestForm(fullname='test name', username='test1', email='test@mail.com',department='IT' )
        signup.onSuccess(fields, request)
        groups = api.group.get_groups(username='test1')
        self.assertTrue('IT' in [group.id for group in groups],'User not created with IT group')

    def test_invalid_domain_name_validation(self):
        group = api.group.get(groupname='staff')
        self.assertTrue(group.getProperty('email').endswith('@plone.org'), 'Staff group email domain is not set to plone.org')
        self.form.signup.user_group_template = Expression('string:staff')
        self.form.signup.email_domain_verification = True
        signup = self.form.signup
        fields = self.form._getFieldObjects()
        request = self.LoadRequestForm(fullname='test name', username='test1', email='test@mail.com')
        signup.onSuccess(fields, request)
        user = api.user.get(username='test1')
        self.assertIsNone(user, 'Fail to validate invalid user email')

    def test_valid_domain_name_validation(self):
        group = api.group.get(groupname='staff')
        self.assertTrue(group.getProperty('email').endswith('@plone.org'),
                        'Staff group email domain is not set to plone.org')
        self.form.signup.user_group_template = Expression('string:staff')
        self.form.signup.email_domain_verification = True
        signup = self.form.signup
        fields = self.form._getFieldObjects()
        request = self.LoadRequestForm(fullname='test name', username='test2', email='test@plone.org')
        signup.onSuccess(fields, request)
        user = api.user.get(username='test2')
        self.assertIsNotNone(user, 'Fail to validate valid user email')

    def test_approve_user(self):
        self.form.signup.user_group_template = Expression('string:staff')
        self.form.signup.manage_group_template = Expression('python:{"Administrators": ["staff"]}')
        signup = self.form.signup
        fields = self.form._getFieldObjects()
        request = self.LoadRequestForm(fullname='test name', username='test1', email='test@mail.com')
        signup.onSuccess(fields, request)
        user = api.user.get(username='test1')
        self.assertIsNone(user, 'User created before approving')
        self.assertTrue(self.portal.MailHost.messages[0])
        self.assertIn('There is a user waiting for approval', self.portal.MailHost.messages[1])
        self.assertIn('From: localhost@plone.org', self.portal.MailHost.messages[1])
        self.assertIn('To: admin@plone.org', self.portal.MailHost.messages[1])
        self.REQUEST = self.LoadRequestForm( userid='test1')
        signup.approve_user()
        user = api.user.get(username='test1')
        self.assertIsNotNone(user, 'User not created after approving')

    def test_reject_user(self):
        self.form.signup.user_group_template = Expression('string:staff')
        self.form.signup.manage_group_template = Expression('python:{"Administrators": ["staff"]}')
        signup = self.form.signup
        fields = self.form._getFieldObjects()
        request = self.LoadRequestForm(fullname='test name', username='test1', email='test@mail.com')
        signup.onSuccess(fields, request)
        user = api.user.get(username='test1')
        self.assertIsNone(user, 'User created before rejecting')
        self.REQUEST = self.LoadRequestForm( userid='test1')
        signup.reject_user()
        user = api.user.get(username='test1')
        self.assertIsNone(user, 'User created after rejecting')

    def test_send_registration_email(self):
        signup = self.form.signup
        fields = self.form._getFieldObjects()
        request = self.LoadRequestForm(fullname='test name', username='test1', email='test@mail.com')
        signup.onSuccess(fields, request)
        self.assertIn('This link is valid for 168 hours', self.portal.MailHost.messages[0])
        self.assertIn('To: test@mail.com\n', self.portal.MailHost.messages[0])
        self.assertIn('From: Plone <localhost@plone.org>\n', self.portal.MailHost.messages[0])

    def test_send_approving_email(self):
        self.form.signup.user_group_template = Expression('string:staff')
        self.form.signup.manage_group_template = Expression('python:{"Administrators": ["staff"]}')
        signup = self.form.signup
        fields = self.form._getFieldObjects()
        request = self.LoadRequestForm(fullname='test name', username='test1', email='test@mail.com')
        signup.onSuccess(fields, request)

        self.assertIn('Your\n                account is waiting for approval', self.portal.MailHost.messages[0])
        self.assertIn('To: test@mail.com', self.portal.MailHost.messages[0])
        self.assertIn('From: localhost@plone.org', self.portal.MailHost.messages[-1])

        self.assertIn('There is a user waiting for approval', self.portal.MailHost.messages[1])
        self.assertIn('To: admin@plone.org', self.portal.MailHost.messages[1])
        self.assertIn('From: localhost@plone.org', self.portal.MailHost.messages[1])
