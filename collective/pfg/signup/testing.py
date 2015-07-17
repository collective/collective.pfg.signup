"""Testing layer."""
from plone.app.testing import FunctionalTesting
from plone.app.testing import IntegrationTesting
from plone.app.testing import PLONE_FIXTURE
from plone.app.testing import PloneSandboxLayer
from plone.testing import z2


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
