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
