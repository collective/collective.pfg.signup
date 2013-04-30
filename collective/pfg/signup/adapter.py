from BTrees.OOBTree import OOBTree
from encrypt import encode
from smtplib import SMTPRecipientsRefused
from email import message_from_string
from email.Header import Header
import logging
from persistent.list import PersistentList
from persistent.mapping import PersistentMapping

from zope.interface import implements
from zope.component import getUtility
from AccessControl import ClassSecurityInfo

from Products.Archetypes import atapi
from Products.ATContentTypes.content.base import registerATCT
from Products.ATContentTypes.content import schemata
from Products.CMFCore.utils import getToolByName
from Products.CMFCore.Expression import getExprContext
from Products.CMFCore.interfaces import ISiteRoot
from Products.statusmessages.interfaces import IStatusMessage
from Products.TALESField import TALESString

from Products.PloneFormGen.config import FORM_ERROR_MARKER
from Products.PloneFormGen.content.actionAdapter import FormAdapterSchema
from Products.PloneFormGen.content.actionAdapter import FormActionAdapter
from Products.PloneFormGen.interfaces import IPloneFormGenActionAdapter

from collective.pfg.signup.interfaces import ISignUpAdapter
from collective.pfg.signup.config import PROJECTNAME
from collective.pfg.signup import _

SignUpAdapterSchema = FormAdapterSchema.copy() + atapi.Schema((

    atapi.StringField('full_name_field',
        default='fullname',
        required=False,
        widget=atapi.StringWidget(
            label=_(u'label_full_name',
            default=u'Full Name Field'),
            description=_(u'help_full_name_field',
            default=u"""Enter the id of the field that will be used for the user's full name."""),
        ),
    ),

    atapi.StringField('username_field',
        default='username',
        required=True,
        widget=atapi.StringWidget(
            label=_(u'label_username', default=u'Username Field'),
            description=_(u'help_username_field',
            default=u""""Enter the id of the field that will be used for the user's user id.
                         This field is required."""),
        ),
    ),

    atapi.StringField('email_field',
        default='email',
        required=True,
        widget=atapi.StringWidget(
            label=_(u'label_email', default=u'Email Field'),
            description=_(u'help_email_field',
            default=u""""Enter the id of the field that will be used for the user's email address.
                         This field is required."""),
        ),
    ),

    atapi.StringField('password_field',
        required=False,
        widget=atapi.StringWidget(
            label=_(u'label_password', default=u'Password Field'),
            description=_(u'help_password_field',
            default=u""""Enter the id of the field that will be used for the user's password.
                         If the Approval Group Template field is empty, and this field is empty,
                         users signing up will be sent a password reset email."""),
        ),
    ),

    atapi.StringField('password_verify_field',
        required=False,
        widget=atapi.StringWidget(
            label=_(u'label_password_verify', default=u'Password Verify Field'),
            description=_(u'help_password_verify_field',
            default=u""""If there is a password and password verify field and the Approval Group Template field is empty,
                         Users will be able to set their passwords and login immediately."""),
        ),
    ),

    TALESString('user_group_template',
        default='string:${department}_${role}',
        required=True,
        widget=atapi.StringWidget(
            label=_(u'label_user_group_template',
            default=u'Add to User Group Template'),
            description=_(u'help_add_to_user_group_template',
            default=u"""A TALES expression to calculate the group the user
                        should be added to. Fields in the form can be used to populate this.
                        eg ${department}_${role}."""),
            ),
        ),

    TALESString('approval_group_template',
        default='string:${department}_${role}_approver',
        required=False,
        widget=atapi.StringWidget(
            label=_(u'label_approval_group_template',
            default=u'Approval Group Template'),
            description=_(u'help_approval_group_template',
            default=u"""A TALES expression to calculate which group the user should be approved by.
                        Leave empty to allow creation of user accounts without any approval."""),
        ),
    ),

))


class SignUpAdapter(FormActionAdapter):
    """A form action adapter that saves signup form"""
    implements(IPloneFormGenActionAdapter, ISignUpAdapter)

    meta_type = 'SignUpAdapter'
    portal_type = 'SignUpAdapter'
    archetype_name = 'SignUp Adapter'
    default_view = 'user_approver_view'
    schema = SignUpAdapterSchema
    security = ClassSecurityInfo()

    security.declarePrivate('onSuccess')

    def __init__(self, oid, **kwargs):
        """ initialize class """
        FormActionAdapter.__init__(self, oid, **kwargs)
        self.waiting_list = OOBTree()

    def getPolicy(self, data):
        """Get the policy for how the signup adapter should treat the user.
            auto: automatically create the user, requires a password to be set within the form.
            email: send the user a password reset to verify the user's email address.
            approve: hold the user in a list waiting for approval from the approval group"""
        if data['approval_group']:
            return 'approve'
        if self.getPassword_field():
            return 'email'
        return 'auto'

    def onSuccess(self, fields, REQUEST=None):
        """Save form input."""
        # get username and password
        portal_registration = getToolByName(self, 'portal_registration')
        fullname = None
        username = None
        email = None
        password = None
        password_verify = None

        data = {}
        for field in fields:
            field_name = field.fgField.getName()
            val = REQUEST.form.get(field_name, None)
            if field_name == self.full_name_field:
                data['fullname'] = val
            elif field_name == self.username_field:
                data['username'] = val
            elif field_name == self.email_field:
                data['email'] = val
            elif field_name == self.password_field:
                data['password'] = val
            elif field_name == self.password_verify_field:
                data['password_verify'] = val
            else:
                data[field_name] = val
        # TalesField needs variables to be available from the context, so create a context and add them
        expression_context = getExprContext(self, self.aq_parent)
        for key in data.keys():
            expression_context.setGlobal(key, REQUEST.form.get(key, None))
        data['user_group'] = self.getUser_group_template(expression_context=expression_context, **data)
        data['approval_group'] = self.getApproval_group_template(expression_context=expression_context, **data)

        if data['email'] is None or data['user_group'] == "":
            # SignUpAdapter did not setup properly
            return {FORM_ERROR_MARKER: _(u'Sign Up form is not setup properly.')}

        if not data['username']:
            data['username'] = data['email']

        if not portal_registration.isMemberIdAllowed(data['username']):
            return {FORM_ERROR_MARKER: _(u'You will need to signup again.'),
                'username': _(u"The login name you selected is already "
                              u"in use or is not valid. "
                              u"Please choose another.")}
        check_id = self.check_userid(data)
        if check_id:
            return check_id

        policy = self.getPolicy(data)

        if policy == 'auto':
            result = self.autoRegister(data)
            # Just return the result, this should either be None on success or an error message
            return result

        email_from = getUtility(ISiteRoot).getProperty('email_from_address', '')
        if not portal_registration.isValidEmail(email_from):
            return {FORM_ERROR_MARKER: _(u'Portal email is not configured.')}

        if policy == 'email':
            result = self.emailRegister(data)
            return result

        if policy == 'approve':
            result = self.approvalRegister(data)
            return result

        # If we get here, then something went wrong
        return {FORM_ERROR_MARKER: _(u'The form is currently unavailable')}

    def check_userid(self, data):
        """Make sure the user does not already exist or on the waiting list"""
        if data['username'] in self.waiting_list.keys():
            # user id is already on waiting list
            return {FORM_ERROR_MARKER: _(u'You will need to signup again.'),
                'username': _(u'The login name you selected is already in use')}
        # TODO check email is not already in use either in existing users or in waiting_list

    def approvalRegister(self, data):
        """User type requires approval,
        so store them on the approval list"""
        portal_groups = getToolByName(self, 'portal_groups')
        # make sure password fields are empty
        data['password'] = ''
        data['password_verify'] = ''
        self.waiting_list[data['username']] = data
        self.send_waiting_approval_email(data)

        # need an email address for the approvers group
        approval_group = portal_groups.getGroupById(data['approval_group'])
        if approval_group is None:
            self.send_approval_group_problem_email(data)
            return
        approval_email = approval_group.getProperty('email')
        if not approval_email:
            self.send_approval_group_problem_email(data)
            return
        self.send_approval_group_email(data)

    def emailRegister(self, REQUEST, data):
        """User type should be authenticated by email,
        so randomize their password and send a password reset"""
        portal_registration = getToolByName(self, 'portal_registration')
        data['password'] = portal_registration.generatePassword()
        result = self.create_member(REQUEST, data, True)
        return result

    def autoRegister(self, REQUEST, data):
        """User type can be auto registered, so pass them through"""
        verified = self.validate_password(data)
        if verified:
            return verified

        self.create_group(data['user_group'])

        # shouldn't store this in the pfg, as once the user is created, we shouldn't care
        result = self.create_member(REQUEST, data, False)
        return result

    def create_member(self, request, data, reset_password=False):
        portal_membership = getToolByName(self, 'portal_membership')
        portal_registration = getToolByName(self, 'portal_registration')
        portal_groups = getToolByName(self, 'portal_groups')
        username = data['username']

        # TODO: add switch to prevent groups being created on the fly
        user_group = data['user_group']
        self.create_group(user_group)
        # need to recheck the member has not been created in the meantime
        member = portal_membership.getMemberById(username)
        if member is None:
            # need to also pass username in properties, otherwise the user isn't found
            # when setting the properties
            try:
                member = portal_registration.addMember(
                    username, data['password'], [],
                    properties={'username': username,
                                'fullname': data['fullname'],
                                'email': data['email']})
            except(AttributeError, ValueError), err:
                logging.exception(err)
                return {FORM_ERROR_MARKER: err}

            portal_groups.addPrincipalToGroup(member.getUserName(), user_group)
            if reset_password:
                # send out reset password email
                portal_registration.mailPassword(username, request)

        else:
            return {FORM_ERROR_MARKER: "This user already exists"}

    def create_group(self, user_group, title=None, email=None):
        """Create the group"""
        # This raises an error, as setGroupProperties does not yet exist on the group
        portal_groups = getToolByName(self, 'portal_groups')
        properties = {}
        if title is not None:
            properties['title'] = title
        if email is not None:
            properties['email'] = email
        if not user_group in portal_groups.getGroupIds():
            try:
                portal_groups.addGroup(user_group, properties=properties)
            except AttributeError:
                pass
            #portal_groups.editGroup(user_group, properties=properties)

    def validate_password(self, data):
        errors = {}
        if not data['password']:
            errors['password'] = _(u'Please enter a password')
        if not data['password_verify']:
            errors['password_verify'] = _(u'Please enter a password')
        if errors:
            errors[FORM_ERROR_MARKER] = _(u'Please enter a password')
            return errors
        if data['password'] != data['password_verify']:
            errors[FORM_ERROR_MARKER] = _(u'The passwords do not match')
            errors['password'] = _(u'The passwords do not match')
            errors['password_verify'] = _(u'The passwords do not match')
            return errors

        registration = getToolByName(self, 'portal_registration')
        # This should ensure that the password is at least 5 chars long, but
        # if the user filling in the form has ManagePortal permission it is ignored
        error_message = registration.testPasswordValidity(data['password'])
        if error_message:
            errors[FORM_ERROR_MARKER] = error_message
            errors['password'] = ' '
            errors['password_verify'] = ' '
            return errors
        return None

    def approve_user(self):
        """Approve the user based on the request"""
        request = self.REQUEST
        portal_registration = getToolByName(self, 'portal_registration')
        userid = request.form['userid']
        user = self.waiting_list.get(userid)
        if self.user_not_permitted(user['approval_group']):
            return
        user['password'] = portal_registration.generatePassword()
        self.create_member(request, user)
        self.send_approval_email(user)
        self.waiting_list.pop(userid)
        self.plone_utils.addPortalMessage(_(u'User has been approved.'))
        request.RESPONSE.redirect(self.absolute_url())

    def reject_user(self):
        """Reject the user based on the request"""
        request = self.REQUEST
        portal_registration = getToolByName(self, 'portal_registration')
        userid = request.form['userid']
        user = self.waiting_list.get(userid)
        if self.user_not_permitted(user['approval_group']):
            return
        user = self.waiting_list.pop(userid)
        self.send_reject_email(user)
        self.plone_utils.addPortalMessage(_(u'User has been rejected.'))
        request.RESPONSE.redirect(self.absolute_url())

    def user_not_permitted(self, group):
        """Check the user is permmited to approve/reject the user"""
        portal_membership = getToolByName(self, 'portal_membership')
        current_user = portal_membership.getAuthenticatedMember()
        current_user_groups = current_user.getGroups()
        if group not in current_user_groups:
            self.plone_utils.addPortalMessage(_(u'You do not have permission to do this.'))
            self.REQUEST.RESPONSE.redirect(self.absolute_url())
            return True

    def get_portal_email_properties(self):
        """Return the portal title for use in emails"""
        portal_url = getToolByName(self, 'portal_url')
        portal = portal_url.getPortalObject()
        return portal.Title(), portal.getProperty('email_from_address'), portal.getProperty('email_from_name')

    def send_approval_group_problem_email(self, data):
        """There is a problem with the approval group so alert someone"""
        portal_title, portal_email, portal_email_name = self.get_portal_email_properties()
        portal_groups = getToolByName(self, 'portal_groups')
        administrators = portal_groups.getGroupById('Administrators')
        administrators_email = administrators.getProperty('email')
        if not administrators_email:
            administrators_email = getUtility(ISiteRoot).getProperty('email_from_address', '')
        portal_groups = getToolByName(self, 'portal_groups')
        approval_group = portal_groups.getGroupById(data['approval_group'])
        if approval_group is None:
            approval_group_title = data['approval_group']
        else:
            approval_group_title = approval_group.getProperty('title')
        messageText = []
        # TODO this could do with tidying up. Email could be going to admin group, and would be useful to differentiate between no group and no email
        messageText.append(u'Dear %s,' % portal_email_name)
        messageText.append('')
        messageText.append(u'There is a problem with one of the approval groups.')
        messageText.append(u'The group, %s, either does not exist or has no email address, and there is a user waiting to be approved by that group.' % approval_group_title)
        messageText.append('')
        messageText.append('Thank you')
        messageText.append(portal_email_name)
        messageText = '\n'.join(messageText)
        subject = portal_title + ' approval group problem'
        self.send_email(messageText, mto=administrators_email, mfrom=portal_email, subject=subject)

    def send_waiting_approval_email(self, data):
        """Send an approval request email"""
        portal_title, portal_email, portal_email_name = self.get_portal_email_properties()
        messageText = []
        messageText.append(u'Dear %s,' % data['fullname'])
        messageText.append('')
        messageText.append(u'Thank you for registering with the %s site. Your account is waiting for approval.' % portal_title)
        messageText.append('')
        messageText.append('Thank you')
        messageText.append(portal_email_name)
        messageText = '\n'.join(messageText)
        subject = portal_title + ' account request submited for approval'
        self.send_email(messageText, mto=data['email'], mfrom=portal_email, subject=subject)
        return

    def send_approval_group_email(self, data):
        """Send an email to approval group that there is a user waiting for approval"""
        portal_title, portal_email, portal_email_name = self.get_portal_email_properties()
        messageText = []
        # TODO need a salutation from somewhere
        messageText.append(u'Dear,')
        messageText.append('')
        messageText.append(u'There is a user waiting for approval. Please use the following link to login and approve/reject them.')
        messageText.append('')
        messageText.append(self.absolute_url())
        messageText.append('')
        messageText.append('Thank you')
        messageText.append(portal_email_name)
        messageText = '\n'.join(messageText)
        subject = portal_title + ' user Waiting for approval'
        self.send_email(messageText, mto=data['email'], mfrom=portal_email, subject=subject)
        return

    def send_approval_email(self, data):
        """Send an email confirming approval"""
        portal_title, portal_email, portal_email_name = self.get_portal_email_properties()
        reset_tool = getToolByName(self, 'portal_password_reset')
        reset = reset_tool.requestReset(data['username'])
        portal_url = getToolByName(self, 'portal_url')()
        password_url = '%s/passwordreset/%s' % (portal_url, reset['randomstring'])
        # should we send the user id with the password link email?
        messageText = []
        messageText.append(u'Dear %s,' % data['fullname'])
        messageText.append('')
        messageText.append(u'Your account request has been accepted. Please use the following link to set your password.')
        messageText.append('')
        messageText.append(password_url)
        messageText.append('')
        messageText.append('This link will expire at: %s.' % reset['expires'].strftime('%H:%M %d/%m/%Y'))
        messageText.append('')
        messageText.append('Thank you')
        messageText.append(portal_email_name)
        messageText = '\n'.join(messageText)
        subject = portal_title + ' account approved'
        self.send_email(messageText, mto=data['email'], mfrom=portal_email, subject=subject)
        return

    def send_reject_email(self, data):
        """Send an email on rejection"""
        portal_title, portal_email, portal_email_name = self.get_portal_email_properties()
        messageText = []
        messageText.append(u'Dear %s,' % data['fullname'])
        messageText.append('')
        messageText.append(u'Your account request has been declined. If you think this is in error, please contact the site administrator.')
        messageText.append('')
        messageText.append('Thank you')
        messageText.append(portal_email_name)
        messageText = '\n'.join(messageText)
        subject = portal_title + ' account request declined'
        self.send_email(messageText, mto=data['email'], mfrom=portal_email, subject=subject)
        return

    def send_email(self, messageText, mto, mfrom, subject):
        encoding = getUtility(ISiteRoot).getProperty('email_charset', 'utf-8')
        mail_host = getToolByName(self, 'MailHost')
        try:
            messageText = message_from_string(messageText.encode(encoding))
            messageText.set_charset(encoding)
            messageText['X-Custom'] = Header(u'Some Custom Parameter', encoding)
            mail_host.send(
                messageText, mto=mto,
                mfrom=mfrom,
                subject=subject)
        except SMTPRecipientsRefused:
            # Don't disclose email address on failure
            raise SMTPRecipientsRefused(
                'Recipient address rejected by server')

registerATCT(SignUpAdapter, PROJECTNAME)
