import random
import re
import string
import typing as t
from collections import UserString


def random_string_generator(length: int) -> str:
    """
    Generate a random string of a specified length using letters and digits.

    :param length: Length of the desired random string.
    :return: Randomly generated string.
    """
    if length <= 0:
        raise ValueError("Length must be a positive integer.")

    characters = string.ascii_letters + string.digits
    return "".join(random.choices(characters, k=length))


def split_on_uppercase_char(string: str) -> list[str]:
    """Splits the supplied string at every uppercase character.
    The string is converted to a string if it isn't one already.

    Args:
        string (str): Any string.

    Returns:
        list: A list of words.
    """
    return re.findall("[A-Z][^A-Z]*", str(string))


class PluralityAwareString(UserString):
    """
    A class to handle singular and plural forms of a string, derived from UserString.
    Defaults to a singular string. When representing this object as a string the singular version is used.
    """

    # Matches singular(es) or singular(s)
    implicit_pattern = r"([a-zA-Z]+)\((s|es)\)"

    # Matches (singular|plural)
    explicit_pattern = r"\(([^|]*)\|([^|]*)\)"

    def __call__(
        self, plural_determinate: bool | int | list | t.Callable = False
    ) -> str:
        """
        Replace (<singular-text>|<plural-text>) patterns in the instance's data (string)
            with the respective value based on the value of plural_determinate.

        :param plural_determinate: Can be callable, list, int, or boolean, determining which part of (a|b) to use.
            - Callable: The return value is used against the below types.
            - List: Its length is used to determine plurality.
            - Integer: `> 1` means plural.
            - Boolean: Directly determines plurality.
        :return: Processed string with (a|b) patterns replaced.
        """
        # Handle various types of `plural_determinate`.
        if callable(plural_determinate):
            # If plural_determinate is callable, call it to get its value.
            plural_determinate = plural_determinate()

        if isinstance(plural_determinate, list):
            # If plural_determinate is a list, use its length to determine plurality.
            plural_determinate = len(plural_determinate)

        if isinstance(plural_determinate, bool):
            # If plural_determinate is an integer, use it to determine plurality.
            plural = plural_determinate
        elif isinstance(plural_determinate, int):
            # If plural_determinate is an integer, use > 1 to determine plurality.
            plural = plural_determinate > 1
        else:
            # Default to False (singular) for other types.
            plural = False

        def replace_explicit(match):
            """
            Replace match based on singular/plural determination for '(singular|plural)' pattern.
            """
            return match.group(2 if plural else 1)

        def replace_implicit(match):
            """
            Replace match based on singular/plural determination for 'word(s)' or 'box(es)' pattern.
            """
            base = match.group(1)
            suffix = match.group(2)
            return base + suffix if plural else base

        processed_string = re.sub(self.implicit_pattern, replace_implicit, self.data)
        processed_string = re.sub(
            self.explicit_pattern, replace_explicit, processed_string
        )
        return processed_string

    def __str__(self):
        return self.__call__(plural_determinate=False)


def grammatical_join(lst, default="", attr=None):
    lst = [getattr(i, attr) if attr else i for i in lst]

    if len(lst) < 1:
        return default

    if len(lst) == 1:
        return lst[0]

    if len(lst) == 2:
        return " and ".join(lst)

    return f"{', '.join(lst[:-1])}, and {lst[-1]}"
