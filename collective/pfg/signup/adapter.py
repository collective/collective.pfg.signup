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
        self.mail_host = getToolByName(self.site, 'MailHost')
        portal_url = getToolByName(self.site, 'portal_url')
        self.portal = portal_url.getPortalObject()
        self.excluded_field = ['form_submit', 'fieldset', 'last_referer',
                               'add_reference', 'form.submitted',
                               '_authenticator', 'password']
        #self.approval_mail = ViewPageTemplateFile('templates/approval_mail.pt')

    def generate_group(self, REQUEST, template):
        print template
        return template

    def onSuccess(self, fields, REQUEST=None):
        """Save form input."""
        # get username and password
        fullname = None
        username = None
        email = None
        password = None

        # e.g. self.approval_template will be like "${council}_${role}_approver"
        approval_group = self.generate_group(REQUEST, self.approval_group_template)
        user_group = self.generate_group(REQUEST, self.user_group_template)

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

        #TODO should we verify the two passwords are the same again?

        if email is None or user_group == "":
            # SignUpAdapter did not setup properly
            return {FORM_ERROR_MARKER: 'Sign Up form is not setup properly.'}

        if not username:
            username = email

        if approval_group:
            #import ipdb; ipdb.set_trace()

            #should use hash the same way as plone if want to store password
            if password:
                secret_password = encode(self.SECRET_KEY, password)
            else:
                secret_password = password

            # just email is enough?
            key_id = encode(self.SECRET_KEY, email)
            key_hash = hashlib.sha224(key_id).hexdigest()

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

            # find the email from group and send out the email
            if not approval_group in self.portal_groups.getGroupIds():
                self.portal_groups.addGroup(approval_group)
                # TODO raise unkown 'new group' and no email
            else:
                group = self.portal_groups.getGroupById(approval_group)
                group_email = group.getProperty('email')
                if not group_email:
                    # TODO raise no email error
                    pass

                # send out email
                try:
                    # TODO using mail template
                    #mail_text = self.approval_mail(group_email=group_email,
                    #                               fullname=fullname,
                    #                               username=username,
                    #                               email=email,
                    #                               charset='utf-8',
                    #                               # email_charset,
                    #                               request=REQUEST)
                    # The ``immediate`` parameter causes an email to be sent immediately
                    # (if any error is raised) rather than sent at the transaction
                    # boundary or queued for later delivery.
                    mail_body = u"There is a user %s waiting for approval. " \
                                u"Please approve at %s. " \
                                u"Thank you." % (email, REQUEST['ACTUAL_URL'] +
                                '/' + self.getRawId())
                    mail_text = message_from_string(mail_body.encode('utf-8'))
                    mail_text.set_charset('utf-8')
                    mail_text['X-Custom'] = Header(u'Some Custom Parameter',
                                                   'utf-8')
                    self.mail_host.send(
                        mail_text, mto=group_email,
                        mfrom=self.portal.getProperty('email_from_address'),
                        subject='Approval Email', immediate=True)
                except SMTPRecipientsRefused:
                    # Don't disclose email address on failure
                    raise SMTPRecipientsRefused(
                        'Recipient address rejected by server')

        else:
            # auto registration

            # username validation

            if username == self.site.getId():
                return {FORM_ERROR_MARKER: 'You will need to signup again.',
                        'username': _(u"This username is reserved. "
                                      u"Please choose a different name.")}

            if not self.registration.isMemberIdAllowed(username):
                return {FORM_ERROR_MARKER: 'You will need to signup again.',
                        'username': _(u"The login name you selected is already "
                                      u"in use or is not valid. "
                                      u"Please choose another.")}

            verified = validate_password(password)

            if verified['fail_message']:
                return verified['fail_message']

            if not user_group in self.portal_groups.getGroupIds():
                self.portal_groups.addGroup(user_group)

            create_member(REQUEST, username, verified['password'], email,
                          verified['reset_password'], user_group)

        return


def create_member(request, username, password, email, reset_password,
                  user_group):
    site = getSite()
    portal_membership = getToolByName(site, 'portal_membership')
    portal_registration = getToolByName(site, 'portal_registration')
    portal_groups = getToolByName(site, 'portal_groups')

    try:
        member = portal_membership.getMemberById(username)

        if member is None:
            member = portal_registration.addMember(
                username, password,
                properties={'username': username,
                            'email': email})

        if not user_group in portal_groups.getGroupIds():
            portal_groups.addGroup(user_group)

        portal_groups.addPrincipalToGroup(member.getUserName(),
                                          user_group)

        if member.has_role('Member'):
            site.acl_users.portal_role_manager.removeRoleFromPrincipal(
                'Member', member.getUserName())

        if reset_password:
            # send out reset password email
            portal_registration.mailPassword(username, request)

    except(AttributeError, ValueError), err:
        logging.exception(err)
        IStatusMessage(request).addStatusMessage(err, type="error")
        return

def validate_password(password):
    site = getSite()
    registration = getToolByName(site, 'portal_registration')
    reset_password = False
    fail_message = None

    if password:
        failMessage = registration.testPasswordValidity(password)
        if failMessage is not None:
            fail_message = {FORM_ERROR_MARKER: 'You will need to signup again.',
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

    return {'password': password, 'reset_password': reset_password,
            'fail_message': fail_message}


registerATCT(SignUpAdapter, PROJECTNAME)
