import hashlib
import re
from typing import Optional

from flask import g, redirect, request
from flask_wtf import FlaskForm
from markupsafe import Markup
from wtforms.fields import HiddenField as WTFormsHiddenField
from wtforms.fields import SubmitField as WTFormsSubmitField
from wtforms.widgets import html_params

from flask_formation.helpers import grammatical_join


#######  Exception Classes  #######
class TriggerTemplateRender(Exception):
    pass


class ObsoleteFormData(Exception):
    pass


class FormValidationError(TriggerTemplateRender):
    pass


#######  Form Classes  #######
class FormationDefaults:
    @classmethod
    def create_submit_field(cls) -> WTFormsSubmitField:
        raise NotImplementedError("create_submit_field must be overridden")

    @classmethod
    def create_hidden_field(cls):
        return WTFormsHiddenField()

    @classmethod
    def create_form_timestamp_field(cls):
        return cls.create_hidden_field()

    @classmethod
    def create_form_hash_field(cls):
        return cls.create_hidden_field()


class FormationForm(FlaskForm, FormationDefaults):
    # form_hash = HiddenField()
    # form_timestamp = HiddenField()

    # Form flags
    db_obj: dict
    delete_sub_form: Optional["FormationDeleteSubForm"]
    form_hash: WTFormsHiddenField
    form_timestamp: WTFormsHiddenField

    def _set_default_form_attr(self, attr_name: str, default):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, default)
        # return getattr(self, attr_name)

    def _generate_form_hash(self):
        # Get the class name
        class_name = self.__class__.__name__
        # Use hashlib to generate a unique hash based on the form class name
        return hashlib.sha256(class_name.encode()).hexdigest()

    def _validate_form_hash(self, potential_form_hash: str | None = None):
        # Default potential_form_hash to the form hash field
        if potential_form_hash is None:
            potential_form_hash = self.form_hash.data

        # Check if the potential form hash is valid
        return self._generate_form_hash() == potential_form_hash

    def get_form_timestamp(self):
        pass

    def check_form_timestamp(self):
        return True

    def error_message(self):
        # Get the labels of all field that have an error
        error_field_labels = [
            getattr(self, field_name).label.text for field_name in self.errors
        ]

        # Set the error message prefix
        if len(error_field_labels) == 1:
            error_message_prefix = "This field has an error"
        else:
            error_message_prefix = "These fields have errors"

        # Concatenate the prefix with the error fields joined by a grammatical join
        return f"{error_message_prefix}: {grammatical_join(error_field_labels)}"

    def __init__(
        self,
        *args,
        db_obj=None,
        **kwargs,
    ):
        #######  Set default form attributes  #######
        self._set_default_form_attr("db_obj", db_obj)

        # #######  Add submit field to form  #######
        self._unbound_fields.append(("submit_field", self.create_submit_field()))

        # #######  Add form hidden fields  #######
        self._unbound_fields.append(("form_hash", self.create_form_hash_field()))
        self._unbound_fields.append(
            ("form_timestamp", self.create_form_timestamp_field())
        )

        #######  Set field values  #######
        field_values = {}
        if request.method == "GET":
            # Set the form hash to the form_hash hidden field on the form
            field_values["form_hash"] = self._generate_form_hash()

            # Set form timestamp
            if ts := self.get_form_timestamp():
                field_values["form_timestamp"] = ts

        #######  Call super init  #######
        super().__init__(*args, **kwargs, **field_values)

        #######  Delete Sub Form #######
        self.delete_sub_form = self.build_delete_sub_form()

        #######  Store form for submission later #######
        g.setdefault("formation_forms", []).append(self)

    def input_fields(self):
        for _, field in self._fields.items():
            # Don't yield the submit field
            if field.id == "submit_field":
                continue
            if isinstance(field, WTFormsHiddenField):
                continue
            yield field

    def input_fields_as_dict(self):
        return {field.id: field.data for field in self.input_fields()}

    def db_fields(self):
        for _, field in self._fields.items():
            # Don't yield the submit field
            if field.id == "submit_field":
                continue
            if not hasattr(field, "db_field") or not field.db_field:
                continue
            yield field

    def db_fields_as_dict(self):
        return {field.id: field.data for field in self.db_fields()}

    #######  During Submit Handlers  #######
    def check_submission(self):
        return self.is_submitted() and self._validate_form_hash()

    def validate_submission(self):
        if self.check_submission() and self.validate():
            if self.check_form_timestamp():
                return True
            raise ObsoleteFormData
        return False

    def on_form_success(self):
        pass

    def on_form_validation_error(self):
        pass

    def on_obsolete_form_data(self):
        pass

    def on_form_handling_error(self):
        pass

    def handle_submission(self):
        try:
            if not self.check_submission():
                return False
            if not self.validate_submission():
                raise FormValidationError

            form_response = self.on_submit() or redirect(request.url)
            self.on_form_success()
            return form_response

        except FormValidationError:
            self.on_form_validation_error()
            raise
        # Reraise trigger template render "error" so it bubbles up to the render form template
        except TriggerTemplateRender:
            raise
        except ObsoleteFormData:
            return self.on_obsolete_form_data() or redirect(request.url)
        except:
            self.on_form_handling_error()
            raise TriggerTemplateRender(
                "Form had errors on submission so rerender the template"
            )

    #######  Delete Sub Form #######
    def build_delete_sub_form(self) -> Optional["FormationDeleteSubForm"]:
        pass


class FormationRenderForm(FormationForm):
    # Form flags
    obj_name: str | None
    static_info: dict

    @property
    def form_id(self):
        # Get the form class name
        class_name = self.__class__.__name__
        # Split class name on uppercase letters
        words = re.findall("[A-Z][a-z]*", class_name)
        # Join lowercased class name words with underscore
        form_id = "_".join(words).lower()

        return form_id

    def __init__(
        self,
        *args,
        db_obj=None,
        obj_name=None,
        static_info=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            db_obj=db_obj,
            **kwargs,
        )

        self._set_default_form_attr("obj_name", obj_name)
        self._set_default_form_attr("static_info", static_info or {})

    def render(
        self,
        pre_form_html: list | None = None,
        post_form_html: list | None = None,
        submit_row_buttons: list | None = None,
        **form_kwargs,
    ):
        # Handle mutable function params
        if pre_form_html is None:
            pre_form_html = []
        if post_form_html is None:
            post_form_html = []
        if submit_row_buttons is None:
            submit_row_buttons = []

        # Form Rendering
        form_kwargs.setdefault("method", "post")
        form_kwargs.setdefault("id", self.form_id)
        if self.errors:
            # Set the form error message to a data attr to be handled with css
            form_kwargs.setdefault("data-error-message", self.error_message())

        form_html = [
            f"<form {html_params(**form_kwargs)}>",
            self.hidden_tag(),
            "".join(pre_form_html),
            *[field() for field in self.input_fields()],
            '<div class="submit-row">',
            self.submit_field(),
            "".join(submit_row_buttons),
            "</div>",
            "</form>",
            "".join(post_form_html),
        ]

        return Markup("".join(form_html))


class FormationDeleteSubForm(FormationForm):
    base_form: FormationForm

    delete_sub_form_object_id: WTFormsHiddenField

    @classmethod
    def create_object_id_field(cls):
        return cls.create_hidden_field()

    @property
    def form_id(self):
        return f"{self.base_form.form_id}_delete-form"

    def create_submit_field(self):
        raise NotImplementedError("create_submit_field must be overridden")
        return BtnSubmitField("Yes, Delete it Forever", render_kw={"class": "delete"})

    def __init__(
        self,
        *args,
        base_form=None,
        obj_name=None,
        **kwargs,
    ):
        # #######  Add form hidden fields  #######
        self._unbound_fields.append(
            ("delete_sub_form_object_id", self.create_object_id_field())
        )

        #######  Set default form attributes  #######
        self._set_default_form_attr("base_form", base_form)

        assert (
            self.base_form is not None
        ), "base_form must be set either in the class or when __init__ is called"

        super().__init__(*args, **kwargs)

    @property
    def object_id(self):
        return self.delete_sub_form_object_id.unsigned_data

    def _generate_form_hash(self):
        # Get the class name
        class_name = f"{self.base_form.__class__.__name__}|delete_sub_form"

        # Use hashlib to generate a unique hash based on the unique string
        return hashlib.sha256(class_name.encode()).hexdigest()

    def on_submit(self):
        return_val = self.base_form.on_delete_submit(self)
        return return_val


class FormationRenderDeleteSubForm(FormationDeleteSubForm, FormationRenderForm):
    pass
