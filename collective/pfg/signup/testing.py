from plone.testing import z2
from plone.app.testing import PloneSandboxLayer
from plone.app.testing import PLONE_FIXTURE
from plone.app.testing import IntegrationTesting
from plone.app.testing import FunctionalTesting


class Layer(PloneSandboxLayer):

    defaultBases = (PLONE_FIXTURE,)

    def setUpZope(self, app, configurationContext):
        import Products.PloneFormGen
        self.loadZCML(package=Products.PloneFormGen)
        z2.installProduct(app, "Products.PloneFormGen")

        import collective.pfg.signup
        self.loadZCML(package=collective.pfg.signup)
        z2.installProduct(app, "collective.pfg.signup")

    def setUpPloneSite(self, portal):
        # PLONE_FIXTURE has no default workflow chain set
        portal.portal_workflow.setDefaultChain("simple_publication_workflow")

        self.applyProfile(portal, 'collective.pfg.signup:default')

    def tearDownZope(self, app):
        z2.uninstallProduct(app, "collective.pfg.signup")
        z2.uninstallProduct(app, "Products.PloneFormGen")


FIXTURE = Layer()
INTEGRATION_TESTING = IntegrationTesting(bases=(FIXTURE,),
    name='collective.pfg.signup:Integration')
FUNCTIONAL_TESTING = FunctionalTesting(bases=(FIXTURE,),
    name='collective.pfg.signup:Functional')
