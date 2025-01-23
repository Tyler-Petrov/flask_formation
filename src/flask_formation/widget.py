import base64
import json
import typing as t
from collections.abc import Mapping

from markupsafe import Markup, escape
from multidict import MultiDict
from werkzeug.utils import cached_property
from wtforms import Field, FieldList, FormField
from wtforms.widgets import Input, html_params

from flask_formation import Form
from flask_formation.class_helpers import Labeler, cache_method, update_attributes
from flask_formation.dictionary_helpers import (
    update_nested_dictionary_with_format_string,
)
from flask_formation.enum import CrudOperation
from flask_formation.field import WidgetField
from flask_formation.string_helpers import PluralityAwareString
from flask_formation.type import HTML, Document


class FormWidget(Labeler):
    """A class for rendering a Form.
    This class is initialized for every render, so that attributes don't intersect.

    All subclasses of this base widget are stored in a FormWidget.subclasses dictionary.
    """

    form: "Form"

    legend: HTML | None = None
    document: Mapping | t.Callable[[], Mapping] = lambda: {}
    set_field_document_defaults: bool = True
    ignored_document_default_fields: list[str] = []
    formdata: MultiDict | None

    subclasses = {}

    @cached_property
    def crud_operation(self) -> CrudOperation:
        """Stores the widget's CRUD operation when submitted.
        Purely for rendering purposes and won't effect form submission handling.

        Returns: CrudOperation enum member."""
        return CrudOperation.Update

    def __init_subclass__(cls):
        FormWidget.subclasses[cls.class_name()] = cls

    @cached_property
    def document_name(self) -> PluralityAwareString | t.Any:
        return PluralityAwareString("Document(s)")

    @cached_property
    def widget_tag(self) -> str:
        """Used to identify the widget type, but not between two widgets of the same type or two widgets of different forms."""
        return self.snake_name()

    @cached_property
    def token(self) -> str | None:
        """Used to identify form widgets apart from each other even if they're the same type and form."""
        return None

    def widget_formdata(self) -> MultiDict | None:
        """Get's the formdata for this specific widget. Might not be the same formdata as another widget rendering the same form.

        Returns:
            MultiDict | None: Formdata
        """
        if self.form.formdata is None:
            return None

        form_id = self.form.formdata.get(self.form.id_field_name) or None
        if form_id != self.id:
            return None

        return self.form.formdata

    @property
    def id(self) -> str | None:
        """Value put in for the form id field of this widget's form.
        Used to identify form widgets apart from each other even if they're the same type and form.
        It's a concatenation self.form.form_tag, self.widget_tag, and self.token if token is not None.
        """

        if self.token is None:
            return None

        return f"{self.form.form_tag}-{self.widget_tag}-{self.token}"

    def __init__(self, form: "Form", **kwargs):
        self.form = form

        # Set form attributes from extra key word arguments
        update_attributes(self, **kwargs)
        self.formdata = self.widget_formdata()

    @cached_property
    def title(self) -> HTML:
        return f"{self.crud_operation.name} {self.document_name}"

    @cached_property
    def subtitle(self) -> HTML:
        return ""

    @classmethod
    def html_params_builder(cls, **html_params_dictionary) -> str:
        """Builds all key word arguments into a string rendered as HTML element parameters.
        If the value for an HTML parameter is None then it is ignored.

        Returns:
            str: HTML parameter string.
        """
        return html_params(
            **{
                key: value
                for key, value in html_params_dictionary.items()
                if value is not None
            }
        )

    @cached_property
    def field_values_override(self) -> dict:
        """Field defaults that override everything else, including formdata from the request.

        Returns:
            dict: Key is field name, value is the field default
        """
        return {
            self.form.id_field_name: self.id,
        }

    @cached_property
    def excluded_widget_field_names(self) -> list[str]:
        return []

    @classmethod
    def markup_builder(
        cls,
        input_content: HTML | None,
        output_wrapper: tuple[str | Markup, str | Markup] | None = None,
    ) -> Markup:
        """Builds safe Markup from the supplied parameters.
        Output is escaped unless the input is specifically specified as markup by being a Markup type.
        If the input is a list then this method is called recursively.
        Thus this method can handle any depth of nested lists.

        Note: If input_content is None then an empty Markup string is returned.
            This string is not wrapped by the wrapper.

        Args:
            input_content (HTML(str | Markup | list[str | Markup]) | None):
                Input to be built into markup.
            output_wrapper (tuple[str  |  Markup, str  |  Markup] | None, optional):
                Optional parameter that wraps output.
                The first item in this tuple goes at the beginning, and the second goes at the end.
                Defaults to None.

        Returns:
            Markup: _description_
        """

        if input_content is None:
            return Markup("")

        if isinstance(input_content, Markup):
            output_html = input_content
        elif isinstance(input_content, list):
            output_html = " ".join(
                cls.markup_builder(input_piece) for input_piece in input_content
            )
        else:
            output_html = escape(input_content)

        if isinstance(output_wrapper, tuple):
            wrapper_start, wrapper_end = output_wrapper

            if not isinstance(wrapper_start, Markup):
                wrapper_start = escape(wrapper_start)
            if not isinstance(wrapper_end, Markup):
                wrapper_end = escape(wrapper_end)

            output_html = f"{wrapper_start}{output_html}{wrapper_end}"

        return Markup(output_html)

    @classmethod
    def base64_encoder(cls, input_string):
        """
        Encodes a UTF-8 string into a URL-safe Base64-encoded string.

        :param input_string: The input string to encode. If None, returns an empty string.
        :return: A URL-safe Base64-encoded string.
        """
        if input_string is None:
            return ""
        # Convert the input string to bytes using UTF-8 encoding
        bytes_string = str(input_string).encode("utf-8")
        # Encode the bytes to Base64 and ensure the output is URL-safe
        base64_bytes = base64.urlsafe_b64encode(bytes_string)
        # Convert the Base64-encoded bytes back to a UTF-8 string
        base64_string = base64_bytes.decode("utf-8")
        return base64_string

    def render_legend(self, **legend_html_params) -> Markup:
        """Delegation function for rendering this widget's legend.
        Calls widget.markup_builder with a <legend> tag wrapper.

        Returns:
            Markup: Html markup
        """

        return self.markup_builder(
            self.legend,
            output_wrapper=(
                Markup(f"<legend {self.html_params_builder(**legend_html_params)}>"),
                Markup("</legend>"),
            ),
        )

    def field2document_value(self, field: "Field") -> t.Any | None:
        """For getting the default value for each field from the widget's document.
        This method supports both a Mapping and an Object for the widget's document.

        If either the fields name or short_name is in this widget's ignored_document_default_fields then None is returned.

        Uses widget.form.field2document_key(...) for the key/attribute-name used on this widget's document.

        How the document key is used:
            If this widget's document is a Mapping the get the value by key, default as None
            If that didn't work then get the attribute with the key as it's name from the widget's document, default is None
            If field_default is a callable then return None

        Args:
            field (Field): Any wtforms field or object with an id attribute

        Returns:
            Any: The value from the form's document that corresponds to the field
        """

        if (
            any(
                field_name in self.ignored_document_default_fields
                for field_name in {field.name, field.short_name}
            )
            or getattr(field, self.form.document_default_attribute_name, True) is False
        ):
            return None

        document_key = self.form.field2document_key(field=field)

        # Update document key to be the fields document_default if it's a string
        field_document_default_key = getattr(
            field, self.form.document_default_attribute_name, True
        )
        if isinstance(field_document_default_key, str):
            document_key = field_document_default_key

        # Set field_default from document_key
        field_default = None
        if hasattr(self.document, "get"):
            field_default = self.document.get(document_key, None)
        if field_default is None:
            field_default = getattr(self.document, document_key, None)
        if callable(field_default):
            return field_default()

        return field_default

    def widget_field_builder(self, field: "Field") -> WidgetField:
        """Builds a WidgetField from the field passed in.
        Setting the fields default from this widget's document is handled here.

        Setting the fields default form this widget's document can be ignored for the whole widget by setting set_field_document_defaults to falsy value.

        Args:
            field (Field): Any WTForms field.

        Returns:
            WidgetField: See WidgetField docstring
        """

        ######### Check if field should be included in this widget #########
        include_in_widget = getattr(field, "include_in_widget", True)
        if callable(include_in_widget):
            include_in_widget = include_in_widget(self)
        if not include_in_widget:
            return None

        if field.name in self.field_values_override:
            # Don't pass formdata into this builder
            # because the response form shouldn't override these fields
            return WidgetField.build_from_field(
                field=field,
                unprocessed_data=self.field_values_override.get(field.name),
            )

        # Set field default from this widget's document
        set_field_document_defaults = getattr(
            self, "set_field_document_defaults", False
        )
        if set_field_document_defaults:
            field_default_from_document = self.field2document_value(field=field)
            if field_default_from_document is not None:
                return WidgetField.build_from_field(
                    field=field,
                    formdata=self.formdata,
                    unprocessed_data=field_default_from_document,
                )

        # Set field default from from
        field_default_from_form = self.form.field_defaults.get(field.name)
        if field_default_from_form:
            return WidgetField.build_from_field(
                field=field,
                formdata=self.formdata,
                unprocessed_data=field_default_from_form,
            )

        # Build WidgetField without unprocessed data
        return WidgetField.build_from_field(field=field, formdata=self.formdata)

    @cache_method
    def widget_fields(self) -> list[WidgetField]:
        """Bundles each field from this widget's form into a WidgetField (view doc for widget field).

        Also handles FormField and FieldList by placing fields directly into the form.
        Thus FormField and FieldList aren't rendered by their __call__ methods but their sub fields are directly rendered in this form.

        Calls widget_field_builder(...) to actually build the WidgetField.

        Note: This method is cached per instance and not calculated again.

        Returns:
            list[WidgetField]: List of WidgetFields
        """

        def generator(widget: t.Self, fields: t.Iterable[Field]):
            for field in fields:
                if field.name in self.excluded_widget_field_names:
                    continue

                # Handle special case of FieldList
                if isinstance(field, FieldList):
                    for widget_field in generator(
                        widget=widget,
                        fields=iter(field),
                    ):
                        yield widget_field
                    continue

                # Handle special case of FormField
                if isinstance(field, FormField):
                    for widget_field in generator(
                        widget=widget,
                        fields=field.form._fields.values(),
                    ):
                        yield widget_field
                    continue

                yield widget.widget_field_builder(field)

        return [
            field
            for field in generator(widget=self, fields=self.form._fields.values())
            if field is not None
        ]

    def render(self) -> Markup:
        """A method for rendering the widget object.
        It doesn't take any arguments (they're all passed directly to the widget), and doesn't modify it's own attributes.
        This method is mostly invisible to the user of flask_formation as the form class calls this method in it's own .render() method.

        Returns:
            Markup: Any Markup string.
        """
        raise NotImplemented(
            "The method .render() needs to be implemented by a subclass."
        )


class BasicFormWidget(FormWidget):
    """A widget class for a basic form. The form fields are rendered directly in <form> html."""

    @cached_property
    def form_html_params(self):
        """A dictionary of html parameters used for the form (<form> by default) element.

        Returns:
            dict: Key is an html parameter and value is it's value.
        """
        params = {
            "method": "post",
            "class": f"design-grid {self.form.form_tag} {self.widget_tag}",
        }
        if self.id:
            params["id"] = self.id
        return params

    def render(self):
        form_html = [
            f"<form {self.html_params_builder(**self.form_html_params)}>",
            self.render_legend(),
            *(widget_field.markup for widget_field in self.widget_fields()),
            "</form>",
        ]

        return Markup(" ".join(form_html))


class AccordionFormWidget(BasicFormWidget):
    subtitle: HTML = ""

    @cached_property
    def accordion_html_params(self) -> dict:
        """A dictionary of html parameters used for the accordion (<div> by default) element.

        Returns:
            dict: Key is an html parameter and value is it's value.
        """
        return {
            "id": self.id,
            "class": f"accordion {self.widget_tag}",
        }

    def render(self) -> Markup:
        html = [
            f"<div { self.html_params_builder(**self.accordion_html_params) }>",
            f'<div class="header">',
            f'<div class="title-row">',
            f'<h4 class="main">{ self.markup_builder(self.title) }</h4>',
            f'<h6 class="sub">{ self.markup_builder(self.subtitle) }</h6>',
            f"</div>",
            f"</div>",
            f'<div class="body" style="display: none;">',
            super().render(),
            f"</div>",
            f"</div>",
        ]

        return Markup("".join(html))


class DialogFormOpenerWidget(FormWidget):

    icon: str = ""
    widget_html_tag = "button"

    def __init__(self, form, **kwargs):
        super().__init__(form, **kwargs)
        assert (
            self.token is not None
        ), f"{self.class_name()} requires a token to be specified"

    @cached_property
    def icon(self) -> str:
        """Widget icon based on this widget's CRUD operation.

        Returns:
            str: String of font-awesome icon.
        """
        if self.crud_operation == CrudOperation.Create:
            return "fa-plus"
        if self.crud_operation == CrudOperation.Delete:
            return "fa-trash"
        return "fa-edit"

    @cached_property
    def dialog_id(self) -> str:
        """The constructed widget token for the dialog this dialog opener references.
        If the token property is changed on the DialogFormWidget this method will NOT reflect that.

        Returns:
            str: String
        """
        return f"{self.form.form_tag}-{DialogFormWidget.snake_name()}-{self.token}"

    @cached_property
    def excluded_widget_field_names(self):
        # Exclude the csrf token field because it's populated in the dialog by default
        return [
            self.form.meta.csrf_field_name,
            *super().excluded_widget_field_names,
        ]

    @property
    def id(self) -> str:
        return self.dialog_id

    def widget_formdata(self):
        # Overridden to None because the formdata is rendered directly in the DialogFormWidget
        # so it's not needed for the dialog opener.
        return None

    @cached_property
    def dialog_opener_html_params(self) -> dict:
        """A dictionary of html parameters used for the opener (<button> by default) element.
        If this widget's CRUD operation is update then the field defaults are returned here.
        The exact format of the field default html param is set by the .opener_field_default_html_param() method.

        Returns:
            dict: Key is an html parameter and value is it's value.
        """
        return_dict = {
            "class": f"open-form-modal",
            "data-modal-selector": f"#{self.dialog_id}",
            "data-clear-form-values": "true",
            "data-clear-form-errors": "true",
            "form-operation": self.crud_operation.name,
        }

        if self.crud_operation == CrudOperation.Update:
            for widget_field in self.widget_fields():
                key, value = self.opener_field_default_html_param(
                    widget_field=widget_field
                )

                if not value:
                    continue

                return_dict.setdefault(key, value)

        return return_dict

    def opener_field_default_html_param(
        self, widget_field: WidgetField
    ) -> tuple[str, str]:
        """Method for rendering each html parameter that's used to set field values in a dialog

        Args:
            widget_field (WidgetField): A WTForms field in a specific state.

        Returns:
            tuple[str, str]: HTML parameter key and value in tuple form.
        """
        field_data = widget_field.data
        if isinstance(field_data, list | dict):
            field_data = json.dumps(field_data)

        encoded_field_data = self.base64_encoder(field_data)
        return (f"elm-sel{widget_field.name}", encoded_field_data)

    @staticmethod
    def render_inner_markup(widget: "DialogFormOpenerWidget") -> HTML:
        """A staticmethod for rendering the inner markup for this widget.
        This method is a staticmethod so it can easily be overwritten.

        Args:
            widget (DialogFormOpenerWidget): The widget built.

        Returns:
            HTML: The markup to render.
        """
        return widget.markup_builder(widget.title)

    def render(self) -> Markup:

        html = [
            f"<{self.widget_html_tag} { self.html_params_builder(**self.dialog_opener_html_params) }>",
            self.markup_builder(self.render_inner_markup(widget=self)),
            f"</{self.widget_html_tag}>",
        ]

        return Markup("".join(html))


class DialogFormButtonOpenerWidget(DialogFormOpenerWidget):
    widget_html_tag = "button"

    @cached_property
    def dialog_opener_html_params(self) -> dict:
        return update_nested_dictionary_with_format_string(
            super().dialog_opener_html_params, {"class": "{super} brand block"}
        )

    @staticmethod
    def render_inner_markup(widget: "DialogFormButtonOpenerWidget") -> HTML:
        html = [
            f'<i class="fa {widget.icon}"></i>',
            '<div class="title-row">',
            f"<div>{ widget.markup_builder(widget.title) }</div>",
            f"<div>{ widget.markup_builder(widget.subtitle) }</div>",
            "</div>",
        ]

        return Markup("".join(html))


class DialogFormCardOpenerWidget(DialogFormOpenerWidget):
    widget_html_tag = "div"

    @cached_property
    def dialog_opener_html_params(self) -> dict:
        return update_nested_dictionary_with_format_string(
            super().dialog_opener_html_params, {"class": "{super} card"}
        )

    @staticmethod
    def render_inner_markup(widget: "DialogFormCardOpenerWidget") -> HTML:
        html = [
            '<div class="title-row">',
            f"<h6>{ widget.markup_builder(widget.title) }</h6>",
            f"<p>{ widget.markup_builder(widget.subtitle) }</p>",
            "</div>",
        ]

        return Markup("".join(html))


class DialogFormWidget(BasicFormWidget):
    set_field_document_defaults = False

    def __init__(self, form, **kwargs):
        super().__init__(form, **kwargs)
        assert (
            self.token is not None
        ), f"{self.class_name()} requires a token to be specified"

    @cached_property
    def title(self) -> str:
        return self.form.client_name()

    @cached_property
    def dialog_html_params(self) -> dict:
        """A dictionary of html parameters used for the dialog (<dialog> by default) element.

        Returns:
            dict: Key is an html parameter and value is it's value.
        """
        return {
            "id": self.id,
            "class": f"modal {self.widget_tag}",
        }

    def render(self) -> Markup:
        html = [
            f"<dialog { self.html_params_builder(**self.dialog_html_params) }>",
            '<div class="title">',
            f"<h4>{ self.markup_builder(self.title) }</h4>",
            '<button type="button" class="boring close-modal"><i class="fa fa-times"></i></button>',
            "</div>",
            '<div class="body">',
            super().render(),
            "</div>",
            "</dialog>",
        ]

        return Markup("".join(html))


class ListDialogFormWidget(FormWidget):
    @cached_property
    def documents(self) -> t.Iterable[Document]:
        return []

    @cached_property
    def list_html_params(self):
        return {
            "class": "grid",
        }

    @cached_property
    def spacer(self):
        return Markup('<div style="height: var(--size-4)"></div>')

    @staticmethod
    def render_opener_inner_markup(widget: "DialogFormCardOpenerWidget") -> HTML:
        return widget.document

    def render(self):
        html = [
            self.form.render(
                widget=DialogFormWidget,
                token=self.token,
            ),
            '<div class="grid">',
            *(
                self.form.render(
                    widget=DialogFormCardOpenerWidget,
                    token=self.token,
                    document=document,
                    render_inner_markup=self.render_opener_inner_markup,
                )
                for document in self.documents
            ),
            "</div>",
            self.markup_builder(self.spacer),
            self.form.render(
                widget=DialogFormButtonOpenerWidget,
                token=self.token,
                crud_operation=CrudOperation.Create,
            ),
        ]

        return Markup("".join(html))


class SubmitButtonWidget:
    """
    Renders a submit button with the <button> html element
    """

    def __call__(self, field, **kwargs):
        button_html_params = {
            "id": field.id,
            "type": "submit",
            "value": field._value(),
            "name": field.name,
            "class": f"submit-btn brand block {field.snake_name()}",
        }

        button_html_params = update_nested_dictionary_with_format_string(
            button_html_params, kwargs
        )

        return Markup(
            f"<button {html_params(**button_html_params)}>{field.label.text}</button>"
        )


class SectionLabelWidget(Input):
    def __call__(self, field) -> Markup:
        return Markup(
            " ".join(
                [
                    f'<h5 class="form-section-label" id="{field.id}">',
                    field.label.text,
                    "</h5>",
                ]
            )
        )
