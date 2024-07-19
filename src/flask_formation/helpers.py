def grammatical_join(lst, default="", attr=None):
    lst = [getattr(i, attr) if attr else i for i in lst]

    if len(lst) < 1:
        return default

    if len(lst) == 1:
        return lst[0]

    if len(lst) == 2:
        return " and ".join(lst)

    return f"{', '.join(lst[:-1])}, and {lst[-1]}"
