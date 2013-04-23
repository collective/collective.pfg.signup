collective.pfg.signup
=====================

.. contents::

Introduction
============

Create flexible user registration forms using PloneFormGen.
A PloneFormGen save adapter that takes details form the submitted form and uses them to add a user to Plone.
Can be configured put the user in a predefined group. Can be configued to allow
members of a group to approve the user before they are added. The destination group or the group of approvers can 
either be predefined, or you can configure a template to workout the group names from the submitted form data.

Use Cases
---------

There are 3 use cases.

 - User is automatically created with the password supplied in the form
 - User is created, password is randomly generated, and a password reset email is sent
 - User is held within the adaptor, pending appoval

Each use case has a corresponding field where you can list which portal groups a user can sign
up to, and which workflow applies. The actual group the user is added to is a combination of the role,
and the council.

For instance, if the user selects Sydney in the council list, and Manager in the role, they would
be added to the 'Sydney Manager' group. The actual group id would be set in the fields, and an underscore
added between the two element, so sydney_manager.

If no councils are added, then this field is ignored for group ids.
