"""Testing layer."""
from plone.app.testing import FunctionalTesting
from plone.app.testing import IntegrationTesting
from plone.app.testing import PLONE_FIXTURE
from plone.app.testing import PloneSandboxLayer
from plone.testing import z2
from plone.app.testing import setRoles
from plone.app.testing import TEST_USER_ID


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

        self.applyProfile(portal, 'collective.pfg.signup:default')


        portal = self.layer['portal']
        setRoles(portal, TEST_USER_ID, ['Contributor'])
        form = portal[portal.invokeFactory('FormFolder', 'form')]
        signup_adapter = form[form.invokeFactory('SignUpAdapter', 'signup')]
        self.assertEqual(signup_adapter.portal_type, 'SignUpAdapter')


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
