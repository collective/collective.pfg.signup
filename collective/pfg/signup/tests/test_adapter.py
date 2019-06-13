"""Test on sign up adapter."""
from collective.pfg.signup.testing import INTEGRATION_TESTING
from plone.app.testing import setRoles
from plone.app.testing import TEST_USER_ID
import unittest2 as unittest


class TestSignUpAdapter(unittest.TestCase):

    """Test case on sign up adapter."""

    layer = INTEGRATION_TESTING



    def test_correctly_installed(self):
        """Test on sign up adapter is correctly installed."""
        portal = self.layer['portal']
        self.assertIn('SignUpAdapter', portal.portal_types.objectIds())
        self.assertIn('SignUpAdapter', portal.portal_factory.getFactoryTypes())

    def test_creation(self):
        """Test on creation of sign up adapter."""
        portal = self.layer['portal']
        setRoles(portal, TEST_USER_ID, ['Contributor'])
        form = portal[portal.invokeFactory('FormFolder', 'form')]
        signup_adapter = form[form.invokeFactory('SignUpAdapter', 'signup')]
        self.assertEqual(signup_adapter.portal_type, 'SignUpAdapter')


    def test_createuser(self):
        pass
