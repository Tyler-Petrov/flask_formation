import copy
import typing as t

from wtforms.utils import unset_value


def update_nested_dictionary(
    base_dictionary: dict,
    updates: dict | None,
    value_setter: t.Callable[[dict, t.Any, t.Any], t.Any] | None = None,
) -> dict:
    """
    Updates a copy of the base dictionary with values from the updates dictionary in a nested fashion,
    leaving the original base dictionary unmodified.

    Args:
        base_dictionary (dict): Base dictionary to be updated.
        updates (dict | None): Updates to be performed on the base dictionary. If None then the base dictionary is return immediately.

    Perhaps an example? If this function is supplied these values:
        base_dictionary = {
            "name": {
                "first": "Alyse",
                "last": "Marks",
            }
        }
        updates = {
            "name": {
                "last": "Petrov",
            }
        }

    then the return dictionary would be:
        {
            "name": {
                "first": "Alyse",
                "last": "Petrov",
            }
        }
    """
    if updates is None:
        return base_dictionary

    base_dictionary_copy = copy.deepcopy(base_dictionary)

    for key, value in updates.items():
        if (
            key in base_dictionary_copy
            and isinstance(base_dictionary_copy[key], dict)
            and isinstance(value, dict)
        ):
            # Recursive call
            base_dictionary_copy[key] = update_nested_dictionary(
                base_dictionary_copy[key], value, value_setter=value_setter
            )
        else:
            if value_setter is not None and callable(value_setter):
                value = value_setter(base_dictionary_copy, key, value)

            base_dictionary_copy[key] = value

    return base_dictionary_copy


def update_nested_dictionary_with_format_string(
    base_dictionary: dict,
    updates: dict | None,
    format_undefined_value: bool = True,
) -> dict:
    """Update a dictionary with a format str which can access the old dictionary's value.
    .format(...) is run on each updates string value with the {super_value} or {super} being the base_dictionary's value.
    This function is helpful for when a user would like to insert the replaced dictionary's value into the updated dictionary's value.

    This function calls update_nested_dictionary under the hood.

    Args:
        base_dictionary (dict): base key/values to be updated
        updates (dict | None): Updater for the old values. This dictionary has the format string as the value.
            If updates is None then it's set to an empty dictionary.
        format_undefined_value (bool): Whether to format the new value (thus removing the {super_value} reference) if there isn't a corresponding value in the base dictionary.

    Raises:
        KeyError: If there is an unknown key (not super or super_value) requested in the format string, then a KeyError is raised.

    Returns:
        dict: This is a new dictionary, so base_dictionary won't be updated.
    """

    def value_setter(base_dictionary, key, value):
        super_value = base_dictionary.get(key, unset_value)
        if not format_undefined_value and super_value is unset_value:
            return value
        if not isinstance(value, str):
            return value
        return value.format(super=super_value, super_value=super_value)

    return update_nested_dictionary(
        base_dictionary,
        updates,
        value_setter=value_setter,
    )


def create_nested_dictionary(
    dot_key: str, value, base_dictionary: dict | None = None
) -> dict:
    """
    Creates or updates a nested dictionary from a dot-notation key.

    Args:
        dot_key (str): The dot-notation key (e.g., "person.name.first").
        value: The value to assign to the key.
        base_dictionary (dict | None): The base dictionary to update. If None, a new dictionary is created.

    Returns:
        dict: The updated dictionary.
    """
    if base_dictionary is None:
        base_dictionary = {}

    keys = dot_key.split(".")
    current = base_dictionary

    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]

    current[keys[-1]] = value
    return base_dictionary
