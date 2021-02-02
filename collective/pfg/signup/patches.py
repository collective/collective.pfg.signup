

def setSecurityProfile(self, password=None, roles=None, domains=None):
    """
    A bug in Products.CMFCore versions < 2.3.0 causes a failure to find
    users whose login ID is different to their user ID. The below code
    will use Products.CMFCore if the version has the fix, otherwise,
    it will use a copy-pasted version. See the following commit for more details on the fix:
    https://github.com/zopefoundation/Products.CMFCore/commit/570dea37248913c6c448f4783b4ef459f9a5456f
    """

    # Products.CMFCore was upgraded past 2.3.0 in Plone 5.2
    # See: https://github.com/plone/buildout.coredev/commit/557884e51426c9fa8d3af63aed8e7777509c285b

    user = self.getUser()

    # The Zope User API is stupid, it should check for None.
    if roles is None:
        roles = list(user.getRoles())
        if 'Authenticated' in roles:
            roles.remove('Authenticated')
    if domains is None:
        domains = user.getDomains()

    user.userFolderEditUser(user.getId(), password, roles, domains)

    
