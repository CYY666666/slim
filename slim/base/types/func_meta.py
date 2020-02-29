from typing import List, Type, Set, Any, Optional

from schematics import Model

from slim.utils.jsdict import JsDict


class FuncMeta(JsDict):
    va_query_lst: List[Type[Model]]
    va_post_lst: List[Type[Model]]
    interface_roles: Optional[Set[Any]]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.va_post_lst = []
        self.va_query_lst = []
        self.interface_roles = None