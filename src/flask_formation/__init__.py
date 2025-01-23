import copy
import types
import typing as t

from flask import Response, abort, g, make_response, redirect, request
from flask_wtf import FlaskForm
from flask_wtf.form import _Auto
from multidict import MultiDict
from werkzeug.datastructures import CombinedMultiDict, ImmutableMultiDict
from werkzeug.utils import cached_property
from wtforms import Field, HiddenField, SubmitField
from wtforms.fields.core import UnboundField

from flask_formation.class_helpers import Labeler
from flask_formation.dictionary_helpers import (
    update_nested_dictionary_with_format_string,
)
from flask_formation.exception import (
    FormNotSubmitted,
    FormNotValidated,
    RerenderTemplate,
)
from flask_formation.field import SubmitButtonField
from flask_formation.class_helpers import update_attributes
from flask_formation.type import Document
from flask_formation.widget import BasicFormWidget, FormWidget


class Form(Labeler, FlaskForm):
    """
    A form class that wraps FlaskForm.

    Key form events are handled by overridable methods:

        Valid Submission (valid_form_handler):
            Method for handling a valid form submission when all goes well.

        Invalid Submission (invalid_form_handler):
            A method for handling a form submission when the user sends a invalid form data.

        Catastrophic Submission (error_form_handler):
            A method for handling a python error during one of the other handlers.
            This is perfect for logging the error.

    This class also supports building a form's default values from a document(Mapping type).
    """

    formdata: MultiDict | None = None

    submit_field_name = "submit_field"
    id_field_name = "form_id_field"
    form_tag_field_name = "form_tag_field"
    document_default_attribute_name = "document_default"

    document: Document = lambda: {}

    @cached_property
    def csrf_token_string(self) -> str:
        """The csrf token in string form."""
        if not hasattr(self, "meta"):
            self.meta = self.Meta()
        return self.meta.csrf_class.generate_csrf_token(self, None)

    @cached_property
    def field_defaults(self) -> dict:
        """A dictionary of field-name and default value for a WTForms field.
        This overrides on a per field basis the document default for that field.

        Returns:
            dict: Dictionary
        """
        if not hasattr(self, "meta"):
            self.meta = self.Meta()
        return {self.meta.csrf_field_name: self.csrf_token_string}

    @cached_property
    def widget_defaults(self) -> dict[str, t.Any]:
        """A dictionary of defaults passed into this a form widget's __init__ method.
        They correspond to attributes on the widget's instance.
        They can be overridden by Form.render key word arguments.

        Returns:
            dict: Dictionary with strings as it's keys.
        """
        return {}

    form_id_field = HiddenField()
    form_tag_field = HiddenField()

    submit_field = SubmitButtonField()

    @cached_property
    def form_tag(self) -> str:
        """This tells each form apart. It can be overwritten by a subclass as well

        Returns:
            str: String identifier for this form class.
        """
        return self.snake_name()

    def input_fields(self) -> t.Iterable[Field]:
        """Yields fields that are used for inputs. Hidden fields and submit fields are excluded."""
        for field in self._fields.values():
            if isinstance(field, (HiddenField, SubmitButtonField, SubmitField)):
                continue
            yield field

    def document_fields(self) -> t.Iterable[Field]:
        """Yields all fields that have their value set by the document."""
        for field in self.input_fields():
            if not getattr(field, self.document_default_attribute_name, None):
                continue
            yield field

    class Meta(FlaskForm.Meta):
        def wrap_formdata(self, form: "Form", formdata):
            # return None
            if formdata is _Auto:
                if form.is_submitted():
                    if request.files:
                        return CombinedMultiDict((request.files, request.form))
                    elif request.form:
                        return request.form
                    elif request.is_json:
                        return ImmutableMultiDict(request.get_json())

                return None

            return formdata

    @staticmethod
    def unbound_field_bind(self: UnboundField, form: "Form", **kwargs) -> Field:
        """The custom bind function called on UnboundFields when binding them to this form.
        It simply handles the "document_default" argument supplied into a field,
            so it doesn't need to be handled directly by the field.
        This function also calls the original .bind() method on the field's __class__ (UnboundField in most cases).

        Args:
            self (UnboundField): WTForms UnboundField.
            form (Form): A FormationForm.

        Returns:
            Field: A bound WTForms Field.
        """
        # Save unbound field state
        unbound_field_state = copy.deepcopy(self.__dict__)

        # Pop custom arguments
        document_default: bool | str = self.kwargs.pop(
            form.document_default_attribute_name, True
        )
        include_in_widget: bool | callable[bool] = self.kwargs.pop(
            "include_in_widget", True
        )

        # Explicitly call the parent class's bind method
        bound_field: Field = self.__class__.bind(self, form=form, **kwargs)

        # Set document_default
        setattr(bound_field, form.document_default_attribute_name, document_default)
        setattr(bound_field, "include_in_widget", include_in_widget)

        # Replace unbound field state
        self.__dict__ = unbound_field_state

        return bound_field

    def __init__(self, formdata=_Auto, **kwargs):
        """This method initializes the form and handles the submission from the client if there is one.
        Extra key word arguments are used to set one of the following:
            - Default value of a field if the key is a field name
            - Attributes on the current instance of this class

        If there is a field named submit_field it is moved to the bottom of the _fields dictionary.

        Note: If a form is submitted then the endpoint stops at that form.
        This means code after a submitted forms initialization won't be run. Be mindful of cleanup code.

        Warning: The .bind() method on UnboundFields for this form will be wrapped with a function.
            This function pops document_default from this form's fields key word arguments and saves it as a field attribute.
            This function is a staticmethod on flask_formation.Form called unbound_field_bind

        Args:
            formdata (Any): Passed into super.__init__(...) call. Defaults to flask_wtf.form._Auto.

        Raises:
            AssertionError: When there isn't a form tag field in this form.
                This field is required so flask_formation knows which form was submitted.
        """
        # Get the names of all the fields
        unbound_field_names = [
            field.name or field_name for field_name, field in self._unbound_fields
        ]
        # Strip the key value pairs from kwargs that set field default values
        self.field_defaults: dict = self.field_defaults
        self.field_defaults.update(
            {
                field_name: kwargs.pop(field_name)
                for field_name in list(kwargs)
                if field_name in unbound_field_names
            }
        )
        self.field_defaults.setdefault(self.form_tag_field_name, self.form_tag)

        for _, unbound_field in self._unbound_fields:
            unbound_field.bind = types.MethodType(
                self.unbound_field_bind, unbound_field
            )

        # call super __init__
        meta = self.Meta()
        self.formdata = meta.wrap_formdata(self, formdata)
        super().__init__(formdata=self.formdata, **self.field_defaults)

        # Assert that this form has a form tag field
        assert (
            self.form_tag_field_name in self._fields
        ), f"The field {repr(self.form_tag_field_name)} is required for this Form to operate"

        # Ensure submit_field is moved to the end of the _fields map and thus rendered last
        if self.submit_field_name in self._fields:
            # Remove the submit field temporarily
            submit_field = self._fields.pop(self.submit_field_name)
            # Re-add the submit field to the end
            self._fields[self.submit_field_name] = submit_field

        # Set form attributes from extra key word arguments
        update_attributes(self, **kwargs)

        if callable(self.document):
            self.document = self.document.__func__()

        try:
            formation_response = self.submission_handler()
            return abort(formation_response)
        except FormNotSubmitted:
            pass
        except RerenderTemplate:
            pass

    def field2document_key(self, field: "Field") -> str:
        """Overridable method for getting the key/attribute-name used on the widget's document
        when getting the default value for a form field from the widget's document.

        Args:
            field (Field): Any wtforms field or object with an id attribute.

        Returns:
            str: Defaults to the field's short_name.
        """

        return field.short_name

    def widget_builder(self, widget: FormWidget, **widget_kwargs) -> FormWidget:
        """A builder for the widget parameter built with all extra key values supplied.

        Args:
            widget (FormWidget): Any flask_formation FormWidget subclass.

        Returns:
            FormWidget: An instance on the widget parameter.
        """
        combined_widget_kwargs = update_nested_dictionary_with_format_string(
            self.widget_defaults, widget_kwargs, format_undefined_value=False
        )
        combined_widget_kwargs.setdefault("document", self.document)

        return widget(form=self, **combined_widget_kwargs)

    def render(
        self,
        widget: FormWidget = BasicFormWidget,
        **widget_kwargs,
    ):
        """Directly renders the widget class supplied after building the widget.

        Args:
            widget (FormWidget, optional): Any flask_formation FormWidget subclass. Defaults to BasicFormWidget.

        Returns:
            Markup: The rendered Markup for the widget supplied.
        """
        return self.widget_builder(widget=widget, **widget_kwargs).render()

    def validate(self, extra_validators=None):
        try:
            assert self.authorize_document()
        except AssertionError as e:
            message = str(e or "You don't have permission to perform that action")
            self.form_errors.append(message)
            raise FormNotValidated(message)
        return super().validate(extra_validators)

    def submission_handler(self) -> Response | None:
        """This method can be called an any time.  It delegates functionality to other more single use methods.
        First there's a check if this form was submitted.
        If this form was submitted and is validated then a flask.Response is made using flask.make_request.
            The body of this request is the response from valid_form_handler() or the default form response.
        If submitted but not validated then the invalid_form_handler() is called and a RerenderTemplate is triggered.

        Raises:
            FormNotSubmitted: If this form wasn't submitted. From .is_submitted()
            FormNotValidated: Internally handled if this form wasn't validated. From .validate()
            RerenderTemplate: Exception to trigger a rerender of the jinja template.
                Simply means that the form request isn't handled and the template is rerendered.

        Returns:
            Response: Success response to be sent to the client.
        """
        if not self.is_submitted():
            raise FormNotSubmitted

        try:
            if self.validate():
                response = make_response(
                    self.valid_form_handler() or self.default_form_response()
                )
                self.success_form_handler()
                return response
            else:
                raise FormNotValidated(
                    f"Validation error for {self.class_name()} form.  Errors were {self.errors}"
                )

        except FormNotValidated as exception:
            self.invalid_form_handler()
            g.formation_error_form = self
            raise RerenderTemplate from exception

        except Exception as exception:
            self.error_form_handler(exception)
            raise RerenderTemplate from exception

    def form_tag_field_validator(self):
        """Return boolean of whether form_tag_field from form data is equal to self.form_tag.
        The formdata from this class hasn't been set yet as this is the check on whether to set the formdata to this form.

        Returns:
            bool: True or False
        """
        return request.form.get(self.form_tag_field_name) == self.form_tag

    def is_submitted(self) -> bool:
        """Checks if this form was submitted from the client.  Criteria are:
            - HTTP methods (from super() call)
            - form_tag field matches this form's tag

        Returns:
            bool: Whether this form was submitted
        """
        return super().is_submitted() and self.form_tag_field_validator()

    def default_form_response(self):
        """The default response if valid_form_handler doesn't return a truthy value.

        Returns:
            Response: Redirect to current page.
        """
        return redirect(request.url)

    def authorize_document(self) -> bool:
        """A validation function for whether this form's document is authorized.
        Assertions are also excepted.

        Returns:
            bool: Boolean or Any (will be evaluated into a Boolean)
        """
        return True

    def valid_form_handler(self) -> None | Response:
        """Handles the form once it's validated.

        Returns:
            None: Response not specified, so the default response will be used.
            Response: Response (or anything that flask.make_response takes) specified, so it will be send directly to the user
        """
        print("Valid form submission", self.class_name())

    def success_form_handler(self):
        """Handles the form once it's validated and valid_form_handler has finished.
        Return value not used.
        """
        print("Success form submission", self.class_name())

    def invalid_form_handler(self):
        """Handles the form if there was a validation issue.
        Return values are unused by flask_formation
        """
        print("Invalid form submission", self.errors, self.class_name())

    def error_form_handler(self, exception: Exception):
        """Handles any handling errors during a form submission. These would be catastrophic errors.
        The ideal purpose would be to log the error here. The template is rerendered by default after error.

        Args:
            exception (Exception): The exception that caused this mess.
        """
        print("Error during form submission", exception, self.client_name())
