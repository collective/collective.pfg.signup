from zope.interface import implements
from AccessControl import ClassSecurityInfo
from Products.Archetypes import atapi
from Products.ATContentTypes.content.base import registerATCT
from Products.ATContentTypes.content import schemata
from Products.PloneFormGen.interfaces import IPloneFormGenActionAdapter
from Products.PloneFormGen.content.actionAdapter import FormAdapterSchema
from Products.PloneFormGen.content.actionAdapter import FormActionAdapter
from Products.PloneFormGen.config import FORM_ERROR_MARKER
from collective.pfg.signup.interfaces import ISignUpAdapter
from collective.pfg.signup.config import PROJECTNAME
from collective.pfg.signup import _


SignUpAdapterSchema = FormAdapterSchema.copy() + atapi.Schema((
    atapi.StringField('username_field',
        default='username',
        required=True,
        widget=atapi.StringWidget(
            label=_(u"label_username_field", default=u"Username Field"),
            description=_(u"help_username_field",
                default=u"Provide the field of the username in "
                         "sign up form."),
         ),
    ),
    atapi.StringField('password_field',
        default='password',
        required=True,
        widget=atapi.StringWidget(
            label=_(u"label_password_field", default=u"Password Field"),
            description=_(u"help_password_field",
                default=u"Provide the field of the passworld in "
                         "sign up form."),
         ),
    ),
))


class SignUpAdapter(FormActionAdapter):
    """A form action adapter that saves signup form"""
    implements(IPloneFormGenActionAdapter, ISignUpAdapter)

    meta_type = 'SignUpAdapter'
    portal_type = 'SignUpAdapter'
    archetype_name = 'SignUp Adapter'
    schema = SignUpAdapterSchema
    security = ClassSecurityInfo()

    def onSuccess(self, fields, REQUEST=None):
        """Save form input."""
        import ipdb; ipdb.set_trace()  # !

        # get username and password
        username = None
        password = None
        for field in fields:
            fname = field.fgField.getName()
            val = REQUEST.form.get(fname, None)
            if fname == self.username_field:
                username = val
            elif fname == self.password_field:
                password = val

        if username is None or password is None:
            return

        # do the registration
        return


registerATCT(SignUpAdapter, PROJECTNAME)
