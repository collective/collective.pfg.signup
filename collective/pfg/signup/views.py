from AccessControl import getSecurityManager
from AccessControl import Unauthorized

from zope.component import getUtility

from Products.CMFCore.interfaces import ISiteRoot
from Products.CMFCore.utils import getToolByName
from Products.CMFCore.permissions import ManagePortal
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.Five import BrowserView

class UserApproverView(BrowserView):
    # TODO: Browser view need to have custom permission.
    index = ViewPageTemplateFile("templates/user_approver_view.pt")

    def result_data(self):
        # This needs to be a list of list, with the number of items in the list matching the number of columns
        return self.results

    def result_columns(self):
        return [{ "sTitle": "User Name" },
                { "sTitle": "Full Name" },
                { "sTitle": "Group" },
                { "sTitle": "Email" },
                { "sTitle": "Approve" },
                { "sTitle": "Reject" },
                ]

    def results(self):
        return self.results

    def __call__(self):
        # aq_inner is needed in some cases like in the portlet renderers
        # where the context itself is a portlet renderer and it's not on the
        # acquisition chain leading to the portal root.
        # If you are unsure what this means always use context.aq_inner
        context = self.context.aq_inner
        portal_membership = getToolByName(context, 'portal_membership')
        portal_groups = getToolByName(context, 'portal_groups')
        results = []

        if portal_membership.isAnonymousUser():
            raise Unauthorized('You need to login to access this page.')

        current_user = portal_membership.getAuthenticatedMember()
        user_groups = current_user.getGroups()
        sm = getSecurityManager()
        portal = getUtility(ISiteRoot)
        display_all = False
        if sm.checkPermission(ManagePortal, portal):
            display_all = True

        for key, value in context.waiting_list.items():
            if not display_all and value['approval_group'] not in user_groups:
                continue
            user_group = portal_groups.getGroupById(value['user_group'])
            if user_group is not None:
                group_name = user_group.getProperty('title')
                if not group_name:
                    group_name = value['user_group']
            else:
                # group may not yet exist
                group_name = value['user_group']
            link = self.context.absolute_url()
            approve_button = '<a class="btn" href="' + link + '/approve_user?userid=' + key + '">Approve</a>'
            reject_button = '<a class="btn" href="' + link + '/reject_user?userid=' + key + '">Reject</a>'
            results.append([value['username'],
                            value['fullname'],
                            group_name,
                            value['email'],
                            approve_button,
                            reject_button])
        self.results = results
        return self.index()

class UsersSignedUpView(BrowserView):
    index = ViewPageTemplateFile("templates/users_signedup_view.pt")

    def result_data(self):
        # This needs to be a list of list, with the number of items in the list matching the number of columns
        return self.results

    def result_columns(self):
        return [{ "sTitle": "User Name" },
                { "sTitle": "Full Name" },
                { "sTitle": "Group" },
                { "sTitle": "Email" },
                { "sTitle": "Approve" },
                { "sTitle": "Reject" },
                ]

    def __call__(self):
        self.results = []
        return self.index()
