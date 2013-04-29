from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.Five import BrowserView

class UserApproverView(BrowserView):
    # TODO: Browser view need to have custom permission that only able to view
    # by Authenticated user. For now, it is public.
    index = ViewPageTemplateFile("templates/user_approver_view.pt")

    def __init__(self, context, request):
        super(UserApproverView, self).__init__(context, request)
        self.results = []

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
        results = []

        if portal_membership.isAnonymousUser():
            # Return target URL for the site anonymous visitors
            return context.restrictedTraverse('login')()

        current_user = portal_membership.getAuthenticatedMember()
        user_groups = current_user.getGroups()

        for key, value in context.waiting_list.items():
            if value['approval_group'] not in user_groups:
                continue
            link = self.context.absolute_url()
            approve_button = '<a href="' + link + '/approve_user?userid=' + key + '">Approve button</a>'
            reject_button = '<a href="' + link + '/reject_user?userid=' + key + '">Reject button</a>'
            results.append([value['username'],
                            value['fullname'],
                            value['user_group'],
                            value['email'],
                            approve_button,
                            reject_button])
        self.results = results
        return self.index()
