class FormNotSubmitted(Exception):
    """Formation Form Exception when it was not submitted, but was in the view function."""

    pass


class FormNotValidated(Exception):
    """Formation Form Exception when validation fails."""

    pass


class RerenderTemplate(Exception):
    """Used to stop a Formation Form's handling.
    Should be called inside Form.valid_form_handler().
    Also used internally for falling out of complex method chains."""

    pass
