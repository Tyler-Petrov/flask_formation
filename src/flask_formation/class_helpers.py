import typing as t
from functools import wraps

from wtforms.utils import unset_value

from flask_formation.dictionary_helpers import (
    create_nested_dictionary,
    update_nested_dictionary_with_format_string,
)
from flask_formation.string_helpers import split_on_uppercase_char
from flask_formation.type import T


class Labeler:
    """Defines some helpful naming classmethods for any class."""

    @classmethod
    def class_name(cls):
        """Returns the Python class name."""
        return cls.__name__

    @classmethod
    def snake_name(cls):
        """Returns the class_name in snake case."""
        return "_".join(split_on_uppercase_char(cls.class_name())).lower()

    @classmethod
    def client_name(cls):
        """Returns the class_name but with spaces before uppercase characters like regular words."""
        return " ".join(split_on_uppercase_char(cls.class_name()))


def cache_method(f):
    """
    A decorator to cache the result of a method or property on an instance.

    - If the decorated function is a method, the result is cached the first time
      the method is called with specific arguments, and subsequent calls return the cached value.
    - If the decorated function is a property, the property value is cached after the first access.

    The cached value is stored as an attribute on the instance, prefixed with an underscore and the method/property name.

    :param f: The method or property to cache.
    :return: A wrapped function or property with caching enabled.
    """

    @wraps(f)
    def cache_function(self, *args, **kwargs):
        """
        Wrapper function that checks for a cached value before calling the original function.

        :param self: The instance of the class.
        :param args: Positional arguments for the function.
        :param kwargs: Keyword arguments for the function.
        :return: The cached value or the result of the original function.
        """
        # Construct the name of the cache attribute
        cached_attr_name = f"_{f.__name__}"

        # Check if the value is already cached
        if not hasattr(self, cached_attr_name):
            # Call the original function and cache its result
            func_value = f(self, *args, **kwargs)

            # If the result is a generator, convert it to a list for caching
            if isinstance(func_value, t.Generator):
                func_value = list(func_value)

            # Store the result in the instance's attribute
            setattr(self, cached_attr_name, func_value)

        # Retrieve and return the cached value
        return getattr(self, cached_attr_name)

    # If the function is a property, wrap the cache_function as a property
    if isinstance(f, property):
        return property(cache_function)

    # Otherwise, return the decorated function
    return cache_function


def update_attributes(obj, **update_dictionary):
    """Update objs's attributes using the key word arguments supplied.
    Uses dot notation and update_nested_dictionary_with_format_string for setting keys in a dictionary.
        This means that when setting dictionary keys the overwritten value is accessible using "{super_key}" in the new dictionary value.

    Args:
        obj (Any): Any object with a setter for attributes.
    """
    for key, value in update_dictionary.items():
        if value is unset_value:
            continue

        # If the key has a . (period) in it, and it's not at the beginning or end
        if "." in key and not (key.startswith(".") or key.endswith(".")):
            # Separate key into first key and sub keys
            first_key, sub_keys = key.split(".", maxsplit=1)

            # Get original attribute from object
            original_attribute = getattr(obj, first_key, {})

            # If the original attribute is either a dictionary to start
            # or it's the default empty dictionary from getattr
            # then update it with the new value
            if isinstance(original_attribute, dict):
                original_dictionary = original_attribute

                # Create the dictionary used to update the original dictionary
                update_dictionary = create_nested_dictionary(sub_keys, value)

                # The updated dictionary
                new_attribute = update_nested_dictionary_with_format_string(
                    original_dictionary, update_dictionary
                )

                # Set the updated dictionary to the object
                setattr(obj, first_key, new_attribute)
                continue

        setattr(obj, key, value)


# Unused, opted for werkzeug.utils.cached_property instead
class mutable_property(t.Generic[T]):
    """
    A custom property-like descriptor that allows dynamic overriding of
    its value on an instance-by-instance basis, while preserving the original
    property behavior when the override is removed.
    """

    def __init__(self, getter: T):
        """
        Initialize the mutable_property with a getter function.

        Args:
            getter (callable): A function that retrieves the value of the property.
        """
        self.getter = getter  # The original getter function
        self.name = getter.__name__  # The name of the property, derived from the getter

    def __get__(self, instance, owner) -> T:
        """
        Retrieve the value of the property.

        If the property has been overridden for the instance, return the
        overridden value. Otherwise, call the original getter.

        Args:
            instance: The instance accessing the property.
            owner: The class of the instance.

        Returns:
            The overridden value (if set) or the value from the getter.
        """
        if instance is None:
            # If accessed on the class, return the descriptor itself
            return self

        # Check if the property has been overridden on the instance
        if self.name in instance.__dict__:
            return instance.__dict__[self.name]

        # Otherwise, call the original getter
        return self.getter(instance)

    def __set__(self, instance, value):
        """
        Override the property value for the instance.

        Args:
            instance: The instance on which to override the property.
            value: The new value to assign to the property.
        """
        # Store the new value in the instance's dictionary
        instance.__dict__[self.name] = value

    def __delete__(self, instance):
        """
        Remove the overridden value, restoring the original property behavior.

        If no overridden value exists, raise an AttributeError.

        Args:
            instance: The instance for which the property override should be removed.

        Raises:
            AttributeError: If there is no overridden value to delete.
        """
        if self.name in instance.__dict__:
            # Remove the overridden value from the instance's dictionary
            del instance.__dict__[self.name]
        else:
            # If no override exists, raise an error
            raise AttributeError(f"{self.name} is not set and cannot be deleted")
