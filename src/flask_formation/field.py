import copy
import typing as t
from dataclasses import dataclass

from markupsafe import Markup
from multidict import MultiDict
from wtforms import Field
from wtforms.utils import unset_value

from flask_formation.class_helpers import Labeler
from flask_formation.widget import SectionLabelWidget, SubmitButtonWidget


@dataclass(frozen=True, init=False)
class WidgetField:
    """An object for storing a specific state of a WTForms field.

    Attributes:
        id (str): Set directly from WTForms field.id.
        name (str): Set directly from WTForms field.name.
        data: This is set after field.process_data(...) has been run for each widget.
        markup (Markup): Rendered field Markup with field.process_data(...) previously run.
    """

    id: str
    name: str
    data: t.Any
    markup: Markup

    def __init__(self, field: Field):
        object.__setattr__(self, "id", field.id)
        object.__setattr__(self, "name", field.name)
        object.__setattr__(self, "data", field.data)
        object.__setattr__(self, "markup", field.__call__())

    @classmethod
    def reset_wtforms_field(cls, field: "Field"):
        """Resets field to the state before .process() was run on it.
        The attribute .raw_data is removed, and the attribute .data is set to wtforms.utils.unset_value.

        This method modifies the above attributes on the field instance passed in.

        Args:
            field (Field): WTForms field
        """
        # Delete field's raw_data attribute if it exists. It was added when field.process was run the first time.
        try:
            delattr(field, "raw_data")
        except AttributeError:
            pass

        # Reset field.data
        field.data = unset_value

    @classmethod
    def build_from_field(
        cls,
        field: Field,
        formdata: MultiDict | None = None,
        unprocessed_data: str = unset_value,
    ) -> t.Self:
        """Builds a WidgetField from the WTForms field supplied.

        If unprocessed_data is not None:
            First the WTForms field supplied has it's attributes copied and stored so the previous state of the field is preserved.
            Next the unprocessed_data is given to the .process_data(...) method, and the field is rendered.
                The processed data and field markup are saved in the __init__ of WidgetField.
            Finally the field is reverted back to it's previous state after the WidgetField is initialized.

        Args:
            field (Field): Any WTForms field.
            formdata (MultiDict): Any multidict (dictionary with multiple of the same keys). Defaults to None.
            unprocessed_data (str, optional):
                Data that hasn't been through a WTForm field's .process_data(...). Defaults to wtforms.utils.unset_value.

        Returns:
            WidgetField: A WidgetField with field markup (and other attributes) pre calculated.
        """

        # Save the state of this fields arguments
        field_dict = copy.copy(field.__dict__)

        # Get this field's processed data for this widget
        cls.reset_wtforms_field(field)
        field.process(formdata, unprocessed_data)

        # Clear field errors if there's no formdata
        if formdata is None:
            field.errors = []

        # Save WidgetField instance to return
        widget_field = cls(field=field)

        # Reset this field's arguments back to the state before process_data was called on it
        field.__dict__ = field_dict

        return widget_field


class SubmitButtonField(Field, Labeler):
    """
    This field represents an HTML ``<button>`` and can be used for a form submission.

    This field's .data isn't directly converted into a boolean like wtforms.SubmitField.
        The exception to this is if this field's data is contained in either the true_values or false_values attributes.
        If it is then this field's .data is set to the respective boolean.
    """

    widget = SubmitButtonWidget()

    true_values: set[str] = {"True", "true"}
    false_values: set[str] = {"False", "false"}

    def process_formdata(self, valuelist):
        if valuelist:
            data = valuelist[0]
            if data in self.true_values:
                data = True
            elif data in self.false_values:
                data = False
            self.data = data

    def _value(self):
        return str(self.data or True)


class SectionLabel(Field):
    widget = SectionLabelWidget()
