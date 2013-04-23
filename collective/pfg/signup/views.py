from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.Five import BrowserView
from zope.interface import implements
from zope.component import getMultiAdapter
from Products.CMFCore.utils import getToolByName
from adapter import send_email
import hashlib


class UserApproverView(BrowserView):
    # TODO: Browser view need to have custom permission that only able to view
    # by Authenticated user. For now, it is public.
    index = ViewPageTemplateFile("templates/user_approver_view.pt")

    def __init__(self, context, request):
        super(UserApproverView, self).__init__(context, request)
        print "UserApproverView: init"
        self.results = []

    def result_data(self):
        # This needs to be a list of list, with the number of items in the list matching the number of columns
        return self.results

    def result_columns(self):
        return [{ "sTitle": "User Name" },
                { "sTitle": "Full Name" },
                { "sTitle": "Email" },
                { "sTitle": "Approve" },
                { "sTitle": "Reject" },
                ]
        return self.field_column

    def results(self):
        return self.results

    def __call__(self):
        # aq_inner is needed in some cases like in the portlet renderers
        # where the context itself is a portlet renderer and it's not on the
        # acquisition chain leading to the portal root.
        # If you are unsure what this means always use context.aq_inner
        context = self.context.aq_inner
        portal_membership = getToolByName(context, 'portal_membership')
        self.field_data = []
        self.field_column = []
        results = []

        if portal_membership.isAnonymousUser():
            # Return target URL for the site anonymous visitors
            return context.restrictedTraverse('login')()

        user_id = portal_membership.getAuthenticatedMember().getId()
        portal_groups = getToolByName(context, 'portal_groups')
        user_groups = portal_groups.getGroupsByUserId(user_id)

        for key, value in context.waiting_list.items():
            # TODO: need to restrict by user group
            link = self.context.absolute_url()
            approve_button = '<a href="' + link + '/approve_user?userid=' + key + '">Approve button</a>'
            reject_button = '<a href="' + link + '/reject_user?userid=' + key + '">Reject button</a>'
            results.append([value['username'],
                            value['fullname'],
                            value['email'],
                            approve_button,
                            reject_button])
        self.results = results
        return self.index()

class UserManagementView(BrowserView):
    # TODO The form in user_management_view need to have Plone csrf protection
    # not sure this is the right way for passing data in Plone
    # datatable plugin is the right tool for this case?
    # redirect in the view is right way to do it?
    # TODO: Browser view need to have custom permission that only able to view
    # by Authenticated user. For now, it is public.
    index = ViewPageTemplateFile("templates/user_management_view.pt")

    def __init__(self, context, request):
        super(UserManagementView, self).__init__(context, request)
        print "UserManagementView: init"

    def __call__(self):
        # aq_inner is needed in some cases like in the portlet renderers
        # where the context itself is a portlet renderer and it's not on the
        # acquisition chain leading to the portal root.
        # If you are unsure what this means always use context.aq_inner
        print "UserManagementView: call"
        context = self.context.aq_inner
        portal_membership = getToolByName(context, 'portal_membership')

        if portal_membership.isAnonymousUser():
            # Return target URL for the site anonymous visitors
            # TODO return error??
            return self.index()

        if 'results' not in self.request:
            # TODO return error??
            return self.index()

        if 'submit' not in self.request:
            # TODO return error??
            return self.index()

        results_string = self.request['results']
        is_approve = self.request['submit']

        results = []
        for result in results_string.split('&'):
            key_hash, _ = result.split("=")
            if key_hash not in context.waiting_list:
                continue

            key_id = context.waiting_list[key_hash]

            # need to verified?
            key_hash_original = hashlib.sha224(key_id).hexdigest()

            if key_hash_original != key_hash:
                # TODO raise error?
                continue

            if is_approve == 'approve' or is_approve == 'reject':
                del context.waiting_list[key_hash]
                results.append(key_id)

        user_id = portal_membership.getAuthenticatedMember().getId()
        portal_groups = getToolByName(context, 'portal_groups')
        user_groups = portal_groups.getGroupsByUserId(user_id)

        # get the user approval list based on groups
        for user_group in user_groups:
            user_group_name = user_group.getName()
            if user_group_name not in context.waiting_by_approver:
                continue
            all_results = waiting_by_approver[user_group_name]

            for key in results:

                # TODO remove the waiting_list
                if key not in all_results:
                    continue

                this_result = all_results[key]
                email = this_result['email']

                if is_approve == 'approve':
                    # create an account:
                    self.create_member(self.request, this_result, True, user_group)
                    del context.waiting_by_approver[user_group_name][key]
                elif is_approve == 'reject':
                    # TODO: create reject email template
                    mail_body = u"Sorry your user registration has been " \
                                u"rejected. Thank you."
                    send_email(mail_body,
                               self.portal.getProperty('email_from_address'),
                               email,
                               'Rejected Email')
                    del context.waiting_by_approver[user_group_name][key]

        return self.index()
