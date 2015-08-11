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

from itertools import chain
from plone.app.controlpanel.usergroups import UsersGroupsControlPanelView
from zope.component import getMultiAdapter
from zope.component import getUtility

logger = logging.getLogger('collective.pfg.signup')


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
            approve_button = '<a class="btn" href="' + link + \
                '/approve_user?userid=' + key + '">Approve</a>'
            reject_button = '<a class="btn" href="' + link + \
                '/reject_user?userid=' + key + '">Reject</a>'
            results.append([value['username'],
                            value['fullname'],
                            group_name,
                            value['email'],
                            approve_button,
                            reject_button])
        self.results = results
        return self.index()


class UserSearchView(UsersGroupsControlPanelView):

    """User search browser view."""
    MANAGE_ALL = "*"

    def __call__(self):
        """Call this browser view."""
        # aq_inner is needed in some cases like in the portlet renderers
        # where the context itself is a portlet renderer and it's not on the
        # acquisition chain leading to the portal root.
        # If you are unsure what this means always use context.aq_inner
        context = self.context.aq_inner
        portal_membership = getToolByName(context, 'portal_membership')

        if portal_membership.isAnonymousUser():
            raise Unauthorized('You need to login to access this page.')

        form = self.request.form
        # submitted = form.get('form.submitted', False)
        search = form.get('form.button.Search', None) is not None
        findAll = form.get('form.button.FindAll', None) is not None
        self.searchString = not findAll and form.get('searchstring', '') or ''
        self.searchResults = []
        self.newSearch = False

        if search or findAll:
            self.newSearch = True

        # Only search for all ('') if the many_users flag is not set.
        if not self.many_users or bool(self.searchString):
            self.searchResults = self.doSearch(self.searchString)

        return self.index()

    def doSearch(self, searchString):
        """Search users."""
        # TODO(ivan): not sure do we need these code below? should delete?
        acl = getToolByName(self, 'acl_users')
        rolemakers = acl.plugins.listPlugins(IRolesPlugin)

        mtool = getToolByName(self, 'portal_membership')

        user_management_list = self.context.aq_inner.get_management_dict()
        current_user = mtool.getAuthenticatedMember()
        groups_tool = getToolByName(self, 'portal_groups')
        current_group_objects = groups_tool.getGroupsByUserId(current_user.id)
        current_groups = [group.id for group in current_group_objects]
        print "current_groups %s" % current_groups
        common_groups = set(user_management_list.keys()) & set(current_groups)
        print "common_groups %s" % common_groups

        limitGroups = []

        for common_group in common_groups:
            manage_user_group = user_management_list[common_group]
            if self.MANAGE_ALL in manage_user_group:
                limitGroups = [self.MANAGE_ALL]
                break
            limitGroups += manage_user_group
        print "limitGroups %s" % limitGroups

        if not limitGroups:
            # Reset the request variable, just in case.
            self.request.set('__ignore_group_roles__', False)
            return []

        searchView = getMultiAdapter(
            (aq_inner(self.context), self.request), name='pas_search')

        # First, search for all inherited roles assigned to each group.
        # We push this in the request so that IRoles plugins are told provide
        # the roles inherited from the groups to which the principal belongs.
        self.request.set('__ignore_group_roles__', False)
        self.request.set('__ignore_direct_roles__', True)
        inheritance_enabled_users = searchView.merge(chain(*[
            searchView.searchUsers(**{field: searchString}) for field in [
                'login', 'fullname', 'email']]), 'userid')
        allInheritedRoles = {}
        for user_info in inheritance_enabled_users:
            userId = user_info['id']
            user = acl.getUserById(userId)
            # play safe, though this should never happen
            if user is None:
                logger.warn(
                    'Skipped user without principal object: %s' % userId)
                continue
            allAssignedRoles = []
            for rolemaker_id, rolemaker in rolemakers:
                allAssignedRoles.extend(rolemaker.getRolesForPrincipal(user))
            allInheritedRoles[userId] = allAssignedRoles

        # We push this in the request such IRoles plugins don't provide
        # the roles from the groups the principal belongs.
        self.request.set('__ignore_group_roles__', True)
        self.request.set('__ignore_direct_roles__', False)
        explicit_users = searchView.merge(chain(*[searchView.searchUsers(
            **{field: searchString}) for field in [
                'login', 'fullname', 'email']]), 'userid')

        # Tack on some extra data, including whether each role is explicitly
        # assigned ('explicit'), inherited ('inherited'), or not assigned at
        # all (None).
        results = []

        for user_info in explicit_users:
            userId = user_info['id']
            user = mtool.getMemberById(userId)
            # play safe, though this should never happen
            if user is None:
                logger.warn(
                    'Skipped user without principal object: %s' % userId)
                continue

            if self.MANAGE_ALL not in limitGroups:
                # TODO((ivan) limit the search instead of doing it after that
                group_objects = groups_tool.getGroupsByUserId(userId)
                user_groups = [group.id for group in group_objects]
                same_groups = set(limitGroups) & set(user_groups)
                print "user_groups %s" % user_groups
                print "same_groups %s" % same_groups
                if not same_groups:
                    continue

            explicitlyAssignedRoles = []
            for rolemaker_id, rolemaker in rolemakers:
                explicitlyAssignedRoles.extend(
                    rolemaker.getRolesForPrincipal(user))

            roleList = {}
            for role in self.portal_roles:
                canAssign = user.canAssignRole(role)
                if role == 'Manager' and not self.is_zope_manager:
                    canAssign = False
                roleList[role] = {
                    'canAssign': canAssign,
                    'explicit': role in explicitlyAssignedRoles,
                    'inherited': role in allInheritedRoles[userId]}

            canDelete = user.canDelete()
            canPasswordSet = user.canPasswordSet()
            if roleList['Manager']['explicit'] or \
               roleList['Manager']['inherited']:
                if not self.is_zope_manager:
                    canDelete = False
                    canPasswordSet = False

            user_info['roles'] = roleList
            user_info['fullname'] = user.getProperty('fullname', '')
            user_info['email'] = user.getProperty('email', '')
            user_info['can_delete'] = canDelete
            user_info['can_set_email'] = user.canWriteProperty('email')
            user_info['can_set_password'] = canPasswordSet
            user_info['council_group'] = self.getGroups(user)
            user_info['active_status'] = self.getStatus(user)
            results.append(user_info)

        # Sort the users by fullname
        results.sort(
            key=lambda x: x is not None and x['fullname'] is not None and
            normalizeString(x['fullname']) or '')

        # Reset the request variable, just in case.
        self.request.set('__ignore_group_roles__', False)
        return results

    def getGroups(self, user):
        """Get user groups."""
        context = self.context.aq_inner
        portal_groups = getToolByName(context, 'portal_groups')
        group_names = []
        user_group_ids = user.getGroups()
        # how we get pool user groups, generic?
        for user_group_id in user_group_ids:
            user_group = portal_groups.getGroupById(user_group_id)
            # group may not yet exist
            group_name = user_group_id
            if user_group is not None:
                group_name = user_group.getProperty('title')
                if not group_name:
                    group_name = user_group_id
            if group_name:
                group_names.append(group_name)
        return ", ".join(group_names)

    def getStatus(self, user):
        """Get user status."""
        user_group_ids = user.getGroups()
        status = _("Active")
        if len(user_group_ids) == 1 and 'AuthenticatedUsers' in user_group_ids:
            status = _("Inactive")
        return status
