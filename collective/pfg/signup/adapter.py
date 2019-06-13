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
from Products.CMFDefault.exceptions import EmailAddressInvalid
from Products.CMFDefault.utils import checkEmailAddress
from Products.CMFPlone.interfaces import IMailSchema
from Products.PloneFormGen.config import FORM_ERROR_MARKER
from Products.PloneFormGen.content.actionAdapter import FormActionAdapter
from Products.PloneFormGen.content.actionAdapter import FormAdapterSchema
from Products.PloneFormGen.interfaces import IPloneFormGenActionAdapter
from Products.TALESField import TALESString

from collective.pfg.signup import _
from collective.pfg.signup.config import PROJECTNAME
from collective.pfg.signup.interfaces import ISignUpAdapter
from datetime import datetime
from email import message_from_string
from plone import api
from plone.registry.interfaces import IRegistry
from smtplib import SMTPRecipientsRefused
from smtplib import SMTPServerDisconnected
from zope.component import getUtility
from zope.interface import implements

import logging
import random
import re
import string
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
        default="",
        required=False,
        widget=atapi.StringWidget(
            label=_(
                u'label_user_group_template',
                default=u'Add to Groups'),
            description=_(
                u'help_add_to_user_group_template',
                default=u"""A TAL expression to calculate the group the user
                            should be added to. Data from the form can be used
                            eg string:${department}_${role}.
                            """),
        ),
    ),

    TALESString(
        'manage_group_template',
        required=False,
        default="",
        widget=atapi.TextAreaWidget(
            label=_(
                u'label_manage_group_template',
                default=u'Approval Group'),
            description=_(
                u'help_manage_group_template',
                default=u"""TAL to say what is the approver group to add to a given group name.
                            e.g. python:{'Administrators': ['Editors']}. Administrators
                            will be emailed to approve add to the Editors group.
                            If there is no match then no approval step is enforced."""),
        ),
    ),

    atapi.BooleanField(
        'email_domain_verification',
        default=False,
        required=False,
        widget=atapi.BooleanWidget(
            label=_(
                u'label_email_domain_verification',
                default=u'Email Domain Verification'),
            description=_(
                u'help_email_domain_verification',
                default=u"""The users email address must match groups email address (domain part only)"""),
        ),
    ),

    atapi.StringField(
        'error_message_email_domain_verification',
        required=False,
        widget=atapi.StringWidget(
            label=_(u'label_error_message_email_domain_verification',
                    default=u'Error Message When Email Domain Is Not Match'),
            description=_(
                u'help_email_domain_verification',
                default=u"""Enter error message that will display to the user 
                when domain of the email address is not match. It will use 
                default message if this field is blank."""),
        ),
    ),

))


def asList(x):
    """If not list, return x in a single-element list.

    .. note:: This will wrap falsy values like ``None`` or ``''`` in a list,
              making them truthy.
    """
    if isinstance(x, (list, tuple)):
        return x
    return [x]


# max 63 chars per label in domains, see RFC1035
PLONE5_EMAIL_RE = re.compile(r"^(\w&.%#$&'\*+-/=?^_`{}|~]+!)*[\w&.%#$&'\*+-/=?^_`{}|~]+@(([0-9a-z]([0-9a-z-]*[0-9a-z])?\.)+[a-z]{2,63}|([0-9]{1,3}\.){3}[0-9]{1,3})$", re.IGNORECASE)  # noqa


class SignUpAdapter(FormActionAdapter):

    """A form action adapter that saves signup form."""

    implements(IPloneFormGenActionAdapter, ISignUpAdapter)

    meta_type = 'SignUpAdapter'
    portal_type = 'SignUpAdapter'
    archetype_name = 'SignUp Adapter'
    default_view = 'user_approver_view'
    schema = SignUpAdapterSchema
    security = ClassSecurityInfo()
    manage_all = "*"
    disabled_email = "USERDISABLED"

    security.declarePrivate('onSuccess')

    def __init__(self, oid, **kwargs):
        """Initialize class."""
        FormActionAdapter.__init__(self, oid, **kwargs)
        self.waiting_list = OOBTree()
        
    @property
    def mail_settings(self):
        registry = getUtility(IRegistry)
        return registry.forInterface(IMailSchema, prefix='plone')

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
            return 'auto'
        return 'email'

    def isValidEmail(self, email):
        plone_version = api.env.plone_version()
        portal_registration = getToolByName(self, 'portal_registration')

        if plone_version < '5.0':
            # Checks for valid email.
            if PLONE5_EMAIL_RE.search(email) is None:
                return 0
            try:
                checkEmailAddress(email)
            except EmailAddressInvalid:
                return 0
            else:
                return 1
        return portal_registration.isValidEmail(email)

    def is_match_email_domain(self, email, user_group):
        portal_groups = getToolByName(self, 'portal_groups')

        group = portal_groups.getGroupById(user_group)
        if not group:
            return 0

        group_email = group.getProperty('email')
        if not group_email:
            return 0

        user_domain = email.strip()
        domain_index = user_domain.rfind('@')
        if domain_index >= 0:
            user_domain = user_domain[domain_index + 1:]

        group_domain = group_email.strip()
        domain_index = group_domain.rfind('@')
        if domain_index >= 0:
            group_domain = group_domain[domain_index + 1:]

        if user_domain == group_domain:
            return 1

        return 0

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
                FORM_ERROR_MARKER: _(u'Required email field not found')}
        if 'username' not in data:
            data['username'] = data['email']
        # TalesField needs variables to be available from the context, so
        # create a context and add them
        expression_context = getExprContext(self, self.aq_parent)
        for key in data.keys():
            expression_context.setGlobal(key, REQUEST.form.get(key, None))
        data_user_group = self.getUser_group_template(
            expression_context=expression_context, **data)
        data['user_group'] = data_user_group
        data['approval_group'] = self.update_data_approval_group(
            data_user_group)

        if data['email'] is None:
            # SignUpAdapter did not setup properly
            return {
                FORM_ERROR_MARKER: _(u'Sign Up form is not setup properly.')}

        if not data['username']:
            data['username'] = data['email']

        # force email and username to lowercase
        data['username'] = data['username'].lower()
        data['email'] = data['email'].lower()

        # Use plone 5 portal_registration.isValidEmail
        if not self.isValidEmail(data['email']):
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

        # Additional email check
        if self.getEmail_domain_verification():
            email_error_text = _(u'This email domain does not match.')
            email_error_message = _(
                u"""The email domain is not valid. Please contact the site administrator.""")
            custom_message = self.getError_message_email_domain_verification()
            if custom_message:
                email_error_message = custom_message
            if not self.is_match_email_domain(
                    data['email'], data['user_group']):
                return {FORM_ERROR_MARKER: email_error_message,
                        'email': email_error_text}

        check_id = self.check_userid(data)
        if check_id:
            return check_id

        policy = self.getPolicy(data)

        if policy == 'auto':
            result = self.autoRegister(REQUEST, data)
            # Just return the result, this should either be None on success or
            # an error message
            return result

        email_from = self.mail_settings.email_from_address

        if email_from:
            email_from = email_from.strip()  # strip the extra spaces
        if not email_from or not self.isValidEmail(email_from):
            #TODO: this check should move to the config form
            return {FORM_ERROR_MARKER: _(u'Portal email is not configured.')}

        if policy == 'email':
            result = self.emailRegister(REQUEST, data)
            return result

        if policy == 'approve':
            result = self.approvalRegister(data)
            return result

        # If we get here, then something went wrong
        return {FORM_ERROR_MARKER: _(u'The form is currently unavailable')}

    def update_data_approval_group(self, data_user_group):
        # Split the manage_group_template into two:
        # manage_group and approval_group
        # manage_group_template can't use data argument any more
        # because it will use when form data is not available
        expression_context = getExprContext(self, self.aq_parent)
        manage_group = self.getManage_group_template(
            expression_context=expression_context)
        is_manage_group_dict = isinstance(manage_group, dict)
        data_approval_group = []
        if manage_group and is_manage_group_dict:
            for manager, user_list in manage_group.iteritems():
                if '*' in user_list:
                    data_approval_group.append(manager)
                elif data_user_group in user_list:
                    data_approval_group.append(manager)
        if data_user_group and not data_approval_group:
            # make sure always got someone to approve
            # if data_user_group is not empty
            # in case the TAL expression wasn't valid
            data_approval_group.append('Administrators')
        return data_approval_group

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
        data_approval_group = data['approval_group']
        if not data_approval_group:
            self.send_approval_group_is_blank_email(data['username'])
            return

        approval_group_list = asList(data_approval_group)
        for approval_group_id in approval_group_list:
            approval_group = portal_groups.getGroupById(approval_group_id)

            if not approval_group:
                self.send_approval_group_not_exist_email(approval_group_id)
                continue

            approval_email = approval_group.getProperty('email')
            if approval_email:
                approval_title = approval_group.getProperty('title')
                self.send_approval_group_email(approval_email, approval_title)
            else:
                approval_group_members = approval_group.getGroupMembers()
                if approval_group_members:
                    self.send_approval_group_members_email(
                        approval_group_members)
                else:
                    self.send_approval_group_problem_email(approval_group_id)

    def emailRegister(self, request, data):
        """User type should be authenticated by email.

        So randomize their password and send a password reset.
        """
        portal_registration = getToolByName(self, 'portal_registration')
        data['password'] = portal_registration.generatePassword()
        result = self.create_member(request, data, True)
        return result

    def autoRegister(self, request, data):
        """User type can be auto registered, so pass them through."""
        verified = self.validate_password(data)
        if verified:
            return verified

        self.create_group(data['user_group'])

        # shouldn't store this in the pfg, as once the user is created, we
        # shouldn't care
        result = self.create_member(request, data, False)
        return result

    def prepare_member_properties(self):
        """Adjust site for custom member properties."""

        # Need to use ancient Z2 property sheet API here...
        portal_memberdata = getToolByName(self, "portal_memberdata")

        # When new member is created, its MemberData
        # is populated with the values from portal_memberdata property sheet,
        # so value="" will be the default value for users' home_folder_uid
        # member property
        if not portal_memberdata.hasProperty("approved_by"):
            portal_memberdata.manage_addProperty(
                id="approved_by", value="", type="string")
        # PAS does not understand datetime or DateTime,
        # so we have to use string instead
        if not portal_memberdata.hasProperty("approved_date"):
            portal_memberdata.manage_addProperty(
                id="approved_date", value="", type="string")

        if not portal_memberdata.hasProperty("last_updated_by"):
            portal_memberdata.manage_addProperty(
                id="last_updated_by", value="", type="string")
        # PAS does not understand datetime or DateTime,
        # so we have to use string instead
        if not portal_memberdata.hasProperty("last_updated_date"):
            portal_memberdata.manage_addProperty(
                id="last_updated_date", value="", type="string")

    def create_member(self, request, data, reset_password=False):
        """Create member."""
        self.prepare_member_properties()
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
                current_user_id = ""
                if not portal_membership.isAnonymousUser():
                    current_user = portal_membership.getAuthenticatedMember()
                    current_user_id = current_user.id
                current_time = datetime.now().strftime("%d %B %Y %I:%M %p")
                member = portal_registration.addMember(
                    username, data['password'], [],
                    properties={'username': username,
                                'fullname': data['fullname'],
                                'email': data['email'],
                                'approved_by': current_user_id,
                                'approved_date': current_time})
            except (AttributeError, ValueError) as err:
                logging.exception(err)
                return {FORM_ERROR_MARKER: err}

            if user_group:
                portal_groups.addPrincipalToGroup(member.getUserName(), user_group)
            if reset_password:
                # send out reset password email
                portal_registration.mailPassword(username, request)

        else:
            return {FORM_ERROR_MARKER: _("This user already exists.")}

    def update_member(self, request, user_id, user_fullname, current_group,
                      new_group):
        """Update member with full name and / or group."""
        # If we use custom member properties they must be initialized
        # before regtool is called
        self.prepare_member_properties()
        portal_membership = getToolByName(self, 'portal_membership')
        # portal_registration = getToolByName(self, 'portal_registration')
        portal_groups = getToolByName(self, 'portal_groups')

        if not user_id:
            self.plone_utils.addPortalMessage(
                _(u'User ID is not valid.'))
            return
        user = portal_membership.getMemberById(user_id)
        if not user:
            self.plone_utils.addPortalMessage(
                _(u'This user does not exists.'))
            return

        if not new_group:
            self.plone_utils.addPortalMessage(
                _(u'User group is not valid.'))
            return
        new_user_group = portal_groups.getGroupById(new_group)
        if not new_user_group:
            self.plone_utils.addPortalMessage(
                _(u'This user group does not exists.'))
            return

        try:
            current_user_id = ""
            if not portal_membership.isAnonymousUser():
                current_user = portal_membership.getAuthenticatedMember()
                current_user_id = current_user.id
            current_time = datetime.now().strftime("%d %B %Y %I:%M %p")
            # update user_last_updated_date and user_last_updated_by
            user.setMemberProperties({
                'fullname': user_fullname,
                'last_updated_by': current_user_id,
                'last_updated_date': current_time})
        except (AttributeError, ValueError) as err:
            logging.exception(err)
            return {FORM_ERROR_MARKER: err}

        if current_group != new_group:
            try:
                portal_groups.removePrincipalFromGroup(user_id, current_group)
            except KeyError as err:
                error_string = _(u'Can not remove group: %s.') % err
                logging.exception(error_string)
                self.plone_utils.addPortalMessage(error_string)
                return

            try:
                portal_groups.addPrincipalToGroup(user_id, new_group)
            except KeyError as err:
                error_string = _(u'Can not add group: %s.') % err
                logging.exception(error_string)
                self.plone_utils.addPortalMessage(error_string)
                return

        return

    def user_activate(self, user_id, request):
        """Activate user with user_id.

        Remove USERDISABLED<randomkey>_user@email.com from email field.
        """
        if not user_id:
            self.plone_utils.addPortalMessage(
                _(u'This user ID is not valid.'))
            return

        self.prepare_member_properties()
        portal_membership = getToolByName(self, 'portal_membership')
        portal_registration = getToolByName(self, 'portal_registration')
        user = portal_membership.getMemberById(user_id)
        if not user:
            self.plone_utils.addPortalMessage(
                _(u'This user does not exists.'))
            return

        try:
            current_user_id = ""
            if not portal_membership.isAnonymousUser():
                current_user = portal_membership.getAuthenticatedMember()
                current_user_id = current_user.id
            current_time = datetime.now().strftime("%d %B %Y %I:%M %p")
            current_email = user.getProperty('email', '')

            if not current_email:
                # no email
                return
            if not current_email.startswith(self.disabled_email):
                # already active
                return
            split = current_email.find("_")
            if split < len(self.disabled_email):
                # assume not valid email, should not be the case
                return

            new_email = current_email[split + 1:]
            # update user_last_updated_date and user_last_updated_by
            user.setMemberProperties({
                'email': new_email,
                'last_updated_by': current_user_id,
                'last_updated_date': current_time})
            portal_registration.mailPassword(user.id, request)
            self.plone_utils.addPortalMessage(
                _(u"""This user is activated and
                reset password email is sent to the user."""))
        except (AttributeError, ValueError) as err:
            logging.exception(err)
            return {FORM_ERROR_MARKER: err}

        return

    def user_deactivate(self, user_id):
        """Deactivate user with user_id.

        Add USERDISABLED<randomkey>_user@email.com to email field.
        """
        if not user_id:
            self.plone_utils.addPortalMessage(
                _(u'This user ID is not valid.'))
            return

        self.prepare_member_properties()
        portal_membership = getToolByName(self, 'portal_membership')
        user = portal_membership.getMemberById(user_id)
        if not user:
            self.plone_utils.addPortalMessage(
                _(u'This user does not exists.'))
            return

        try:
            current_user_id = ""
            if not portal_membership.isAnonymousUser():
                current_user = portal_membership.getAuthenticatedMember()
                current_user_id = current_user.id
            current_time = datetime.now().strftime("%d %B %Y %I:%M %p")
            current_email = user.getProperty('email', '')

            if not current_email:
                # no email
                return
            if current_email.startswith(self.disabled_email):
                # already deactivate
                return

            new_email = self.disabled_email + self.id_generator() + "_" + \
                current_email
            # update user_last_updated_date and user_last_updated_by
            user.setMemberProperties({
                'email': new_email,
                'last_updated_by': current_user_id,
                'last_updated_date': current_time})
            passwd = self.id_generator(size=32)
            user.setSecurityProfile(password=passwd)
            self.plone_utils.addPortalMessage(
                _(u'This user is deactivated.'))
        except (AttributeError, ValueError) as err:
            logging.exception(err)
            return {FORM_ERROR_MARKER: err}

        return

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

    def update_approval_group(self):
        """Fix wrong approval group based on the request."""
        request = self.REQUEST
        userid = request.form['userid']
        sm = getSecurityManager()
        portal = getUtility(ISiteRoot)
        if userid:
            user = self.waiting_list.get(userid)
            if user is None:
                self.plone_utils.addPortalMessage(
                    _(u'This user has already been dealt with.'))
            elif sm.checkPermission(ManagePortal, portal):
                # Fix the wrong approval group
                current_approval_group = user['approval_group']
                data_user_group = user['user_group']
                new_approval_group = self.update_data_approval_group(
                    data_user_group)
                user['approval_group'] = new_approval_group
                # commit a subtransaction, to save the changes
                transaction.get().commit()
                messsage_string = _(u'"%(current)s" updated to "%(new)s"') % {
                    'current': current_approval_group,
                    'new': new_approval_group}
                self.plone_utils.addPortalMessage(messsage_string)
            else:
                self.plone_utils.addPortalMessage(
                    _(u'You do not have permission to manage this user.'))
        request.RESPONSE.redirect(self.absolute_url())

    def check_approval_group(self):
        """Check current approval group based on the request."""
        request = self.REQUEST
        userid = request.form['userid']
        sm = getSecurityManager()
        portal = getUtility(ISiteRoot)
        user = self.waiting_list.get(userid)
        if userid:
            user = self.waiting_list.get(userid)
            if user is None:
                self.plone_utils.addPortalMessage(
                    _(u'This user has already been dealt with.'))
            elif sm.checkPermission(ManagePortal, portal):
                # show the current approval group
                current_username = user['username']
                current_approval_group = user['approval_group']
                messsage_string = _(
                    u'Approval group for "%(username)s" is "%(approval)s"') % {
                    'username': current_username,
                    'approval': current_approval_group}
                self.plone_utils.addPortalMessage(messsage_string)
            else:
                self.plone_utils.addPortalMessage(
                    _(u'You do not have permission to manage this user.'))
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

        if not group:
            self.plone_utils.addPortalMessage(
                _(u'You do not have permission to do this.'))
            self.REQUEST.RESPONSE.redirect(self.absolute_url())
            return True

        group_list = asList(group)
        for current_group in group_list:
            if current_group in current_user_groups:
                return False

        self.plone_utils.addPortalMessage(
            _(u'You do not have permission to do this.'))
        self.REQUEST.RESPONSE.redirect(self.absolute_url())
        return True

    def get_portal_email_properties(self):
        """Return the portal title for use in emails."""
        portal_url = getToolByName(self, 'portal_url')
        portal = portal_url.getPortalObject()
        return (
            portal.Title(), self.mail_settings.email_from_address,
            self.mail_settings.email_from_name)

    def send_approval_group_is_blank_email(self, username):
        """This username does not have approval group."""
        portal_title, portal_email, portal_email_name = \
            self.get_portal_email_properties()
        # portal_url = getToolByName(self, 'portal_url')()
        portal_groups = getToolByName(self, 'portal_groups')
        administrators = portal_groups.getGroupById('Administrators')
        administrators_email = administrators.getProperty('email')
        if not administrators_email:
            administrators_email = getUtility(ISiteRoot).getProperty(
                'email_from_address', '')
        if administrators_email:
            # strip the extra spaces
            administrators_email = administrators_email.strip()
        portal_groups = getToolByName(self, 'portal_groups')
        if not username:
            username = ""
        messageText = [
            self.get_approval_group_email_text(username), ]
        messageText.append('')
        messageText.append(
            '---------------------------------------------------')
        messageText.append('')
        messageText.append(
            u"""This email has been sent to this address because the username
            "%s" currently doesn\'t have approval group and needs to be
            created.""" %
            username)
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

    def send_approval_group_not_exist_email(self, approval_group_id):
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
        if administrators_email:
            # strip the extra spaces
            administrators_email = administrators_email.strip()
        portal_groups = getToolByName(self, 'portal_groups')
        if not approval_group_id:
            approval_group_id = ""
        messageText = [
            self.get_approval_group_email_text(approval_group_id), ]
        messageText.append('')
        messageText.append(
            '---------------------------------------------------')
        messageText.append('')
        messageText.append(
            u"""This email has been sent to this address because the group "%s"
            currently doesn\'t exist and needs to be created.""" %
            approval_group_id)
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

    def send_approval_group_problem_email(self, approval_group_id):
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
        if administrators_email:
            # strip the extra spaces
            administrators_email = administrators_email.strip()
        portal_groups = getToolByName(self, 'portal_groups')
        if not approval_group_id:
            approval_group_id = ""
        messageText = [
            self.get_approval_group_email_text(approval_group_id), ]
        messageText.append('')
        messageText.append(
            '---------------------------------------------------')
        messageText.append('')
        messageText.append(
            u"""This email has been sent to this address because the group "%s"
                currently doesn\'t have any members with contact information or
                the group itself doesn\'t have contact information.""" %
            approval_group_id)
        messageText.append('')
        messageText.append(
            u"""You can add members to the group using this link: %s""" %
            portal_url + '/@@usergroup-groupmembership?groupname=' +
            approval_group_id)
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

    def send_approval_group_email(self, approval_email, approval_title):
        """Send an email to approval group.

        When there is a user waiting for approval.
        """
        portal_title, portal_email, portal_email_name = \
            self.get_portal_email_properties()
        # already checked that the group exists and has an email address
        if not approval_title:
            approval_title = approval_email
        messageText = self.get_approval_group_email_text(approval_title)
        subject = portal_title + ' user Waiting for approval'
        try:
            self.send_email(messageText, mto=approval_email,
                            mfrom=portal_email, subject=subject)
        except SMTPServerDisconnected:
            pass
        return

    def send_approval_group_members_email(self, approval_group_members):
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
            try:
                self.send_email(messageText, mto=email, mfrom=portal_email,
                                subject=subject)
            except SMTPServerDisconnected:
                pass
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
        try:
            self.send_email(messageText, mto=data['email'], mfrom=portal_email,
                            subject=subject)
        except SMTPServerDisconnected:
            pass
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
        try:
            self.send_email(messageText, mto=data['email'], mfrom=portal_email,
                            subject=subject)
        except SMTPServerDisconnected:
            pass
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

    def get_management_dict(self):
        """Return dictionary where 'key' group manage 'value' groups.

        '*' meaning all users. Leave empty to allow creation of user accounts
        without any management. eg python:{'Administrators': ['*']}. This TALES
        expression is allowing all the users managed by 'Administrators' group.
        """
        expression_context = getExprContext(self, self.aq_parent)
        manage_group = self.getManage_group_template(
            expression_context=expression_context)
        # make sure manage_group is dictionary
        if not isinstance(manage_group, dict):
            return {}
        return manage_group

    def get_manager_groups(self, manager=""):
        """Return common manager groups.

        If manager parameter is not provided, Current login user will used.
        """
        portal_membership = getToolByName(self, 'portal_membership')
        # portal_groups = getToolByName(self, 'portal_groups')
        acl = getToolByName(self, 'acl_users')

        if manager:
            current_user = acl.getUserById(manager)
        elif portal_membership.isAnonymousUser():
            return []
        else:
            current_user = portal_membership.getAuthenticatedMember()

        user_groups = current_user.getGroups()
        user_management_list = self.get_management_dict()
        common_groups = set(user_management_list.keys()) & set(user_groups)
        return common_groups

    def get_manage_by_groups(self, manager=""):
        """Return a list of group ids that manage by manager.

        '*' meaning all users.
        If manager parameter is not provided, current login user will used.
        """
        user_management_list = self.get_management_dict()
        common_groups = self.get_manager_groups(manager)
        manage_by_group = []

        for common_group in common_groups:
            if common_group not in user_management_list:
                continue
            manage_user_group = user_management_list[common_group]
            if self.manage_all in manage_user_group:
                manage_by_group = [self.manage_all]
                break
            manage_by_group += manage_user_group

        return manage_by_group

    def get_manage_all(self):
        """Return manage all constant string."""
        return self.manage_all

    def get_status(self, user):
        """Return user status."""
        if not user:
            return ""

        current_email = user.getProperty('email', '')
        status = _("Active")
        if current_email.startswith(self.disabled_email):
            status = _("Inactive")
        return status

    def is_active(self, user):
        """Return whether the user is active."""
        status = self.get_status(user)
        if status == "Active":
            return True

        return False

    def get_user_name(self, user_id):
        """Return user name."""
        if not user_id:
            return ""

        portal_membership = getToolByName(self, 'portal_membership')
        user = portal_membership.getMemberById(user_id)
        if not user:
            return ""

        user_fullname = user.getProperty('fullname', '')
        if user_fullname:
            return user_fullname

        return user_id

    def get_groups_title(self, user_groups):
        """Return groups id and title as dictionary."""
        acl_users = getToolByName(self, 'acl_users')
        portal_groups = getToolByName(self, 'portal_groups')

        # if user_groups contains 'manage_all', show all the groups
        if self.manage_all in user_groups:
            user_groups = acl_users.source_groups.getGroupIds()

        group_names = []
        for user_group_id in user_groups:
            # {"group_id": group_name, "group_title": group_name}
            user_group = portal_groups.getGroupById(user_group_id)
            # group may not yet exist
            group_name = ""
            if user_group is not None:
                group_name = user_group.getProperty("title", "")
                if not group_name:
                    # don't have title, use id
                    group_name = user_group_id
            if group_name:
                group_names.append(
                    {"group_id": user_group_id, "group_title": group_name})
        return group_names

    def id_generator(self, size=8,
                     chars=string.ascii_uppercase + string.digits):
        """Random id generator."""
        return ''.join(
            random.SystemRandom().choice(chars) for _ in range(size))


registerATCT(SignUpAdapter, PROJECTNAME)
