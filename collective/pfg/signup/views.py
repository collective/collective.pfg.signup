from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.Five import BrowserView
from zope.interface import implements
from zope.component import getMultiAdapter
from Products.CMFCore.utils import getToolByName

class UserApproverView(BrowserView):
    index = ViewPageTemplateFile("templates/user_approver_view.pt")

    def __init__(self, context, request):
        super(UserApproverView, self).__init__(context, request)

    def render(self):
        return self.index()

    def __call__(self):
        # aq_inner is needed in some cases like in the portlet renderers
        # where the context itself is a portlet renderer and it's not on the
        # acquisition chain leading to the portal root.
        # If you are unsure what this means always use context.aq_inner
        context = self.context.aq_inner
        portal_membership = getToolByName(context, 'portal_membership')



        #import ipdb; ipdb.set_trace()

        if portal_membership.isAnonymousUser():
            # Return target URL for the site anonymous visitors
            # TODO show nothing
            pass
        else:
            user_id = portal_membership.getAuthenticatedMember().getId()
            portal_groups = getToolByName(context, 'portal_groups')
            portal_groups.getGroupsByUserId(user_id)

            # get the user approval list based on groups

            # after user click the form button:
            # - send out email to user for reject?
            # - Create user and send out reset password email for approval.
            # clear the data from the OOBTree.

        return self.render()
