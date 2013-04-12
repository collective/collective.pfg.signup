from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.Five import BrowserView
from zope.interface import implements
from zope.component import getMultiAdapter
from Products.CMFCore.utils import getToolByName

class UserApproverView(BrowserView):
    index = ViewPageTemplateFile("templates/user_approver_view.pt")

    def __init__(self, context, request):
        super(UserApproverView, self).__init__(context, request)
        print "UserApproverView: init"
        self.results = {}

    def result_data(self):
        results = {
            "aaData": [
                [
                    "Trident",
                    "Internet Explorer 4.0",
                    "Win 95+",
                    "4",
                    "X",
                    "<input type='checkbox' name='aCheckBox' value='aValue1' />"
                ],
                [
                    "Trident",
                    "Internet Explorer 5.0",
                    "Win 95+",
                    "5",
                    "C",
                    "<input type='checkbox' name='aCheckBox' value='aValue2' />"
                ]
            ]}
        #return results['aaData']
        print self.field_data
        return self.field_data

    def result_columns(self):
        results = {"aoColumns": [
            { "sTitle": "Engine" },
            { "sTitle": "Browser" },
            { "sTitle": "Platform" },
            { "sTitle": "Version", "sClass": "center" },
            { "sTitle": "Grade", "sClass": "center" },
            { "sTitle": "CheckBox", "sClass": "center" }
        ],
                   "aoColumn": [
            "Engine",
            "Browser",
            "Platform",
            "Version",
            "Grade",
            "CheckBox"
        ]}
        #return results['aoColumns']
        print self.field_column
        return self.field_column

    def results(self):
        return self.results

    def __call__(self):
        # aq_inner is needed in some cases like in the portlet renderers
        # where the context itself is a portlet renderer and it's not on the
        # acquisition chain leading to the portal root.
        # If you are unsure what this means always use context.aq_inner
        print "UserApproverView: call"
        context = self.context.aq_inner
        portal_membership = getToolByName(context, 'portal_membership')

        if portal_membership.isAnonymousUser():
            # Return target URL for the site anonymous visitors
            # TODO show nothing
            pass
        else:
            user_id = portal_membership.getAuthenticatedMember().getId()
            portal_groups = getToolByName(context, 'portal_groups')
            user_groups = portal_groups.getGroupsByUserId(user_id)

            #import ipdb; ipdb.set_trace()

            waiting_by_approver = context.waiting_by_approver

            self.results = {}
            self.field_data = []
            self.field_column = []

            # get the user approval list based on groups
            for user_group in user_groups:
                user_group_name = user_group.getName()
                if user_group_name not in waiting_by_approver:
                    continue

                self.results.update(waiting_by_approver[user_group_name])

            is_first_item = True
            for _, fields in self.results.items():

                form_data = fields['form_data']
                form_column = fields['form_column']

                if is_first_item:
                    for column in form_column:
                        self.field_column.append({ "sTitle": column })
                    is_first_item = False

                self.field_data.append(form_data)










            # after user click the form button:
            # - send out email to user for reject?
            # - Create user and send out reset password email for approval.
            # clear the data from the OOBTree.

        return self.index()
