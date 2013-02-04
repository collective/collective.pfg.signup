from zope.interface import implements
from AccessControl import ClassSecurityInfo
from Products.Archetypes import atapi
from Products.ATContentTypes.content.base import registerATCT
from Products.ATContentTypes.content import schemata
from Products.PloneFormGen.interfaces import IPloneFormGenActionAdapter
from Products.PloneFormGen.content.actionAdapter import FormAdapterSchema
from Products.PloneFormGen.content.actionAdapter import FormActionAdapter
from Products.PloneFormGen.config import FORM_ERROR_MARKER
from collective.pfg.signup.interfaces import ISignUpAdapter
from collective.pfg.signup.config import PROJECTNAME
from collective.pfg.signup import _
from Products.statusmessages.interfaces import IStatusMessage
from Products.CMFCore.utils import getToolByName
from zope.app.component.hooks import getSite
from zope.component import getUtility
from Products.CMFCore.interfaces import ISiteRoot

import logging

SignUpAdapterSchema = FormAdapterSchema.copy() + atapi.Schema((
    atapi.StringField('username_field',
        default='username',
        required=True,
        widget=atapi.StringWidget(
            label=_(u'label_username', default=u'Username Field'),
            description=_(u'help_username_field',
                default=u"Enter username field from the sign up form."),
         ),
    ),
    atapi.StringField('email_field',
        default='email',
        required=True,
        widget=atapi.StringWidget(
            label=_(u'label_email', default=u'Email Field'),
            description=_(u'help_email_field',
                default=u"Enter email field from the sign up form."),
            ),
        ),
    atapi.StringField('password_field',
        default='password',
        required=True,
        widget=atapi.StringWidget(
            label=_(u'label_password', default=u'Password Field'),
            description=_(u'help_password_field',
                default=u'Enter password field from the sign up form.'),
        ),
    ),
    atapi.StringField('group_field',
        default='caravan_group',
        required=False,
        widget=atapi.StringWidget(
            label=_(u'label_user_group', default=u'Add to User Group'),
            description=_(u'help_add_to_user_group',
                default=u'Enter user group name that users added to.'),
        ),
    ),
))


class SignUpAdapter(FormActionAdapter):
    """A form action adapter that saves signup form"""
    implements(IPloneFormGenActionAdapter, ISignUpAdapter)

    meta_type = 'SignUpAdapter'
    portal_type = 'SignUpAdapter'
    archetype_name = 'SignUp Adapter'
    schema = SignUpAdapterSchema
    security = ClassSecurityInfo()

    security.declarePrivate('onSuccess')

    def onSuccess(self, fields, REQUEST=None):
        """Save form input."""
        # get username and password
        username = None
        password = None
        email = None
        group = self.group_field
        for field in fields:
            fname = field.fgField.getName()
            val = REQUEST.form.get(fname, None)
            if fname == self.username_field:
                username = val
            elif fname == self.email_field:
                email = val
            elif fname == self.password_field:
                password = val

        #TODO should we verify the two passwords are the same again?

        if username is None or password is None or email is None or group == "":
            # SignUpAdapter did not setup properly
            return {FORM_ERROR_MARKER: 'Sign Up form is not setup properly.'}

        # username validation
        site = getSite()
        registration = getToolByName(site, 'portal_registration')
        if username == site.getId():
            return {FORM_ERROR_MARKER: 'You will need to signup again.',
                    'username': _(u"This username is reserved. Please choose a "
                                  "different name.")}

        if not registration.isMemberIdAllowed(username):
            return {FORM_ERROR_MARKER: 'You will need to signup again.',
                    'username': _(u"The login name you selected is already in "
                                  "use or is not valid. "
                                  "Please choose another.")}

        failMessage = registration.testPasswordValidity(password)
        if failMessage is not None:
            return {FORM_ERROR_MARKER: 'You will need to signup again.',
                    'password': failMessage}

        # do the registration
        #TODO should based on turn on self-registration flag?
        #refer to plone.app.users/browser/register.py
        # data = {'username': 'user3', 'fullname': u'User3',
        # 'password': u'qwert', 'email': 'user3@mail.com',
        # 'password_ctl': u'qwert'}
        if isinstance(password, unicode):
            password = password.encode('utf8')

        portal_groups = getToolByName(site, 'portal_groups')
        if not group in portal_groups.getGroupIds():
            portal_groups.addGroup(group)

        try:
            member = registration.addMember(username, password,
                                            properties={'username': username,
                                                        'email': email})
            #groups = portal_groups.getGroupsByUserId(member.getUserName())
            portal_groups.addPrincipalToGroup(member.getUserName(), group)
            if member.has_role('Member'):
                site.acl_users.portal_role_manager.removeRoleFromPrincipal(
                    'Member', member.getUserName())

        except(AttributeError, ValueError), err:
            logging.exception(err)
            IStatusMessage(self.request).addStatusMessage(err, type="error")
            return

        return

registerATCT(SignUpAdapter, PROJECTNAME)
