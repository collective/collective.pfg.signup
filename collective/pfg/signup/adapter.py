from persistent.list import PersistentList
from persistent.mapping import PersistentMapping
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
from BTrees.OOBTree import OOBTree
from encrypt import encode
from smtplib import SMTPRecipientsRefused
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from email import message_from_string
from email.Header import Header
import hashlib

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
    atapi.StringField('user_group_template',
                      default='council_role',
                      required=True,
                      widget=atapi.StringWidget(
                          label=_(u'label_user_group_template',
                              default=u'Add to User Group Template'),
                          description=_(u'help_add_to_user_group_template',
                              default=u'Enter user group template that users '
                                      u' added to, '
                                      u'eg ${council}_council_${role}.'),
                      ),
                      ),
    atapi.StringField('approval_group_template',
                      default='council_role_approver',
                      required=False,
                      widget=atapi.StringWidget(
                          label=_(u'label_approval_group_template',
                              default=u'Approval Group Template'),
                          description=_(u'help_approval_group_template',
                              default=u"Enter approval group template where "
                                      u"group that need to approve this user, "
                                      u"eg ${council}_${role}_approver."),
                      ),
                      ),
    atapi.LinesField('auto_roles',
                      widget=atapi.LinesWidget(
                          label=_(u'label_auto_roles',
                              default=u'Automatic Roles'),
                          description=_(u'help_auto_roles',
                              default=u"""These are the roles that will be
                                      automatically signed up as users, and
                                      require the user to create a password."""),
                      ),
                      ),
    atapi.LinesField('email_roles',
                      widget=atapi.LinesWidget(
                          label=_(u'label_email_roles',
                              default=u'Email Roles'),
                          description=_(u'help_email_roles',
                              default=u"""These are the roles that will confirm
                                  the user's email address by sending a password
                                  reset email before the user can login."""),
                      ),
                      ),
    atapi.LinesField('approval_roles',
                      widget=atapi.LinesWidget(
                          label=_(u'label_approval_roles',
                              default=u'Approval Roles'),
                          description=_(u'help_approval_roles',
                              default=u"""These are the roles that will go
                                  through the apporval process. An account will
                                  not be created until they are approved, and
                                  a password reset email will be generated when
                                  they are approved."""),
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

        self.site = getSite()
        self.SECRET_KEY = 'o41vivy!f3!$v6hl5geg0p1o2xkvmjn9&*b)(ejc^2t]p4hmsq'
        self.waiting_list = OOBTree()
        self.waiting_by_approver = OOBTree()
        self.registration = getToolByName(self.site, 'portal_registration')
        self.portal_groups = getToolByName(self.site, 'portal_groups')
        portal_url = getToolByName(self.site, 'portal_url')
        self.portal = portal_url.getPortalObject()
        self.excluded_field = ['form_submit', 'fieldset', 'last_referer',
                               'add_reference', 'form.submitted',
                               '_authenticator', 'password']
        #self.approval_mail = ViewPageTemplateFile('templates/approval_mail.pt')

    def generate_group(self, REQUEST, template):
        # TODO Create generate council role group function
        # e.g. self.approval_template will be like "${council}_${role}_approver"
        # replace ${council} with council form field,
        # replace ${role} with role form field from the Plone form gen
        print template
        return template

    def getRoles(self):
        """there are three kinds of roles, auto, email and approve"""
        roles = {}
        roles['auto'] = list(self.getAuto_roles())
        roles['email'] = list(self.getEmail_roles())
        roles['approval'] = list(self.getApproval_roles())
        for key in roles.keys():
            for i in range(len(roles[key])):
                roles[key][i] = roles[key][i].lower()
                roles[key][i] = roles[key][i].replace(' ', '')
        return roles

    def getRolesVocab(self):
        """Build the vocab for the roles field, this will be passed to DisplayList"""
        roles = []
        roles_list = self.getAuto_roles() + self.getEmail_roles() + self.getApproval_roles()
        for role in roles_list:
            key = role.lower()
            key = key.replace(' ', '')
            roles.append([key, role])
        return roles

    def onSuccess(self, fields, REQUEST=None):
        """Save form input."""
        # get username and password
        portal_registration = getToolByName(self, 'portal_registration')
        fullname = None
        username = None
        email = None
        password = None
        password_verify = None

        #approval_group = self.generate_group(REQUEST, self.approval_group_template)
        user_group = self.generate_group(REQUEST, self.user_group_template)

        data = {}
        for field in fields:
            fname = field.fgField.getName()
            val = REQUEST.form.get(fname, None)
            if fname == self.full_name_field:
                data['fullname'] = val
            elif fname == self.username_field:
                data['username'] = val
            elif fname == self.email_field:
                data['email'] = val
            elif fname == self.password_field:
                data['password'] = val
        data['password_verify'] = REQUEST.form.get('password_verify', None)

        role = REQUEST.form.get('role', None)

        if data['email'] is None or user_group == "":
            # SignUpAdapter did not setup properly
            return {FORM_ERROR_MARKER: _(u'Sign Up form is not setup properly.')}

        if not data['username']:
            data['username'] = data['email']

        # username validation
        if data['username'] == self.site.getId():
            return {FORM_ERROR_MARKER: _(u'You will need to signup again.'),
                'username': _(u"This username is reserved. "
                              u"Please choose a different name.")}

        if not portal_registration.isMemberIdAllowed(data['username']):
            return {FORM_ERROR_MARKER: _(u'You will need to signup again.'),
                'username': _(u"The login name you selected is already "
                              u"in use or is not valid. "
                              u"Please choose another.")}

        # TODO check waiting list for usernames

        roles = self.getRoles()

        if role in roles['auto']:
            result = self.autoRegister(REQUEST, data, user_group)
            # Just return the result, this should either be None on success or an error message
            return result

        email_from = self.portal.getProperty('email_from_address')
        if not portal_registration.isValidEmail(email_from):
            return {FORM_ERROR_MARKER: _(u'Portal email is not configured.')}

        if role in roles['email']:
            result = self.emailRegister(REQUEST, data, user_group)
            return result

        if role in roles['approval']:
            result = self.approvalRegister(REQUEST, data, user_group)
            return result

        # If we get here, then no role was selected
        return {FORM_ERROR_MARKER: _(u'Please select a role'),
                'role': _(u'Please select a role')}

    def approvalRegister(self, REQUEST, data, user_group):
        """User type requires approval,
        so store them on the approval list"""
        # make sure password fields are empty
        data['password'] = ''
        data['password_verify'] = ''
        self.waiting_list[data['username']] = data

        # need an email address for the approvers group
        administrators = self.portal_groups.getGroupById('Administrators')
        administrators_email = administrators.getProperty('email')
        if not administrators_email:
            administrators_email = self.portal.getProperty('email_from_address')
        try:
            self.sendApprovalEmail(data)
        except SMTPRecipientsRefused:
            # Don't disclose email address on failure
            raise SMTPRecipientsRefused('Recipient address rejected by server')

    def sendApprovalEmail(self, data):
        """Send an approval request email"""
        mail_host = getToolByName(self, 'MailHost')
        # TODO Create waiting list email template
        mail_body = u"Your account is waiting for approval. " \
                    u"Thank you. "
        mail_text = message_from_string(mail_body.encode('utf-8'))
        mail_text.set_charset('utf-8')
        mail_text['X-Custom'] = Header(u'Some Custom Parameter', 'utf-8')
        mail_host.send(mail_text, mto=data['email'],
                       mfrom=self.portal.getProperty('email_from_address'),
                       subject='Waiting for approval', immediate=True)
        return

                      
    def groupEmail(self, data):
        # TODO not sure if this is required
        if approval_group:
            #approval don't need password, as they should get reset email

            full_form_data = REQUEST.form
            #form_column = ['key_id']
            #form_data = [key_id]
            form_column = ["approve"]
            approve_string = "<input type='checkbox' name='{0}' value='1' />".\
                format(key_hash)
            form_data = [approve_string]

            for key, value in full_form_data.items():
                if key not in self.excluded_field:
                    form_column.append(key)
                    form_data.append(value)

            record = {'fullname': fullname, 'username': username,
                      'email': email, 'full_form_data': full_form_data,
                      'form_column': form_column, 'form_data': form_data,
                      'password': secret_password, 'key_hash': key_hash,
                      'user_group': user_group,
                      'approval_group': approval_group}
            self.waiting_list[key_hash] = key_id
            if approval_group not in self.waiting_by_approver:
                self.waiting_by_approver[approval_group] = {}

            self.waiting_by_approver[approval_group].update({key_id: record})
            #print "%s: %s" % (key_id, record)

            administrators = self.portal_groups.getGroupById('Administrators')
            administrators_email = administrators.getProperty('email')
            if not administrators_email:
                administrators_email = self.portal.getProperty(
                    'email_from_address')

            if approval_group:
                # TODO Create waiting list email template
                mail_body = u"Your account is waiting for approval. " \
                            u"Thank you. "
                send_email(mail_body,
                           self.portal.getProperty('email_from_address'),
                           email,
                           'Waiting for approval')
                return

            # find the email from group and send out the email
            if not approval_group in self.portal_groups.getGroupIds():
                #self.portal_groups.addGroup(approval_group)
                # Raise unknown 'new group' and no email, should not happen
                # TODO Create no existing group email template
                mail_body = u"There is a new group called %s waiting to" \
                            u" create. " % approval_group
                send_email(mail_body,
                           self.portal.getProperty('email_from_address'),
                           administrators_email,
                           'New Group Email')
                return

            # else
            group = self.portal_groups.getGroupById(approval_group)
            group_email = group.getProperty('email')
            if not group_email:
                # TODO Create no approval group email template
                mail_body = u"There is a user group %s does not have " \
                            u"email. Thank you." % approval_group
                send_email(mail_body,
                           self.portal.getProperty('email_from_address'),
                           administrators_email,
                           'Approval Email')
                return

            # TODO Create approval email template
            mail_body = u"There is a user %s waiting for approval. " \
                        u"Please approve at %s . " \
                        u"Thank you." % (email, REQUEST['ACTUAL_URL'] +
                        '/' + self.getRawId())
            send_email(mail_body,
                       self.portal.getProperty('email_from_address'),
                       group_email,
                       'Approval Email')

            return

    def emailRegister(self, REQUEST, data, user_group):
        """User type should be authenticated by email,
        so randomize their password and send a password reset"""
        portal_registration = getToolByName(self, 'portal_registration')
        data['password'] = portal_registration.generatePassword()
        result = self.create_member(REQUEST, data, True, user_group)
        return result

    def autoRegister(self, REQUEST, data, user_group):
        """User type can be auto registered, so pass them through"""
        verified = self.validate_password(data)
        if verified:
            return verified

        # This is a bad idea, if anon is filling in the form they will get a permission error
        #if not user_group in self.portal_groups.getGroupIds():
            #self.portal_groups.addGroup(user_group)

        # shouldn't store this in the pfg, as once the user is created, we shouldn't care
        result = self.create_member(REQUEST, data, False, user_group)
        return result

    def create_member(self, request, data, reset_password, user_group):
        portal_membership = getToolByName(self, 'portal_membership')
        portal_registration = getToolByName(self, 'portal_registration')
        portal_groups = getToolByName(self, 'portal_groups')
        username = data['username']

        self.create_group(user_group)

        try:
            member = portal_membership.getMemberById(username)

            if member is None:
                # need to also pass username in properties, otherwise the user isn't found
                # when setting the properties
                member = portal_registration.addMember(
                    username, data['password'], [],
                    properties={'username': username,
                                'fullname': data['fullname'],
                                'email': data['email']})

            #portal_groups.addPrincipalToGroup(member.getUserName(), user_group)
            if reset_password:
                # send out reset password email
                portal_registration.mailPassword(username, request)

        except(AttributeError, ValueError), err:
            logging.exception(err)
            return {FORM_ERROR_MARKER: err}

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
        # TODO: Check user has permissions and is in right group to approve the user
        request = self.REQUEST
        portal_registration = getToolByName(self, 'portal_registration')
        userid = request.form['userid']
        user = self.waiting_list.pop(userid)
        user['password'] = portal_registration.generatePassword()
        user_group = self.generate_group(request, self.user_group_template)
        self.create_member(request, user, True, user_group)
        request.RESPONSE.redirect(self.absolute_url())

    def reject_user(self):
        """Reject the user based on the request"""
        # TODO: Check user has permissions and is in right group to approve the user
        request = self.REQUEST
        userid = request.form['userid']
        user = self.waiting_list.pop(userid)
        request.RESPONSE.redirect(self.absolute_url())

def send_email(mail_body, mail_from, mail_to, subject):
    # TODO instead of hard code email, changed to template
    site = getSite()
    mail_host = getToolByName(site, 'MailHost')
    try:
        mail_text = message_from_string(mail_body.encode('utf-8'))
        mail_text.set_charset('utf-8')
        mail_text['X-Custom'] = Header(u'Some Custom Parameter',
                                       'utf-8')
        mail_host.send(
            mail_text, mto=mail_to,
            mfrom=mail_from,
            subject=subject, immediate=True)
    except SMTPRecipientsRefused:
        # Don't disclose email address on failure
        raise SMTPRecipientsRefused(
            'Recipient address rejected by server')


registerATCT(SignUpAdapter, PROJECTNAME)
