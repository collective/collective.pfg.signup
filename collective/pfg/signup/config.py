"""config -- shared values"""
from Products.CMFCore.permissions import setDefaultRoles

PROJECTNAME = 'collective.pfg.signup'
ADD_PERMISSIONS = {
    'SignUpAdapter': 'collective.pfg.signup: Add SignUpAdapter',
    }
setDefaultRoles(ADD_PERMISSIONS['SignUpAdapter'],
                ('Manager', 'Owner', 'Contributor', 'Site Administrator')
)

from Products.Archetypes.atapi import DisplayList
MESSAGE_PRIORITIES = DisplayList((
    ('high', 'High Priority'),
    ('normal', 'Normal Priority'),
    ('low', 'Low Priority'),
    ))
