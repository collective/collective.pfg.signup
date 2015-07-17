"""Plone form gen signed up adapter."""
from AccessControl import ClassSecurityInfo
from AccessControl import getSecurityManager
from AccessControl import Unauthorized
from BTrees.OOBTree import OOBTree
from Products.Archetypes import atapi
from Products.ATContentTypes.content.base import registerATCT
from Products.CMFCore.Expression import getExprContext
from Products.CMFCore.interfaces import ISiteRoot
from Products.CMFCore.permissions import ManagePortal
from Products.CMFCore.utils import getToolByName
from Products.PloneFormGen.config import FORM_ERROR_MARKER
from Products.PloneFormGen.content.actionAdapter import FormActionAdapter
from Products.PloneFormGen.content.actionAdapter import FormAdapterSchema
from Products.PloneFormGen.interfaces import IPloneFormGenActionAdapter
from Products.TALESField import TALESString

from collective.pfg.signup import _
from collective.pfg.signup.config import PROJECTNAME
from collective.pfg.signup.interfaces import ISignUpAdapter
from email import message_from_string
from smtplib import SMTPRecipientsRefused
from smtplib import SMTPServerDisconnected
from zope.component import getUtility
from zope.interface import implements

import logging
import transaction

SignUpAdapterSchema = FormAdapterSchema.copy() + atapi.Schema((

    atapi.StringField(
        'full_name_field',
        default='fullname',
        required=False,
        widget=atapi.StringWidget(
            label=_(u'label_full_name', default=u'Full Name Field'),  # noqa H702
            description=_(
                u'help_full_name_field',
                default=u"""Enter the id of the field that will be used for the
                            user's full name."""),
        ),
    ),

    atapi.StringField(
        'username_field',
        required=False,
        widget=atapi.StringWidget(
            label=_(u'label_username', default=u'Username Field'),
            description=_(
                u'help_username_field',
                default=u"""Enter the id of the field that will be used for the
                            user's user id. If this field is left empty the
                            email address will be used for the username."""),
        ),
    ),

    atapi.StringField(
        'email_field',
        default='email',
        required=True,
        widget=atapi.StringWidget(
            label=_(u'label_email', default=u'Email Field'),
            description=_(
                u'help_email_field',
                default=u"""Enter the id of the field that will be used for the
                            user's email address. This field is required."""),
        ),
    ),

    atapi.StringField(
        'password_field',
        required=False,
        widget=atapi.StringWidget(
            label=_(u'label_password', default=u'Password Field'),
            description=_(
                u'help_password_field',
                default=u"""Enter the id of the field that will be used for the
                            user's password. If the Approval Group Template
                            field is empty, and this field is empty, users
                            signing up will be sent a password reset email.
                            """),
        ),
    ),

    atapi.StringField(
        'password_verify_field',
        required=False,
        widget=atapi.StringWidget(
            label=_(
                u'label_password_verify',
                default=u'Password Verify Field'),
            description=_(
                u'help_password_verify_field',
                default=u"""If there is a password and password verify field
                            and the Approval Group Template field is empty,
                            Users will be able to set their passwords and login
                            immediately."""),
        ),
    ),

    TALESString(
        'user_group_template',
        required=True,
        widget=atapi.StringWidget(
            label=_(
                u'label_user_group_template',
                default=u'Add to User Group Template'),
            description=_(
                u'help_add_to_user_group_template',
                default=u"""A TALES expression to calculate the group the user
                            should be added to. Fields in the form can be used
                            to populate this. eg string:${department}_${role}.
                            """),
            ),
        ),

    TALESString(
        'approval_group_template',
        required=False,
        widget=atapi.StringWidget(
            label=_(
                u'label_approval_group_template',
                default=u'Approval Group Template'),
            description=_(
                u'help_approval_group_template',
                default=u"""A TALES expression to calculate which group the
                            user should be approved by. Leave empty to allow
                            creation of user accounts without any approval. eg
                            python:request.form['role'] == 'manager' and
                            'Administrators' or request.form['department'] +
                            '_manager'"""),
        ),
    ),

))


class SignUpAdapter(FormActionAdapter):

    """A form action adapter that saves signup form."""

    implements(IPloneFormGenActionAdapter, ISignUpAdapter)

    meta_type = 'SignUpAdapter'
    portal_type = 'SignUpAdapter'
    archetype_name = 'SignUp Adapter'
    default_view = 'user_approver_view'
    schema = SignUpAdapterSchema
    security = ClassSecurityInfo()

    security.declarePrivate('onSuccess')

    def __init__(self, oid, **kwargs):
        """Initialize class."""
        FormActionAdapter.__init__(self, oid, **kwargs)
        self.waiting_list = OOBTree()

    def getPolicy(self, data):
        """Get the policy for how the signup adapter should treat the user.

        auto: automatically create the user, requires a password to be set
              within the form.
        email: send the user a password reset to verify the user's email
               address.
        approve: hold the user in a list waiting for approval from the
                 approval group
        """
        if data['approval_group']:
            return 'approve'
        if self.getPassword_field():
            return 'email'
        return 'auto'

    def onSuccess(self, fields, REQUEST=None):  # noqa C901
        """Save form input."""
        # get username and password
        portal_registration = getToolByName(self, 'portal_registration')

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
        if 'email' not in data:
            return {
                FORM_ERROR_MARKER: _(u'Sign Up form is not setup properly.')}
        if 'username' not in data:
            data['username'] = data['email']
        # TalesField needs variables to be available from the context, so
        # create a context and add them
        expression_context = getExprContext(self, self.aq_parent)
        for key in data.keys():
            expression_context.setGlobal(key, REQUEST.form.get(key, None))
        data['user_group'] = self.getUser_group_template(
            expression_context=expression_context, **data)
        data['approval_group'] = self.getApproval_group_template(
            expression_context=expression_context, **data)

        if data['email'] is None or data['user_group'] == "":
            # SignUpAdapter did not setup properly
            return {
                FORM_ERROR_MARKER: _(u'Sign Up form is not setup properly.')}

        if not data['username']:
            data['username'] = data['email']

        # force email and username to lowercase
        data['username'] = data['username'].lower()
        data['email'] = data['email'].lower()

        if not portal_registration.isValidEmail(data['email']):
            return {
                FORM_ERROR_MARKER: _(u'You will need to signup again.'),
                'email': _(u'This is not a valid email address')}
        if not portal_registration.isMemberIdAllowed(data['username']):
            error_text = _(u"""The login name you selected is already in use or is not valid.
                               Please choose another.""")
            if self.getUsername_field():
                return {
                    FORM_ERROR_MARKER: _(u'You will need to signup again.'),
                    'username': error_text}
            else:
                return {
                    FORM_ERROR_MARKER: _(u'You will need to signup again.'),
                    'email': error_text}
        check_id = self.check_userid(data)
        if check_id:
            return check_id

        policy = self.getPolicy(data)

        if policy == 'auto':
            result = self.autoRegister(data)
            # Just return the result, this should either be None on success or
            # an error message
            return result

        email_from = getUtility(ISiteRoot).getProperty(
            'email_from_address', '')
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
        """Make sure the user does not already exist or on the waiting list."""
        if data['username'] in self.waiting_list.keys():
            # user id is already on waiting list
            error_text = _(
                u"""The login name you selected is already in use.""")
            if self.getUsername_field():
                return {
                    FORM_ERROR_MARKER: _(u'You will need to signup again.'),
                    'username': error_text}
            else:
                return {
                    FORM_ERROR_MARKER: _(u'You will need to signup again.'),
                    'email': error_text}
        # TODO(ivanteoh): check email is not already in use either in existing
        # users or in waiting_list

    def approvalRegister(self, data):
        """User type requires approval.

        So store them on the approval list.
        """
        portal_groups = getToolByName(self, 'portal_groups')
        # make sure password fields are empty
        data['password'] = ''
        data['password_verify'] = ''
        self.waiting_list[data['username']] = data
        self.send_waiting_approval_email(data)

        # need an email address for the approvers group
        approval_group = portal_groups.getGroupById(data['approval_group'])
        if approval_group is None:
            self.send_approval_group_not_exist_email(data)
            return
        approval_email = approval_group.getProperty('email')
        if not approval_email:
            approval_group_members = approval_group.getGroupMembers()
            if approval_group_members:
                self.send_approval_group_members_email(
                    data, approval_group_members)
            else:
                self.send_approval_group_problem_email(data)
            return
        self.send_approval_group_email(data)

    def emailRegister(self, REQUEST, data):
        """User type should be authenticated by email.

        So randomize their password and send a password reset.
        """
        portal_registration = getToolByName(self, 'portal_registration')
        data['password'] = portal_registration.generatePassword()
        result = self.create_member(REQUEST, data, True)
        return result

    def autoRegister(self, REQUEST, data):
        """User type can be auto registered, so pass them through."""
        verified = self.validate_password(data)
        if verified:
            return verified

        self.create_group(data['user_group'])

        # shouldn't store this in the pfg, as once the user is created, we
        # shouldn't care
        result = self.create_member(REQUEST, data, False)
        return result

    def create_member(self, request, data, reset_password=False):
        """Create member."""
        portal_membership = getToolByName(self, 'portal_membership')
        portal_registration = getToolByName(self, 'portal_registration')
        portal_groups = getToolByName(self, 'portal_groups')
        username = data['username']

        # TODO(ivanteoh): add switch to prevent groups being created on the fly
        user_group = data['user_group']
        self.create_group(user_group)
        # need to recheck the member has not been created in the meantime
        member = portal_membership.getMemberById(username)
        if member is None:
            # need to also pass username in properties, otherwise the user
            # isn't found when setting the properties
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
        """Create the group."""
        # This raises an error, as setGroupProperties does not yet exist on the
        # group
        portal_groups = getToolByName(self, 'portal_groups')
        properties = {}
        if title is not None:
            properties['title'] = title
        if email is not None:
            properties['email'] = email
        if user_group not in portal_groups.getGroupIds():
            try:
                portal_groups.addGroup(user_group, properties=properties)
            except AttributeError:
                pass
        if title or email:
            # commit a subtransaction, to instantiate the group properly, so we
            # can edit it
            transaction.get().commit()
            portal_groups.editGroup(user_group, properties=properties)

    def validate_password(self, data):
        """Validate password."""
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
        # if the user filling in the form has ManagePortal permission it is
        # ignored
        error_message = registration.testPasswordValidity(data['password'])
        if error_message:
            errors[FORM_ERROR_MARKER] = error_message
            errors['password'] = ' '
            errors['password_verify'] = ' '
            return errors
        return None

    def approve_user(self):
        """Approve the user based on the request."""
        request = self.REQUEST
        portal_registration = getToolByName(self, 'portal_registration')
        userid = request.form['userid']
        user = self.waiting_list.get(userid)
        if user is None:
            self.plone_utils.addPortalMessage(
                _(u'This user has already been dealt with.'))
        elif self.user_not_permitted(user['approval_group']):
            self.plone_utils.addPortalMessage(
                _(u'You do not have permission to manage this user.'))
        else:
            user['password'] = portal_registration.generatePassword()
            self.create_member(request, user)
            self.send_approval_email(user)
            self.waiting_list.pop(userid)
            self.plone_utils.addPortalMessage(_(u'User has been approved.'))
        request.RESPONSE.redirect(self.absolute_url())

    def reject_user(self):
        """Reject the user based on the request."""
        request = self.REQUEST
        # portal_registration = getToolByName(self, 'portal_registration')
        userid = request.form['userid']
        user = self.waiting_list.get(userid)
        if user is None:
            self.plone_utils.addPortalMessage(
                _(u'This user has already been dealt with.'))
        elif self.user_not_permitted(user['approval_group']):
            self.plone_utils.addPortalMessage(
                _(u'You do not have permission to manage this user.'))
        else:
            user = self.waiting_list.pop(userid)
            self.send_reject_email(user)
            self.plone_utils.addPortalMessage(_(u'User has been rejected.'))
        request.RESPONSE.redirect(self.absolute_url())

    def user_not_permitted(self, group):
        """Check the user is permmited to approve/reject the user."""
        sm = getSecurityManager()
        portal = getUtility(ISiteRoot)
        portal_membership = getToolByName(self, 'portal_membership')
        if sm.checkPermission(ManagePortal, portal):
            return False
        elif portal_membership.isAnonymousUser():
            raise Unauthorized('You need to login to access this page.')
        current_user = portal_membership.getAuthenticatedMember()
        current_user_groups = current_user.getGroups()
        if group not in current_user_groups:
            self.plone_utils.addPortalMessage(
                _(u'You do not have permission to do this.'))
            self.REQUEST.RESPONSE.redirect(self.absolute_url())
            return True

    def get_portal_email_properties(self):
        """Return the portal title for use in emails."""
        portal_url = getToolByName(self, 'portal_url')
        portal = portal_url.getPortalObject()
        return (
            portal.Title(), portal.getProperty('email_from_address'),
            portal.getProperty('email_from_name'))

    def send_approval_group_not_exist_email(self, data):
        """The approval group does not exist."""
        portal_title, portal_email, portal_email_name = \
            self.get_portal_email_properties()
        portal_url = getToolByName(self, 'portal_url')()
        portal_groups = getToolByName(self, 'portal_groups')
        administrators = portal_groups.getGroupById('Administrators')
        administrators_email = administrators.getProperty('email')
        if not administrators_email:
            administrators_email = getUtility(ISiteRoot).getProperty(
                'email_from_address', '')
        portal_groups = getToolByName(self, 'portal_groups')
        approval_group = portal_groups.getGroupById(data['approval_group'])
        if approval_group is None:
            approval_group_title = data['approval_group']
            # email_link = portal_url + '/@@usergroup-groupprefs'
        else:
            approval_group_title = approval_group.getProperty('title')
            # email_link = portal_url + '/@@usergroup-groupdetails?groupname='
            # + data['approval_group']
            if not approval_group_title:
                approval_group_title = data['approval_group']
        messageText = [
            self.get_approval_group_email_text(approval_group_title), ]
        messageText.append('')
        messageText.append(
            '---------------------------------------------------')
        messageText.append('')
        messageText.append(
            u"""This email has been sent to this address because the group "%s"
            currently doesn\'t exist and needs to be created.""" %
            approval_group_title)
        messageText.append('')
        messageText.append(
            u"""You can add the group using this link: %s""" %
            portal_url + '/@@usergroup-groupprefs')
        messageText.append('')
        messageText.append('Thank you,')
        messageText.append('')
        messageText.append(portal_email_name)
        messageText = '\n'.join(messageText)
        subject = portal_title + ' approval group problem'
        try:
            self.send_email(messageText, mto=administrators_email,
                            mfrom=portal_email, subject=subject)
        except SMTPServerDisconnected:
            pass
        return

    def send_approval_group_problem_email(self, data):
        """There is a problem with the approval group so alert someone."""
        portal_title, portal_email, portal_email_name = \
            self.get_portal_email_properties()
        portal_url = getToolByName(self, 'portal_url')()
        portal_groups = getToolByName(self, 'portal_groups')
        administrators = portal_groups.getGroupById('Administrators')
        administrators_email = administrators.getProperty('email')
        if not administrators_email:
            administrators_email = getUtility(ISiteRoot).getProperty(
                'email_from_address', '')
        portal_groups = getToolByName(self, 'portal_groups')
        approval_group = portal_groups.getGroupById(data['approval_group'])
        if approval_group is None:
            approval_group_title = data['approval_group']
            # email_link = portal_url + '/@@usergroup-groupprefs'
        else:
            approval_group_title = approval_group.getProperty('title')
            # email_link = portal_url + '/@@usergroup-groupdetails?groupname='
            # + data['approval_group']
            if not approval_group_title:
                approval_group_title = data['approval_group']
        messageText = [
            self.get_approval_group_email_text(approval_group_title), ]
        messageText.append('')
        messageText.append(
            '---------------------------------------------------')
        messageText.append('')
        messageText.append(
            u"""This email has been sent to this address because the group "%s"
                currently doesn\'t have any members with contact information or
                the group itself doesn\'t have contact information.""" %
            approval_group_title)
        messageText.append('')
        messageText.append(
            u"""You can add members to the group using this link: %s""" %
            portal_url + '/@@usergroup-groupmembership?groupname=' +
            data['approval_group'])
        messageText.append('')
        messageText.append('Thank you,')
        messageText.append('')
        messageText.append(portal_email_name)
        messageText = '\n'.join(messageText)
        subject = portal_title + ' approval group problem'
        try:
            self.send_email(messageText, mto=administrators_email,
                            mfrom=portal_email, subject=subject)
        except SMTPServerDisconnected:
            pass
        return

    def send_waiting_approval_email(self, data):
        """Send an approval request email."""
        portal_title, portal_email, portal_email_name = \
            self.get_portal_email_properties()
        messageText = []
        messageText.append(u'Dear %s,' % data['fullname'])
        messageText.append('')
        messageText.append(
            u"""Thank you for registering with the %s site. Your
                account is waiting for approval.""" % portal_title)
        messageText.append('')
        messageText.append('Thank you,')
        messageText.append('')
        messageText.append(portal_email_name)
        messageText = '\n'.join(messageText)
        subject = portal_title + ' account request submited for approval'
        try:
            self.send_email(messageText, mto=data['email'],
                            mfrom=portal_email, subject=subject)
        except SMTPServerDisconnected:
            pass
        return

    def send_approval_group_email(self, data):
        """Send an email to approval group.

        When there is a user waiting for approval.
        """
        portal_title, portal_email, portal_email_name = \
            self.get_portal_email_properties()
        portal_groups = getToolByName(self, 'portal_groups')
        # already checked that the group exists and has an email address
        approval_group = portal_groups.getGroupById(data['approval_group'])
        approval_group_email = approval_group.getProperty('email')
        approval_group_title = approval_group.getProperty('title')
        if not approval_group_title:
            approval_group_title = data['approval_group']
        messageText = self.get_approval_group_email_text(approval_group_title)
        subject = portal_title + ' user Waiting for approval'
        try:
            self.send_email(messageText, mto=approval_group_email,
                            mfrom=portal_email, subject=subject)
        except SMTPServerDisconnected:
            pass
        return

    def send_approval_group_members_email(self, data, approval_group_members):
        """Send an email to each member of the approval group.

        When there is a user waiting for approval.
        """
        portal_title, portal_email, portal_email_name = \
            self.get_portal_email_properties()
        subject = portal_title + ' user Waiting for approval'
        for member in approval_group_members:
            email = member.getProperty('email')
            name = member.getProperty('fullname')
            if not name:
                name = email
            messageText = self.get_approval_group_email_text(name)
            self.send_email(messageText, mto=email, mfrom=portal_email,
                            subject=subject)
        return

    def get_approval_group_email_text(self, name):
        """Construct the body text of the email."""
        portal_title, portal_email, portal_email_name = \
            self.get_portal_email_properties()
        messageText = []
        messageText.append(u'Dear %s,' % name)
        messageText.append('')
        messageText.append(u"""There is a user waiting for approval. Please use
                               the following link to login and approve/reject
                               them.""")
        messageText.append('')
        messageText.append(self.absolute_url())
        messageText.append('')
        messageText.append('Thank you,')
        messageText.append('')
        messageText.append(portal_email_name)
        messageText = '\n'.join(messageText)
        return messageText

    def send_approval_email(self, data):
        """Send an email confirming approval."""
        portal_title, portal_email, portal_email_name = \
            self.get_portal_email_properties()
        reset_tool = getToolByName(self, 'portal_password_reset')
        reset = reset_tool.requestReset(data['username'])
        portal_url = getToolByName(self, 'portal_url')()
        password_url = '%s/passwordreset/%s' % \
            (portal_url, reset['randomstring'])
        # should we send the user id with the password link email?
        messageText = []
        messageText.append(u'Dear %s,' % data['fullname'])
        messageText.append('')
        messageText.append(u"""Your account request has been accepted. Please
                               use the following link to set your password.""")
        messageText.append('')
        messageText.append(password_url)
        messageText.append('')
        messageText.append('This link will expire at: %s.' %
                           reset['expires'].strftime('%H:%M %d/%m/%Y'))
        messageText.append('')
        messageText.append('Thank you,')
        messageText.append('')
        messageText.append(portal_email_name)
        messageText = '\n'.join(messageText)
        subject = portal_title + ' account approved'
        self.send_email(messageText, mto=data['email'], mfrom=portal_email,
                        subject=subject)
        return

    def send_reject_email(self, data):
        """Send an email on rejection."""
        portal_title, portal_email, portal_email_name = \
            self.get_portal_email_properties()
        messageText = []
        messageText.append(u'Dear %s,' % data['fullname'])
        messageText.append('')
        messageText.append(u"""Your account request has been declined. If you
                               think this is in error, please contact the site
                               administrator.""")
        messageText.append('')
        messageText.append('Thank you,')
        messageText.append('')
        messageText.append(portal_email_name)
        messageText = '\n'.join(messageText)
        subject = portal_title + ' account request declined'
        self.send_email(messageText, mto=data['email'], mfrom=portal_email,
                        subject=subject)
        return

    def send_email(self, messageText, mto, mfrom, subject):
        """Send email."""
        encoding = getUtility(ISiteRoot).getProperty('email_charset', 'utf-8')
        mail_host = getToolByName(self, 'MailHost')
        try:
            messageText = message_from_string(messageText.encode(encoding))
            messageText.set_charset(encoding)
            mail_host.send(
                messageText, mto=mto,
                mfrom=mfrom,
                subject=subject)
        except SMTPRecipientsRefused:
            # Don't disclose email address on failure
            raise SMTPRecipientsRefused(
                'Recipient address rejected by server')

registerATCT(SignUpAdapter, PROJECTNAME)
