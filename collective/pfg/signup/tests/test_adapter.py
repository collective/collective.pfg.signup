import unittest2 as unittest
from collective.pfg.signup.testing import INTEGRATION_TESTING
from plone.app.testing import TEST_USER_ID
from plone.app.testing import setRoles


class TestSignUpAdapter(unittest.TestCase):

    layer = INTEGRATION_TESTING

    def test_correctly_installed(self):
        portal = self.layer['portal']
        self.assertIn('SignUpAdapter', portal.portal_types.objectIds())
        self.assertIn('SignUpAdapter', portal.portal_factory.getFactoryTypes())

    def test_creation(self):
        portal = self.layer['portal']
        setRoles(portal, TEST_USER_ID, ['Contributor'])
        form = portal[portal.invokeFactory('FormFolder', 'form')]
        signup_adapter = form[form.invokeFactory('SignUpAdapter', 'signup')]
        self.assertEqual(signup_adapter.portal_type, 'SignUpAdapter')
