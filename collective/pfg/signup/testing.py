"""Testing layer."""
from plone.app.testing import FunctionalTesting
from plone.app.testing import IntegrationTesting
from plone.app.testing import PLONE_FIXTURE
from plone.app.testing import PloneSandboxLayer
from plone.testing import z2
from plone.app.testing import setRoles
from plone.app.testing import TEST_USER_ID
from zope.component import getUtility
from plone.registry.interfaces import IRegistry
from Products.CMFCore.utils import getToolByName
try:
    from Products.CMFPlone.interfaces import IMailSchema
except ImportError:
    from plone.app.controlpanel.mail import IMailSchema
from plone import api
from plone.app.robotframework.testing import REMOTE_LIBRARY_BUNDLE_FIXTURE
from plone.testing.z2 import ZSERVER_FIXTURE

class Layer(PloneSandboxLayer):

    """Plone testing sandbox layer."""

    defaultBases = (PLONE_FIXTURE,)

    def setUpZope(self, app, configurationContext):
        """Set up Zope."""
        import Products.PloneFormGen
        self.loadZCML(package=Products.PloneFormGen)
        z2.installProduct(app, "Products.PloneFormGen")

        import collective.pfg.signup
        self.loadZCML(package=collective.pfg.signup)
        z2.installProduct(app, "collective.pfg.signup")

    def setUpPloneSite(self, portal):
        """Set up Plone site."""
        # PLONE_FIXTURE has no default workflow chain set
        portal.portal_workflow.setDefaultChain("simple_publication_workflow")

        self.applyProfile(portal, 'Products.PloneFormGen:default')
        self.applyProfile(portal, 'collective.pfg.signup:default')
        setRoles(portal, TEST_USER_ID, ['Contributor'])
        form = portal[portal.invokeFactory('FormFolder', 'form')]
        signup_adapter = form[form.invokeFactory('SignUpAdapter', 'signup')]
        form.invokeFactory('FormStringField', 'fullname')
        form.invokeFactory('FormStringField', 'username')
        form.invokeFactory('FormStringField', 'email')
        form.invokeFactory('FormStringField', 'department')
        form.mailer.setRecipient_name('Mail Dummy')
        form.mailer.setRecipient_email('mdummy@address.com')
        form.signup.full_name_field = 'fullname'
        form.signup.username_field = 'username'
        form.signup.email_field = 'email'
        # registry = getUtility(IRegistry)
        mail_settings =  IMailSchema(portal)
        mail_settings.email_from_address = 'localhost@plone.org'
        mail_settings.email_from_name = u'Plone'
        group = api.group.create(groupname='staff')
        group.setProperties(email ='staff@plone.org')
        admin_group = api.group.create(groupname='Administrators')
        admin_group.setProperties(email ='admin@plone.org')
        portal_membership = getToolByName(portal, 'portal_membership')
        current_user = portal_membership.getAuthenticatedMember()
        api.group.add_user(groupname='Administrators', username=current_user.id)

    def tearDownZope(self, app):
        """Tear down zope."""
        z2.uninstallProduct(app, "collective.pfg.signup")
        z2.uninstallProduct(app, "Products.PloneFormGen")


FIXTURE = Layer()
INTEGRATION_TESTING = IntegrationTesting(
    bases=(FIXTURE,),
    name='collective.pfg.signup:Integration')
FUNCTIONAL_TESTING = FunctionalTesting(
    bases=(FIXTURE,),
    name='collective.pfg.signup:Functional')
# ACCEPTANCE_TESTING = FunctionalTesting(
#     bases=(FIXTURE, REMOTE_LIBRARY_BUNDLE_FIXTURE, ZSERVER_FIXTURE),
#     name="collective.easyform:Acceptance",
# )
