import typing as t
from collections.abc import Mapping

from markupsafe import Markup

T = t.TypeVar("T", bound=t.Callable[..., t.Any])
HTML: t.TypeAlias = str | Markup | list[str | Markup]
Document: t.TypeAlias = Mapping | object | t.Callable[[], Mapping | object]
