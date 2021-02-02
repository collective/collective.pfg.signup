"""Browser view on sign up adapter."""
import logging

from AccessControl import getSecurityManager
from AccessControl import Unauthorized
from Acquisition import aq_inner

from Products.CMFCore.interfaces import ISiteRoot
from Products.CMFCore.permissions import ManagePortal
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone import PloneMessageFactory as _
from Products.CMFPlone.utils import normalizeString
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.Five import BrowserView
from Products.PluggableAuthService.interfaces.plugins import IRolesPlugin

from collective.pfg.signup.adapter import asList
from itertools import chain
from zope.component import getMultiAdapter
from zope.component import getUtility
from zope.publisher.interfaces.browser import IBrowserView
from ZTUtils import make_query


try:
    # Plone 5.0.8 and above
    # The users/groups control panel was moved to Products.CMFPlone in
    # plone.app.controlpanel.usergroups version 3.
    from Products.CMFPlone.controlpanel.browser.usergroups import \
        UsersGroupsControlPanelView
except ImportError:
    # Before Plone 5.0.8
    from plone.app.controlpanel.usergroups import UsersGroupsControlPanelView

UNAUTHORISED_ERROR = "You don't have permission to manage this user"


logger = logging.getLogger('collective.pfg.signup')


def to_str(unicode_or_str):
    """Convert to string from unicode or str"""
    if isinstance(unicode_or_str, unicode):
        value = unicode_or_str.encode('utf-8')
    else:
        value = unicode_or_str
    return value  # Instance of str


class UserApproverView(BrowserView):

    """User approver browser view."""

    # TODO(Ivan): Browser view need to have custom permission.
    index = ViewPageTemplateFile("templates/user_approver_view.pt")

    def result_data(self):
        """Return user data in list."""
        # This needs to be a list of list, with the number of items in the list
        # matching the number of columns
        return self.results

    def result_columns(self):
        """Return user data columns."""
        return [{"sTitle": "User Name"},
                {"sTitle": "Full Name"},
                {"sTitle": "Group"},
                {"sTitle": "Email"},
                {"sTitle": "Approve"},
                {"sTitle": "Reject"},
                ]

    def results(self):
        """Return user data in list."""
        return self.results

    def __call__(self):
        """Browser view call."""
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
            approval_group = value['approval_group']
            belong_to_approval_group = False
            if approval_group:
                # before fix, the approval_group_list could be '' or
                # 'dlg_admin'. Now it should be ['dlg_admin']
                approval_group_list = asList(approval_group)
                for group_name in approval_group_list:
                    if group_name in user_groups:
                        belong_to_approval_group = True
                        break
            if not display_all and not belong_to_approval_group:
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
            approve_button = '<a class="btn" href="' + link + \
                '/approve_user?userid=' + key + '">Approve</a>'
            reject_button = '<a class="btn" href="' + link + \
                '/reject_user?userid=' + key + '">Reject</a>'
            # make sure results only contain str as JS does not
            # understand python unicode u''.
            results.append([to_str(value['username']),
                            to_str(value['fullname']),
                            to_str(group_name),
                            to_str(value['email']),
                            to_str(approve_button),
                            to_str(reject_button)])
        self.results = results
        return self.index()


class UserSearchView(BrowserView):

    """User search browser view."""

    def __call__(self):
        """Call this browser view."""
        # aq_inner is needed in some cases like in the portlet renderers
        # where the context itself is a portlet renderer and it's not on the
        # acquisition chain leading to the portal root.
        # If you are unsure what this means always use context.aq_inner
        context = self.context.aq_inner
        portal_membership = getToolByName(context, 'portal_membership')
        portal = getUtility(ISiteRoot)
        path = "/".join(portal.getPhysicalPath())
        self.usersview = self.context.unrestrictedTraverse(path+"/usergroup-userprefs")

        if portal_membership.isAnonymousUser():
            raise Unauthorized('You need to login to access this page.')

        form = self.request.form
        # submitted = form.get('form.submitted', False)
        search = form.get('form.button.Search', None) is not None
        # findAll = form.get('form.button.FindAll', None) is not None
        # self.searchString = not findAll and form.get('searchstring', '')
        # or ''
        self.searchString = form.get('searchstring', '')
        self.searchResults = []
        self.newSearch = False

        if search:  # search or findAll
            self.newSearch = True

        # Custom code: allow user to filter user groups.
        # manager_groups = context.get_manager_groups()
        manage_by_group = context.get_manage_by_groups()
        # all_user_groups = set(manage_by_group) | set(manager_groups)
        group_names = context.get_groups_title(manage_by_group)

        group_filter = form.get('user-groups', '')
        if group_filter and type(group_filter) != list:
            group_filter = set([group_filter])

        # find the current groups
        for current_group_name in group_filter:
            for group_name in group_names:
                if group_name["group_id"] == current_group_name:
                    group_name["current"] = True
        self.search_user_groups = group_names

        self.many_users =  self.usersview.many_users
        self.many_groups = self.usersview.many_groups # used yet 
        #TODO: what if many_groups? should disable query by group. If many users should we show all in a group too?
        gtool = getToolByName(context, 'portal_groups')
        mtool = getToolByName(context, 'portal_membership')

        # Do search with query or by group, or if not many_users set then display everyone
        if self.searchString or group_filter or not self.many_users:
            if not self.searchString and group_filter:
                # it's more efficient to list out the users of a particular group since there could be many users
                def get_users(groups, found=set()):
                    "recursively get memembers of the group"
                    results =[]
                    for group in groups:
                        found.add(group) # Just in case of recursive groups?
                        for user_id in gtool.getGroupMembers(group):
                            if user_id in found:
                                continue
                            user = mtool.getMemberById(user_id)
                            if user is None:
                                # It's a group. We should manage users of that group also
                                results.extend(get_users([user_id], found))
                                continue
                            results.append(dict(
                                login=user.getUserName(),
                                fullname=user.getProperty('fullname',''),
                                email=user.getProperty('email',''),
                                id=user.id,
                                userid=user.id))
                            found.add(user_id)
                    return results
                results = get_users(group_filter)
                results.sort(key=lambda u: u['fullname'])
            else:
                # use search feature first and then filter by group later
                results = self.usersview.doSearch(self.searchString)
            acl = getToolByName(self, 'acl_users')
            for user_info in results:
                userId = user_info['id']
                user = acl.getUserById(userId)
                user_info['login'] = user.getUserName() # fix bug when searching by email or fullname
                user_info['groups'] = self.getGroups(user)
                user_info['user_status'] = context.get_status(user)
                # filter out users who we don't manage
                if  self.context.manage_all not in manage_by_group and not user_info['groups']:
                    continue
                if group_filter and not set(user.getGroups()).intersection(group_filter):
                    continue
                self.searchResults.append(user_info)


        return self.index()

    def getGroups(self, user):
        """Get user groups."""
        if not user:
            return ""

        context = self.context.aq_inner
        login_manage_by_groups = context.get_manage_by_groups()
        user_group_ids = user.getGroups()
        user_groups = user_group_ids
        if context.manage_all not in login_manage_by_groups:
            user_groups = set(login_manage_by_groups) & set(user_group_ids)

        group_names = context.get_groups_title(user_groups)
        return ", ".join(
            [group_name["group_title"] for group_name in group_names])

    def makeQuery(self, **kw):
        return make_query(**kw)


class UserProfileView(BrowserView):

    """User profile browser view."""
    index = ViewPageTemplateFile("templates/user_profile_view.pt")

    def __init__(self, context, request):
        """Initial this browser view."""
        self.context = context
        self.request = request
        self.userid = self.request.get("userid", "")
        self.loginid = self.request.get("loginid", "")
        self.user_fullname = ""
        self.user_group = ""
        self.user_email = ""
        self.user_approved_by = ""
        self.user_approved_date = ""
        self.user_last_updated_by = ""
        self.user_last_updated_date = ""
        self.user_status = ""
        self.user_is_active = False

    def __call__(self):
        """Call this browser view."""
        # aq_inner is needed in some cases like in the portlet renderers
        # where the context itself is a portlet renderer and it's not on the
        # acquisition chain leading to the portal root.
        # If you are unsure what this means always use context.aq_inner
        context = self.context.aq_inner
        form = self.request.form
        self.userid = form.get("userid", "")
        self.loginid = form.get("loginid", "")
        self.user_edit = form.get("form.button.edit", None) is not None
        self.user_activate = form.get("form.button.activate", None) is not None
        self.user_deactivate = form.get(
            "form.button.deactivate", None) is not None

        if not self.userid:
            return self.index()

        if self.user_edit:
            edit_view = "%s/user_edit_view?userid=%s" % (
                self.context.absolute_url(), self.userid)
            self.request.response.redirect(edit_view)

        portal_membership = getToolByName(context, 'portal_membership')

        if portal_membership.isAnonymousUser():
            raise Unauthorized('You need to login to access this page.')

        current_user = portal_membership.getAuthenticatedMember()
        user_groups = current_user.getGroups()
        sm = getSecurityManager()
        portal = getUtility(ISiteRoot)

        # user_management_list = context.get_management_dict()
        manage_by_group = context.get_manage_by_groups()
        manage_all = context.get_manage_all()

        # TODO: "checking for * should be done in get_manage_by_groups"
        if sm.checkPermission(ManagePortal, portal) and not manage_by_group:
            # show all for adminstratior/manager
            manage_by_group = [manage_all]

        if not manage_by_group:
            raise Unauthorized(UNAUTHORISED_ERROR)

        user = portal_membership.getMemberById(self.userid)
        if not user:
            context.plone_utils.addPortalMessage(
                _(u'This user does not exists.'))
            return self.index()

        user_groups = user.getGroups()
        same_groups = user_groups
        if manage_all not in manage_by_group:
            # TODO((ivan) limit the search instead of doing it after that
            same_groups = set(manage_by_group) & set(user_groups)
            if not same_groups:
                raise Unauthorized(UNAUTHORISED_ERROR)

        self.user_fullname = user.getProperty('fullname', '')
        self.user_email = user.getProperty('email', '')
        approved_by = user.getProperty('approved_by', '')
        self.user_approved_by = context.get_user_name(
            approved_by)
        self.user_approved_date = user.getProperty('approved_date', '')
        last_updated_by = user.getProperty('last_updated_by', '')
        self.user_last_updated_by = context.get_user_name(
            last_updated_by)
        self.user_last_updated_date = user.getProperty('last_updated_date', '')
        self.user_status = context.get_status(user)
        self.user_is_active = context.is_active(user)
        # display the groups based from the login user management list
        group_names = context.get_groups_title(same_groups)
        self.user_group = ", ".join(
            [group_name["group_title"] for group_name in group_names])

        if self.user_activate:
            context.user_activate(self.userid, self.request)

            profile_view = "%s/user_profile_view?userid=%s" % (
                self.context.absolute_url(), self.userid)
            self.request.response.redirect(profile_view)

        if self.user_deactivate:
            context.user_deactivate(self.userid)

            profile_view = "%s/user_profile_view?userid=%s" % (
                self.context.absolute_url(), self.userid)
            self.request.response.redirect(profile_view)

        return self.index()


class UserEditView(BrowserView):

    """User edit browser view."""
    index = ViewPageTemplateFile("templates/user_edit_view.pt")

    def __init__(self, context, request):
        """Initial this browser view."""
        self.context = context
        self.request = request
        self.user_fullname = ""
        self.user_group = ""
        self.user_email = ""
        self.user_approved_by = ""
        self.user_approved_date = ""
        self.user_last_updated_by = ""
        self.user_last_updated_date = ""
        self.user_status = ""

    def __call__(self):
        """Call this browser view."""
        # aq_inner is needed in some cases like in the portlet renderers
        # where the context itself is a portlet renderer and it's not on the
        # acquisition chain leading to the portal root.
        # If you are unsure what this means always use context.aq_inner
        context = self.context.aq_inner
        form = self.request.form
        self.userid = form.get("userid", "")
        self.loginid = form.get("loginid", "")
        self.field_fullname = form.get("fullname", "")
        self.field_user_group = form.get("user-group", "")
        self.user_save = form.get("form.button.save", None) is not None
        self.user_cancel = form.get("form.button.cancel", None) is not None

        if not self.userid:
            return self.index()

        # "Cancel" action
        if self.user_cancel:
            profile_view = "%s/user_profile_view?userid=%s" % (
                self.context.absolute_url(), self.userid)
            self.request.response.redirect(profile_view)

        portal_membership = getToolByName(context, 'portal_membership')

        if portal_membership.isAnonymousUser():
            raise Unauthorized('You need to login to access this page.')

        current_user = portal_membership.getAuthenticatedMember()
        user_groups = current_user.getGroups()
        sm = getSecurityManager()
        portal = getUtility(ISiteRoot)

        # user_management_list = context.get_management_dict()
        # manager_groups = context.get_manager_groups()
        manage_by_group = context.get_manage_by_groups()
        manage_all = context.get_manage_all()

        if sm.checkPermission(ManagePortal, portal) and not manage_by_group:
            # show all for adminstratior/manager
            manage_by_group = [manage_all]

        if not manage_by_group:
            raise Unauthorized(UNAUTHORISED_ERROR)

        user = portal_membership.getMemberById(self.userid)
        if not user:
            context.plone_utils.addPortalMessage(
                _(u'This user does not exists.'))
            return self.index()

        user_groups = user.getGroups()
        same_groups = user_groups
        if manage_all not in manage_by_group:
            # TODO(ivan) limit the search instead of doing it after that
            same_groups = set(manage_by_group) & set(user_groups)
            if not same_groups:
                raise Unauthorized(UNAUTHORISED_ERROR)

        self.user_fullname = user.getProperty('fullname', '')
        self.user_email = user.getProperty('email', '')
        approved_by = user.getProperty('approved_by', '')
        self.user_approved_by = context.get_user_name(
            approved_by)
        self.user_approved_date = user.getProperty('approved_date', '')
        last_updated_by = user.getProperty('last_updated_by', '')
        self.user_last_updated_by = context.get_user_name(
            last_updated_by)
        self.user_last_updated_date = user.getProperty('last_updated_date', '')
        self.user_status = context.get_status(user)
        # in edit page, login user allow to assign the user to the group that
        # they allow and its own groups as well.
        # edit_user_groups = set(manage_by_group) | set(manager_groups)
        group_names = self.context.get_groups_title(manage_by_group)
        # find the current groups
        current_group_name = list(same_groups)[0]
        for group_name in group_names:
            if group_name["group_id"] == current_group_name:
                group_name["current"] = True
                break
        self.user_group = group_names

        # "Save" action
        if self.user_save:
            context.update_member(
                self.request,
                self.userid,
                self.field_fullname,
                current_group_name,
                self.field_user_group)

            profile_view = "%s/user_profile_view?userid=%s" % (
                self.context.absolute_url(), self.userid)
            self.request.response.redirect(profile_view)

        return self.index()
