collective.pfg.signup
=====================

![CI](https://github.com/collective/collective.pfg.signup/workflows/CI/badge.svg)

[![Coverage Status](https://coveralls.io/repos/github/collective/collective.pfg.signup/badge.svg?branch=fix_userid_username)](https://coveralls.io/github/collective/collective.pfg.signup?branch=fix_userid_username)


.. contents::

Introduction
============

Flexible member registration, membership workflow and membership management in Plone.

Features:

- Customisable user registration forms (via PloneFormGen);
- different registration forms for certain areas of the site;
- user approval workflow and user management based on groups;
- collecting additional information about members.

This plugin provides a PloneFormGen save adapter that uses the details from the 
submitted form to add Plone members.

It can be configured to:

- put the user in a predefined group, and
- allow members of a group to approve users before they are added. 
- The destination group or the group of approvers can be predefined, or
- you can configure a template to work out the group names from the submitted form data.

Use Cases
---------

There are 3 use cases:

- User is automatically created with the password supplied in the form.
- User is created, password is randomly generated, and a password reset email is sent.
- User is held within the adaptor, pending approval.

### Destination group

Once someone is signed up, they are added to a *destination group*.
The id of the destination group is determined by the **destination group id template**
in your signup adapter.

If you enter `Members` into the **destination group id template** field, all
users will be added to the `Members` group.

You can vary the group that a user gets added to by using variable substitution
in your **destination group id template** field.
For example, if you create a registration form with a selection box called
**organisation** with the values `IBM`, `APPLE`, `GOOGLE`, you can get the
adapter to add your users into groups such as `Members_APPLE`, `Members_IBM`,
`Members_GOOGLE` by entering a `Members_${organisation}` as the value for the
**destination group id template** field.

The substitutions need to correspond to fields on your registration form
and the groups need to exist, otherwise the registrations will be held
for approval and an error email sent to the portal administrator.

### Approving user registration

Optionally you can have a group or groups who will be responsible for approving
user registrations.
You can do this using the **approver group id template** configured in the signup
adapter.
This field also undergoes variable substitution as detailed above.
If the group has an email address configured, then this email address will be used to send a
notification that a user needs approval. 
Otherwise an email will be sent to every member of the approval group.
If the approval group is empty or doesn't exist, a error message will be sent
to the portal administrator.
For example in the example above, if the value of **approver group id template** is
`Members_${organisation}_approvers`, you would have to create
groups such `Members_APPLE_approvers`, `Members_IBM_approvers`, etc. Members of these
groups would then be notified so that they can approve or reject users signing
up to join the corresponding `Members_APPLE`, etc, groups.

If you want to store the information entered into a signup form,
or take any other actions based on this information,
you can configure an additional PFG save action adapter.
Instead of directly activating that on the form, 
configure it as the **approved save action adapter** in the signup adapter
and this adapter will be activated only once the user has finally been approved.
You can use this with a scriptable adapter for example to do scriptable actions
on user approval.

Membership management view
--------------------------

This plugin adds the `@@user_search_view` browser view, which improves upon the 
default Plone **Users and Groups** settings page for member management.

User profile pages are filtered by the **Manage Group Template** field.
Members have the fields **Access approved by**, **Access approved
date**, **Access last updated by** and **Access last updated date** to have a
record of membership management actions.

There are **activate** and **deactivate** buttons to disable user for accessing
the site.
