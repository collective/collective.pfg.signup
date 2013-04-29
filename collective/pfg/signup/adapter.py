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
from Products.TALESField import TALESString
from collective.pfg.signup.interfaces import ISignUpAdapter
from collective.pfg.signup.config import PROJECTNAME
from collective.pfg.signup import _
from Products.statusmessages.interfaces import IStatusMessage
from Products.CMFCore.utils import getToolByName
from Products.CMFCore.Expression import getExprContext
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
    TALESString('user_group_template',
        default='string:${council}_council_${role}',
        required=True,
        widget=atapi.StringWidget(
            label=_(u'label_user_group_template',
            default=u'Add to User Group Template'),
            description=_(u'help_add_to_user_group_template',
            default=u"""Enter user group template that users'
                        added to,
                        eg ${council}_council_${role}."""),
            ),
        ),

    TALESString('approval_group_template',
        default='string:${council}_${role}_approver',
        required=False,
        widget=atapi.StringWidget(
            label=_(u'label_approval_group_template',
            default=u'Approval Group Template'),
            description=_(u'help_approval_group_template',
            default=u"""Enter approval group template where
                        group that need to approve this user,
                        eg ${council}_${role}_approver."""),
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
            else:
                data[field_name] = val
        print data
        # TalesField needs variables to be available from the context, so create a context and add them
        expression_context = getExprContext(self, self.aq_parent)
        for key in data.keys():
            expression_context.setGlobal(key, REQUEST.form.get(key, None))
        data['user_group'] = self.getUser_group_template(expression_context=expression_context, **data)
        data['approval_group'] = self.getApproval_group_template(expression_context=expression_context, **data)
        print data

        if data['email'] is None or data['user_group'] == "":
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

        policy = self.getPolicy(data)

        if policy == 'auto':
            result = self.autoRegister(REQUEST, data)
            # Just return the result, this should either be None on success or an error message
            return result

        email_from = self.portal.getProperty('email_from_address')
        if not portal_registration.isValidEmail(email_from):
            return {FORM_ERROR_MARKER: _(u'Portal email is not configured.')}

        if policy == 'email':
            result = self.emailRegister(REQUEST, data)
            return result

        if policy == 'approve':
            result = self.approvalRegister(REQUEST, data)
            return result

        # If we get here, then something went wrong
        return {FORM_ERROR_MARKER: _(u'The form is currently unavailable')}

    def approvalRegister(self, REQUEST, data):
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

        # This is a bad idea, if anon is filling in the form they will get a permission error
        #if not user_group in self.portal_groups.getGroupIds():
            #self.portal_groups.addGroup(user_group)

        # shouldn't store this in the pfg, as once the user is created, we shouldn't care
        result = self.create_member(REQUEST, data, False)
        return result

    def create_member(self, request, data, reset_password):
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
        self.create_member(request, user, True)
        self.waiting_list.remove(userid)
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
        self.waiting_list.remove(userid)
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
