collective.pfg.signup
=====================

.. contents::

Introduction
============

Create flexible user registration forms using PloneFormGen.

The problem it is trying to solve is

 - having customisable user registration forms
 - having registration forms just for certain areas of the site
 - user approval workflow
 - collecting other information about users who signup

A PloneFormGen save adapter that takes details form the submitted form and uses them to add a user to Plone.
Can be configured put the user in a predefined group. Can be configued to allow
members of a group to approve the user before they are added. The destination group or the group of approvers can 
either be predefined, or you can configure a template to work out the group names from the submitted form data.

Use Cases
---------

There are 3 use cases.

 - User is automatically created with the password supplied in the form
 - User is created, password is randomly generated, and a password reset email is sent
 - User is held within the adaptor, pending appoval

Once someone is signed up they are adding a group called the destination group. The id of the destination
group is determined configuring a "destination group id template" in your signup adapter.
If you enter a "Members" into the "destination group id template" the adapter will add every user that signups
via this form to the group "Members". You can however differentiate which group a user gets added to via
using variable substitution in your "destination group id template". For example if you create a registration form
with a selection box called "organisation" with values IBM,APPLE,GOOGLE, you can get the adapter to add your users
into the approriate groups such as "Members_APPLE", "Members_IBM", "Members_GOOGLE" by entering a
"destination group id template" of "Members_${organisation}". The substitutions have to be the same ids as fields
you created on your registration form and these groups have to exist, otherwise the registrations will be held
for approval and an error email sent to the portal administrator.

Optionally you can have a group or groups who will be responsible for approving user registrations. You can
do this using the "approver group id template" configured in the signup adapter. This could be a single group
or a dynamic group worked out from the registration form fields using the same template format as above. If the
group has an email then this email address will be used to send a notification that a user needs approval. Otherwise
an email will be sent to every member of the approval group. If the approval group is empty or doesn't exist then a
error message will be sent to the portal administrator.
For example in the example above, "approver group id template" = "Members_${organisation}_approvers" would mean you
would have to create
groups such "Members_APPLE_approvers" which you can add members who would be sent notifications so they can approve or
reject users signing up to joing the group "Members_APPLE".

If you want to store or do other actions with the information entered into a signup form then you can configure an
additional PFG save action adapter. Instead of directly activating that on the form, in the signup adapter configure it
as the "approved save action adapter" and this adapter will be activated only once the user has finally been approved.
You can use this with a scriptable adapter for example to do scriptable actions on user approval.

