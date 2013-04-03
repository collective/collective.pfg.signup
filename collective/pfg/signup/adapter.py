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
    atapi.StringField('full_name_field',
                      default='fullname',
                      required=False,
                      widget=atapi.StringWidget(
                          label=_(u'label_full_name',
                              default=u'Full Name Field'),
                          description=_(u'help_full_name_field',
                              default=u"Enter full name field from the sign up "
                                      u"form."),
                          ),
                      ),
    atapi.StringField('username_field',
                      default='username',
                      required=False,
                      widget=atapi.StringWidget(
                          label=_(u'label_username', default=u'Username Field'),
                          description=_(u'help_username_field',
                              default=u"Enter username field from the "
                                      u"sign up form."),
                      ),
                      ),
    atapi.StringField('email_field',
                      default='email',
                      required=True,
                      widget=atapi.StringWidget(
                          label=_(u'label_email', default=u'Email Field'),
                          description=_(u'help_email_field',
                              default=u"Enter email field from the sign up "
                                      u"form."),
                      ),
                      ),
    atapi.StringField('password_field',
                      default='password',
                      required=False,
                      widget=atapi.StringWidget(
                          label=_(u'label_password', default=u'Password Field'),
                          description=_(u'help_password_field',
                              default=u'Enter password field from the sign '
                                      u'up form.'),
                      ),
                      ),
    atapi.StringField('council_field',
                      default='council',
                      required=False,
                      widget=atapi.StringWidget(
                          label=_(u'label_council', default=u'Council Field'),
                          description=_(u'help_council_field',
                              default=u'Enter council field from the sign up '
                                      u'form.'),
                          ),
                      ),
    atapi.StringField('role_field',
                      default='role',
                      required=False,
                      widget=atapi.StringWidget(
                          label=_(u'label_role', default=u'Role Field'),
                          description=_(u'help_role_field',
                              default=u'Enter role field from the sign up '
                                      u'form.'),
                          ),
                      ),
    atapi.StringField('user_group',
                      default='user-group',
                      required=True,
                      widget=atapi.StringWidget(
                          label=_(u'label_user_group',
                              default=u'Add to User Group'),
                          description=_(u'help_add_to_user_group',
                              default=u'Enter user group name that users added '
                                      u'to.'),
                      ),
                      ),
    atapi.StringField('approval_group',
                      default='approval-group',
                      required=False,
                      widget=atapi.StringWidget(
                          label=_(u'label_approval_group',
                              default=u'Approval Group Field'),
                          description=_(u'help_approval_group_field',
                              default=u"Enter approval group field where group "
                                      u"that need to approve this user group."),
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
        fullname = None
        username = None
        email = None
        password = None
        council = None
        role = None
        group = self.user_group
        approval_group = self.approval_group
        reset_password = False

        for field in fields:
            fname = field.fgField.getName()
            val = REQUEST.form.get(fname, None)
            if fname == self.full_name_field:
                fullname = val
            elif fname == self.username_field:
                username = val
            elif fname == self.email_field:
                email = val
            elif fname == self.password_field:
                password = val
            elif fname == self.council_field:
                council = val
            elif fname == self.role_field:
                role = val

        #TODO should we verify the two passwords are the same again?
        import ipdb; ipdb.set_trace()

        if email is None or group == "":
            # SignUpAdapter did not setup properly
            return {FORM_ERROR_MARKER: 'Sign Up form is not setup properly.'}

        if not username:
            username = email

        if approval_group:
            pass
        else:
            # auto registration

            # username validation
            site = getSite()
            registration = getToolByName(site, 'portal_registration')
            if username == site.getId():
                return {FORM_ERROR_MARKER: 'You will need to signup again.',
                        'username': _(u"This username is reserved. "
                                      u"Please choose a different name.")}

            if not registration.isMemberIdAllowed(username):
                return {FORM_ERROR_MARKER: 'You will need to signup again.',
                        'username': _(u"The login name you selected is already "
                                      u"in use or is not valid. "
                                      u"Please choose another.")}

            if password:

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

            else:
                # generate random string and
                # set send out reset password email flag
                password = registration.generatePassword()
                reset_password = True

            portal_groups = getToolByName(site, 'portal_groups')
            if not group in portal_groups.getGroupIds():
                portal_groups.addGroup(group)

            try:
                member = registration.addMember(
                    username, password,
                    properties={'username': username,
                                'email': email})
                #groups = portal_groups.getGroupsByUserId(member.getUserName())
                portal_groups.addPrincipalToGroup(member.getUserName(), group)
                if member.has_role('Member'):
                    site.acl_users.portal_role_manager.removeRoleFromPrincipal(
                        'Member', member.getUserName())

                if reset_password:
                    # send out reset password email
                    registration.mailPassword(username, REQUEST)

            except(AttributeError, ValueError), err:
                logging.exception(err)
                IStatusMessage(self.request).addStatusMessage(err, type="error")
                return

        return

registerATCT(SignUpAdapter, PROJECTNAME)
