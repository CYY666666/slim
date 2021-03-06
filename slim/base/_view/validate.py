from typing import Optional, Type, TYPE_CHECKING, Iterable, Mapping, List, Tuple

from aiohttp.web_request import BaseRequest
from schematics import Model
from schematics.exceptions import DataError
from schematics.types import ListType, ModelType

from slim.base.types import InnerInterfaceName
from slim.exception import InvalidParams, InvalidPostData, InvalidHeaders
from .err_catch_context import ErrorCatchContext

if TYPE_CHECKING:
    from slim.base._view.base_view import BaseView


async def view_validate_check(view: "BaseView", va_query: Optional[Type[Model]], va_post: Optional[Type[Model]],
                              va_headers: Optional[Type[Model]] = None, va_write_value: Type[Model] = None):
    with ErrorCatchContext(view):

        def do_validate(va_model, data, err_cls):
            try:
                return va_model(strict=False, validate=True, partial=False, raw_data=data)
            except DataError as e:
                raise err_cls(e.to_primitive())

        if va_query:
            # TODO: 这里有问题，对SQL请求来说，多个同名参数项，会在实际解析时会被折叠为一个数组，但是这里没有
            view._.validated_query = do_validate(va_query, view.params, InvalidParams)

        if view.method in BaseRequest.POST_METHODS:
            from slim.base._view.abstract_sql_view import AbstractSQLView
            post_data = await view.post_data()

            if va_write_value:
                if isinstance(view, AbstractSQLView):
                    write_values = []

                    if view.current_interface == InnerInterfaceName.BULK_INSERT:
                        items = post_data.get('items')
                        if isinstance(items, (List, Tuple)):
                            for i in items:
                                write_values.append(do_validate(va_write_value, i, InvalidPostData))
                        else:
                            raise InvalidPostData("`items` from post data should be list")
                    elif view.current_interface in (InnerInterfaceName.SET, InnerInterfaceName.NEW):
                        write_values.append(do_validate(va_write_value, post_data, InvalidPostData))

                    view._.validated_write_values = write_values

            if va_post:
                view._.validated_post = do_validate(va_post, await view.post_data(), InvalidPostData)

        if va_headers:
            view._.validated_headers = do_validate(va_headers, view.headers, InvalidHeaders)
