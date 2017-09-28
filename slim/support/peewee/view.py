import json
import binascii
import logging

import peewee
# noinspection PyPackageRequirements
from playhouse.postgres_ext import BinaryJSONField
from playhouse.shortcuts import model_to_dict

from ...base.permission import AbilityRecord
from ...retcode import RETCODE
from ...utils import to_bin, pagination_calc, dict_filter, bool_parse
from ...base.view import AbstractSQLView, AbstractSQLFunctions

logger = logging.getLogger(__name__)


class PeeweeAbilityRecord(AbilityRecord):
    # noinspection PyMissingConstructor
    def __init__(self, table_name, val: peewee.Model):
        self.table = table_name
        self.val = val  # 只是为了补全才继承的

    def keys(self):
        # noinspection PyProtectedMember
        return self.val._meta.fields.keys()

    def get(self, key):
        return getattr(self.val, key)

    def has(self, key):
        return hasattr(self.val, key)

    def to_dict(self, available_columns=None):
        if available_columns:
            return dict_filter(model_to_dict(self.val), available_columns)
        return model_to_dict(self.val)


_peewee_method_map = {
    # '+': '__pos__',
    # '-': '__neg__',
    '=': '__eq__',
    '==': '__eq__',
    '!=': '__ne__',
    '<>': '__ne__',
    '<': '__lt__',
    '<=': '__le__',
    '>': '__gt__',
    '>=': '__ge__',
    'eq': '__eq__',
    'ne': '__ne__',
    'ge': '__ge__',
    'gt': '__gt__',
    'le': '__le__',
    'lt': '__lt__',
    'in': '__lshift__',  # __lshift__ = _e(OP.IN)
    'is': '__rshift__',  # __rshift__ = _e(OP.IS)
    'isnot': '__rshift__'
}


# noinspection PyProtectedMember,PyArgumentList
class PeeweeSQLFunctions(AbstractSQLFunctions):
    def _get_args(self, args):
        pw_args = []
        for field_name, op, value in args:
            field = self.view.fields[field_name]

            conv_func = None
            # 说明：我记得 peewee 会自动完成 int/float 的转换，所以不用自己转
            if isinstance(field, peewee.BlobField):
                conv_func = to_bin
            elif isinstance(field, peewee.BooleanField):
                conv_func = bool_parse

            if conv_func:
                try:
                    if op == 'in':
                        value = list(map(conv_func, value))
                    else:
                        value = conv_func(value)
                except binascii.Error:
                    self.err = RETCODE.INVALID_HTTP_PARAMS, 'Invalid query value for blob: Odd-length string'
                    return
                except ValueError as e:
                    self.err = RETCODE.INVALID_HTTP_PARAMS, ' '.join(map(str, e.args))

            pw_args.append(getattr(field, _peewee_method_map[op])(value))
        return pw_args

    def _get_orders(self, orders):
        # 注：此时早已经过检查可确认orders中的列存在
        ret = []
        fields = self.view.fields

        for i in orders:
            if len(i) == 2:
                # column, order
                item = fields[i[0]]
                if i[1] == 'asc': item = item.asc()
                elif i[1] == 'desc': item = item.desc()
                ret.append(item)

            elif len(i) == 3:
                # column, order, table
                # TODO: 日后再说
                pass
        return ret

    def _make_select(self, info):
        nargs = self._get_args(info['args'])
        if self.err: return
        orders = self._get_orders(info['orders'])
        if self.err: return

        q = self.view.model.select()
        # peewee 不允许 where 时 args 为空
        if nargs: q = q.where(*nargs)
        if orders: q = q.order_by(*orders)
        return q

    async def select_one(self, info):
        try:
            q = self._make_select(info)
            if self.err: return self.err
            return RETCODE.SUCCESS, PeeweeAbilityRecord(self.view.table_name, q.get())
        except self.view.model.DoesNotExist:
            return RETCODE.NOT_FOUND, None

    async def select_pagination_list(self, info, size, page):
        q = self._make_select(info)
        count = q.count()
        pg = pagination_calc(count, size, page)
        # offset = size * (page - 1)

        func = lambda item: PeeweeAbilityRecord(self.view.table_name, item)
        pg["items"] = list(map(func, q.paginate(page, size)))
        return RETCODE.SUCCESS, pg

    async def update(self, info, data):
        try:
            q = self._make_select(info)
            if self.err: return self.err
            item = q.get()
            db = self.view.model._meta.database
            with db.atomic():
                ok = False
                try:
                    for k, v in data.items():
                        if k in self.view.fields:
                            setattr(item, k, v)
                    item.save()
                    ok = True
                except peewee.DatabaseError:
                    db.rollback()

            if ok:
                return RETCODE.SUCCESS, {'count': 1}

        except self.view.model.DoesNotExist:
            return RETCODE.NOT_FOUND, None

    async def insert(self, data):
        if not len(data):
            return RETCODE.INVALID_HTTP_PARAMS, None
        db = self.view.model._meta.database

        kwargs = {}
        for k, v in data.items():
            if k in self.view.fields:
                field = self.view.fields[k]
                if isinstance(field, BinaryJSONField):
                    kwargs[k] = json.loads(v)
                else:
                    kwargs[k] = v

        with db.atomic():
            try:
                item = self.view.model.create(**kwargs)
                return RETCODE.SUCCESS, PeeweeAbilityRecord(self.view.table_name, item)
            except peewee.DatabaseError as e:
                db.rollback()
                logger.error("database error", e)
                return RETCODE.FAILED, None


class PeeweeView(AbstractSQLView):
    model = None
    # fields
    # table_name

    @classmethod
    def cls_init(cls):
        # py3.6: __init_subclass__
        if not (cls.__name__ == 'PeeweeView' and AbstractSQLView in cls.__bases__):
            assert cls.model, "%s.model must be specified." % cls.__name__
        super().cls_init()

    def __init__(self, request):
        super().__init__(request)
        self._sql = PeeweeSQLFunctions(self)

    # noinspection PyProtectedMember
    @staticmethod
    async def _fetch_fields(cls_or_self):
        if cls_or_self.model:
            cls_or_self.fields = cls_or_self.model._meta.fields
            cls_or_self.table_name = cls_or_self.model._meta.db_table
